import io

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.errors import ApiError
from app.uploads import MAX_UPLOAD_BYTES, read_image_upload

TYPE_MESSAGE = "Please use a JPG, PNG or WebP image"
SIZE_MESSAGE = "That photo is over 5 MB"

JPEG_HEAD = b"\xff\xd8\xff\xe0"
PNG_HEAD = b"\x89PNG\r\n\x1a\n"


def make_upload(data=JPEG_HEAD, content_type="image/jpeg", filename="photo.jpg", size=None):
    """An UploadFile whose bytes are `data` padded with zeros up to `size`."""
    if size is not None:
        data = data + b"\x00" * (size - len(data))
    headers = Headers({"content-type": content_type}) if content_type is not None else Headers()
    return UploadFile(io.BytesIO(data), filename=filename, headers=headers)


def error_of(upload):
    with pytest.raises(ApiError) as excinfo:
        read_image_upload(upload)
    return excinfo.value


# --- Accepted files --------------------------------------------------------


@pytest.mark.parametrize(
    ("head", "content_type"),
    [(JPEG_HEAD, "image/jpeg"), (PNG_HEAD, "image/png")],
)
def test_valid_image_returns_bytes_sniffed_type_and_filename(head, content_type):
    upload = make_upload(head + b"body", content_type, filename="fern.img")

    result = read_image_upload(upload)

    assert result.data == head + b"body"
    assert result.content_type == content_type
    assert result.filename == "fern.img"


# --- Declared type -----------------------------------------------------------


@pytest.mark.parametrize("content_type", ["image/gif", "text/plain", None])
def test_declared_type_outside_the_allowed_three_is_415(content_type):
    error = error_of(make_upload(content_type=content_type))

    assert error.status_code == 415
    assert error.message == TYPE_MESSAGE


# --- Size ----------------------------------------------------------------------


def test_file_over_5_mib_is_413_and_exactly_5_mib_passes():
    error = error_of(make_upload(size=5 * 1024 * 1024 + 1))

    assert error.status_code == 413
    assert error.message == SIZE_MESSAGE
    assert len(read_image_upload(make_upload(size=MAX_UPLOAD_BYTES)).data) == MAX_UPLOAD_BYTES


# --- Sniffing ------------------------------------------------------------------


def test_empty_file_is_415():
    error = error_of(make_upload(data=b""))

    assert error.status_code == 415
    assert error.message == TYPE_MESSAGE


def test_png_declared_as_jpeg_is_415():
    error = error_of(make_upload(data=PNG_HEAD + b"body", content_type="image/jpeg"))

    assert error.status_code == 415
    assert error.message == TYPE_MESSAGE


