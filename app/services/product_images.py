import base64
import binascii
from uuid import uuid4
from typing import Any, Dict, List, Tuple

from bson import BSON, Binary
from fastapi import HTTPException
from app.services.images import ALLOWED_IMAGE_TYPES, validated_image

MAX_PRODUCT_IMAGE_BYTES = 2 * 1024 * 1024
MAX_PRODUCT_DOCUMENT_BYTES = 16 * 1024 * 1024


def image_url(product_id: str, image_id: str) -> str:
    return f"/api/v1/products/{product_id}/images/{image_id}"


def decode_product_image(value: str) -> Tuple[bytes, str]:
    header, separator, encoded = value.partition(",")
    content_type = header.removeprefix("data:").removesuffix(";base64")
    if not separator or header != f"data:{content_type};base64" or content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(415, detail="Use JPEG or PNG images encoded as base64.")
    if len(encoded) > 4 * ((MAX_PRODUCT_IMAGE_BYTES + 2) // 3):
        raise HTTPException(413, detail="Each product image must be at most 2 MiB.")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(422, detail="Invalid image encoding.") from exc
    with validated_image(data, content_type, MAX_PRODUCT_IMAGE_BYTES):
        pass
    return data, content_type


def prepare_product_images(images: List[str], product_id: str, existing: Dict[str, Any]) -> Dict[str, Any]:
    stored = {image_url(product_id, image["id"]): image for image in existing.get("image_data", [])}
    references = []
    binaries = {}
    for value in images:
        if value.startswith("data:"):
            data, content_type = decode_product_image(value)
            image_id = uuid4().hex
            reference = image_url(product_id, image_id)
            binaries[image_id] = {"id": image_id, "content_type": content_type, "data": Binary(data)}
        elif value in stored:
            reference = value
            binaries[stored[value]["id"]] = stored[value]
        elif value.startswith(("assets/", "/assets/", "https://", "http://")):
            reference = value
        else:
            raise HTTPException(422, detail="Invalid product image reference. Reload the product and try again.")
        references.append(reference)
    return {"images": references, "image_data": list(binaries.values())}


def validate_product_document(document: Dict[str, Any]) -> None:
    if len(BSON.encode(document)) > MAX_PRODUCT_DOCUMENT_BYTES:
        raise HTTPException(413, detail="Product data and images exceed MongoDB's 16 MiB document limit.")
