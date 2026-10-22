"""Shared image-upload validation (used by plant identify and, later, photo posts)."""

from dataclasses import dataclass

from fastapi import UploadFile

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
