from contextlib import contextmanager
from io import BytesIO
from typing import Iterator
import warnings

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError

ALLOWED_IMAGE_TYPES = {"image/jpeg": "JPEG", "image/png": "PNG"}
MAX_IMAGE_PIXELS = 16_000_000


@contextmanager
def validated_image(data: bytes, content_type: str, max_bytes: int) -> Iterator[Image.Image]:
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(415, detail="Use JPEG or PNG.")
    if not data or len(data) > max_bytes:
        raise HTTPException(413, detail=f"The image must be between 1 byte and {max_bytes // (1024 * 1024)} MiB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as original:
                if original.format != ALLOWED_IMAGE_TYPES[content_type]:
                    raise HTTPException(422, detail="Image content does not match its declared format.")
                if original.width * original.height > MAX_IMAGE_PIXELS or getattr(original, "n_frames", 1) != 1:
                    raise HTTPException(422, detail="Use a single image with at most 16 million pixels.")
                original.verify()
            with Image.open(BytesIO(data)) as original:
                original.load()
                yield original
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError,
            Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise HTTPException(422, detail="The image is invalid or cannot be decoded.") from exc
