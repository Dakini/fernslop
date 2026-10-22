"""Shared image-upload validation (plant identify and photo posts) and photo metadata stripping."""

import io
import struct
from dataclasses import dataclass

from fastapi import UploadFile
from PIL import Image, ImageOps, ImageSequence

from app.errors import ApiError

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_CONTENT_TYPES = ("image/jpeg", "image/png", "image/webp")

TOO_LARGE_MESSAGE = "That photo is over 5 MB"
UNSUPPORTED_TYPE_MESSAGE = "Please use a JPG, PNG or WebP image"

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class ValidatedImage:
    """An upload that passed validation. ``content_type`` is the sniffed type."""

    data: bytes
    content_type: str
    filename: str | None


def sniff_image_type(data: bytes) -> str | None:
    """The image type the leading bytes say this is, or ``None`` if unrecognised."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(_PNG_SIGNATURE):
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def read_image_upload(file: UploadFile) -> ValidatedImage:
    """Validate an uploaded image and return its bytes, sniffed type and filename.

    Checks in order: declared type (415), size (413), then the bytes themselves
    against the declared type (415). Raises ``ApiError`` on failure.
    """
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise ApiError(415, UNSUPPORTED_TYPE_MESSAGE)

    # Read one byte past the limit so an oversize file is detected without trusting file.size.
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise ApiError(413, TOO_LARGE_MESSAGE)

    sniffed = sniff_image_type(data)
    if sniffed is None or sniffed != file.content_type:
        raise ApiError(415, UNSUPPORTED_TYPE_MESSAGE)

    return ValidatedImage(data=data, content_type=sniffed, filename=file.filename)


# --- Metadata stripping ---------------------------------------------------------
#
# Photos are public by URL, so what a camera writes beside the pixels (GPS, device,
# timestamps, comments) is removed before a photo is stored. A photo is re-encoded only
# when it carries something to remove: a clean one is stored byte for byte, which keeps
# its quality and makes stripping an already stripped photo a no-op.

_PIL_FORMATS = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}
_DECODED_AS = {"image/jpeg": ("JPEG", "MPO"), "image/png": ("PNG",), "image/webp": ("WEBP",)}

# Segments and chunks that only describe how to draw the pixels. Anything else is metadata.
_JPEG_KEPT_APP = {0xE0: b"JFIF\x00", 0xE2: b"ICC_PROFILE\x00", 0xEE: b"Adobe"}
_PNG_KEPT_CHUNKS = {
    b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"gAMA", b"cHRM", b"sRGB", b"iCCP",
    b"sBIT", b"bKGD", b"pHYs", b"hIST", b"acTL", b"fcTL", b"fdAT",
}  # fmt: skip
_WEBP_KEPT_CHUNKS = {b"VP8 ", b"VP8L", b"VP8X", b"ALPH", b"ANIM", b"ANMF", b"ICCP"}

_JPEG_QUALITY = 95
_WEBP_QUALITY = 90
_DECODE_ERRORS = (Image.DecompressionBombError, OSError, SyntaxError, ValueError, EOFError, struct.error)


def strip_metadata(image: ValidatedImage) -> bytes:
    """Return the image's bytes without EXIF, XMP, IPTC, comments or text chunks.

    The EXIF orientation is applied to the pixels first, so the photo still displays upright.
    The type stays the same, an ICC colour profile and transparency are kept, and an animated
    PNG or WebP stays animated. Bytes Pillow cannot decode, or an image over Pillow's
    decompression-bomb pixel limit, raise ``ApiError(415)``.
    """
    fmt = _PIL_FORMATS[image.content_type]
    try:
        with Image.open(io.BytesIO(image.data), formats=[fmt]) as img:
            too_big = Image.MAX_IMAGE_PIXELS is not None and img.width * img.height > Image.MAX_IMAGE_PIXELS
            if too_big or img.format not in _DECODED_AS[image.content_type]:
                raise ApiError(415, UNSUPPORTED_TYPE_MESSAGE)
            img.load()
            if not _has_metadata(image.data, image.content_type):
                return image.data
            return _reencode(img, fmt, _webp_is_lossless(image))
    except _DECODE_ERRORS as exc:
        raise ApiError(415, UNSUPPORTED_TYPE_MESSAGE) from exc


def _reencode(img: Image.Image, fmt: str, lossless: bool) -> bytes:
    params: dict = {}
    if icc_profile := img.info.get("icc_profile"):
        params["icc_profile"] = icc_profile
    if fmt == "JPEG":
        params["quality"] = _JPEG_QUALITY
    elif fmt == "WEBP":
        params.update(lossless=lossless, quality=100 if lossless else _WEBP_QUALITY)

    if fmt != "JPEG" and getattr(img, "is_animated", False):
        frames, durations = [], []
        for frame in ImageSequence.Iterator(img):
            durations.append(frame.info.get("duration", 0))
            frames.append(_bare(frame.copy()))
        first = frames[0]
        params.update(save_all=True, append_images=frames[1:], duration=durations, loop=img.info.get("loop", 0))
    else:
        # A JPEG with several pictures (MPO) keeps only the first.
        first = _bare(ImageOps.exif_transpose(img))

    out = io.BytesIO()
    first.save(out, format=fmt, **params)
    return out.getvalue()


def _bare(img: Image.Image) -> Image.Image:
    """The image with only its transparency left in ``info`` (Pillow writes some ``info`` keys back out)."""
    img.info = {k: v for k, v in img.info.items() if k == "transparency"}
    return img


def _has_metadata(data: bytes, content_type: str) -> bool:
    if content_type == "image/jpeg":
        return _jpeg_has_metadata(data)
    if content_type == "image/png":
        return _png_has_metadata(data)
    return _webp_has_metadata(data)


def _jpeg_has_metadata(data: bytes) -> bool:
    """Any APPn segment other than JFIF, ICC or Adobe, any comment, or anything after the end marker."""
    if not data.endswith(b"\xff\xd9"):
        return True
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            return True
        marker = data[i + 1]
        if marker == 0xFF:  # fill byte
            i += 1
            continue
        if marker == 0xDA:  # start of scan: the header segments are over
            return False
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:  # markers without a length
            i += 2
            continue
        length = int.from_bytes(data[i + 2 : i + 4], "big")
        payload = data[i + 4 : i + 2 + length]
        if marker == 0xFE:
            return True
        if 0xE0 <= marker <= 0xEF and not payload.startswith(_JPEG_KEPT_APP.get(marker, b"\x00\x00")):
            return True
        i += 2 + length
    return True


def _png_has_metadata(data: bytes) -> bool:
    """Any chunk other than image, colour or animation chunks, or anything after ``IEND``."""
    i = len(_PNG_SIGNATURE)
    while i + 8 <= len(data):
        length = int.from_bytes(data[i : i + 4], "big")
        kind = data[i + 4 : i + 8]
        if kind not in _PNG_KEPT_CHUNKS:
            return True
        i += 12 + length
        if kind == b"IEND":
            return i != len(data)
    return True


def _webp_chunks(data: bytes) -> list[bytes]:
    """The top-level RIFF chunk types."""
    kinds, i = [], 12
    while i + 8 <= len(data):
        kinds.append(data[i : i + 4])
        size = int.from_bytes(data[i + 4 : i + 8], "little")
        i += 8 + size + (size & 1)
    return kinds


def _webp_has_metadata(data: bytes) -> bool:
    """An ``EXIF``, ``XMP `` or unknown chunk, or bytes past the RIFF size."""
    if int.from_bytes(data[4:8], "little") + 8 != len(data):
        return True
    return any(kind not in _WEBP_KEPT_CHUNKS for kind in _webp_chunks(data))


def _webp_is_lossless(image: ValidatedImage) -> bool:
    return image.content_type == "image/webp" and b"VP8L" in _webp_chunks(image.data)
