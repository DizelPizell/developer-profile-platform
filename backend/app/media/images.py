"""Checks an uploaded image and re-encodes it to WebP (ADR-0022).

Re-encoding drops EXIF (GPS included) and proves the file is an image.
"""

import threading
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps

from app.models.projects import SCREENSHOT_MAX_SIDE

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
# Checked from the header, before any pixel is decoded: a decompression bomb
# is rejected without the memory it asks for.
MAX_PIXELS = 40_000_000
_FORMATS = ("JPEG", "PNG", "WEBP")
_WEBP_QUALITY = 82

# Pillow's own guard, for any path that decodes without the check below.
Image.MAX_IMAGE_PIXELS = MAX_PIXELS

# A 40 Mpx PNG takes about 160 MB decoded; parallel uploads would exhaust the
# backend's memory. Others wait for a slot in the thread pool.
MAX_CONCURRENT_REENCODES = 2
_reencode_slots = threading.BoundedSemaphore(MAX_CONCURRENT_REENCODES)

# What a broken or hostile file makes Pillow raise.
_DECODE_ERRORS = (OSError, SyntaxError, ValueError, EOFError, Image.DecompressionBombError)


class ImageRejected(Exception):
    """kind is the error type of the file field: invalid_image, image_too_large,
    too_many_pixels."""

    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


@dataclass(frozen=True)
class EncodedImage:
    data: bytes
    width: int
    height: int


def reencode(data: bytes) -> EncodedImage:
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImageRejected("image_too_large")
    with _reencode_slots:
        return _reencode(data)


def _reencode(data: bytes) -> EncodedImage:
    try:
        # The format comes from the content; the name and Content-Type are ignored.
        image = Image.open(BytesIO(data), formats=_FORMATS)
    except Image.DecompressionBombError:
        # Pillow's own check in open(), above twice MAX_IMAGE_PIXELS.
        raise ImageRejected("too_many_pixels") from None
    except _DECODE_ERRORS:
        raise ImageRejected("invalid_image") from None
    width, height = image.size
    if width * height > MAX_PIXELS:
        raise ImageRejected("too_many_pixels")
    try:
        # Applies the EXIF orientation that is dropped below; an animation keeps its first frame.
        image = ImageOps.exif_transpose(image)
        has_alpha = image.mode in ("RGBA", "LA", "PA") or (
            image.mode == "P" and "transparency" in image.info
        )
        image = image.convert("RGBA" if has_alpha else "RGB")
        image.thumbnail((SCREENSHOT_MAX_SIDE, SCREENSHOT_MAX_SIDE), Image.Resampling.LANCZOS)
        out = BytesIO()
        image.save(out, "WEBP", quality=_WEBP_QUALITY, exif=b"", xmp=b"")
    except _DECODE_ERRORS:
        raise ImageRejected("invalid_image") from None
    return EncodedImage(out.getvalue(), image.width, image.height)
