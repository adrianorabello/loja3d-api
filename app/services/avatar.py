from io import BytesIO

from fastapi import HTTPException
from PIL import Image, ImageOps
from app.services.images import validated_image

MAX_AVATAR_BYTES = 10 * 1024 * 1024
MAX_STORED_BYTES = 512 * 1024


def normalize_avatar(data: bytes, content_type: str) -> bytes:
    """Decode and re-encode an avatar; never persist untrusted original bytes."""
    with validated_image(data, content_type, MAX_AVATAR_BYTES) as original:
        image = ImageOps.exif_transpose(original)
        image.thumbnail((512, 512))
        rgba = image.convert("RGBA")
        output_image = Image.new("RGB", rgba.size, "white")
        output_image.paste(rgba, mask=rgba.getchannel("A"))
        output = BytesIO()
        output_image.save(output, format="JPEG", quality=85, optimize=True)
    result = output.getvalue()
    if len(result) > MAX_STORED_BYTES:
        raise HTTPException(422, detail="The normalized image is too large.")
    return result
