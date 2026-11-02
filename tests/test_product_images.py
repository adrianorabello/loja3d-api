import base64
from io import BytesIO
from unittest.mock import AsyncMock

from bson import BSON, Binary
from fastapi import HTTPException
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from pymongo.errors import OperationFailure
import pytest

from app.database import db_manager
from app.services.product_images import MAX_PRODUCT_IMAGE_BYTES, validate_product_document


def picture(size=(32, 24), color="red", target_bytes=None):
    image = Image.new("RGB", size, color)
    output = BytesIO()
    metadata = PngInfo()
    metadata.add_text("padding", "")
    image.save(output, format="PNG", pnginfo=metadata)
    if target_bytes:
        metadata = PngInfo()
        metadata.add_text("padding", "x" * (target_bytes - len(output.getvalue())))
        output = BytesIO()
        image.save(output, format="PNG", pnginfo=metadata)
    return output.getvalue()


def data_url(data):
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def product(images, slug="binary-photo"):
    return {"slug": slug, "name": {"pt-PT": "Binary photo"}, "categoryId": "test",
            "price": 10, "images": images, "active": True}


@pytest.mark.asyncio
async def test_binary_product_images_roundtrip_and_removal(client, admin_token, customer_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    original = picture()
    created = await client.post("/api/clara-rosa/product", headers=headers,
                                json={"product": product([data_url(original), "assets/test.png"])})
    assert created.status_code == 201, created.text
    result = created.json()
    url = result["images"][0]
    assert url.startswith("/api/v1/products/") and "data:" not in created.text
    stored = await db_manager.db.products.find_one({"id": result["id"]})
    assert isinstance(stored["image_data"][0]["data"], (bytes, Binary))
    assert bytes(stored["image_data"][0]["data"]) == original
    assert stored["images"] == result["images"]
    downloaded = await client.get(url)
    assert downloaded.status_code == 200 and downloaded.content == original
    assert downloaded.headers["content-type"] == "image/png"
    assert downloaded.headers["x-content-type-options"] == "nosniff"
    for endpoint in ["/api/v1/products", "/api/v1/products/binary-photo"]:
        response = await client.get(endpoint)
        assert response.status_code == 200
        assert "image_data" not in response.text and "data:image" not in response.text
    reloaded = await client.get(f"/api/v1/product/{result['id']}", headers=headers)
    assert reloaded.json()["images"] == result["images"]
    changed = await client.patch("/api/clara-rosa/product", headers=headers, json={
        "id": result["id"], "product": {"images": [data_url(picture(color="blue")), url]}})
    assert changed.status_code == 200
    new_url = changed.json()["images"][0]
    assert new_url != url
    assert (await client.get(url)).content == original
    assert (await client.get(new_url)).content == picture(color="blue")
    denied = await client.patch(f"/api/v1/admin/products/{result['id']}",
                               headers={"Authorization": f"Bearer {customer_token}"}, json={"images": []})
    assert denied.status_code == 403
    cleared = await client.patch(f"/api/v1/admin/products/{result['id']}", headers=headers, json={"images": []})
    assert cleared.status_code == 200
    assert (await client.get(url)).status_code == 404
    assert (await client.get(new_url)).status_code == 404
    assert (await db_manager.db.products.find_one({"id": result["id"]}))["image_data"] == []


@pytest.mark.asyncio
async def test_exact_size_limit_and_atomic_invalid_update(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    data = picture(target_bytes=MAX_PRODUCT_IMAGE_BYTES)
    assert len(data) == 2 * 1024 * 1024
    created = await client.post("/api/v1/admin/products", headers=headers, json=product([data_url(data)]))
    assert created.status_code == 201, created.text
    result = created.json()
    invalid_cases = [
        (data_url(b"not an image"), 422),
        (data_url(data + b"x"), 413),
        ("data:image/svg+xml;base64,PHN2Zy8+", 415),
        ("data:image/png;base64,invalid!", 422),
        (data_url(picture(size=(4001, 4000))), 422),
        ("/api/v1/products/another/images/missing", 422),
    ]
    for value, code in invalid_cases:
        response = await client.patch(f"/api/v1/admin/products/{result['id']}", headers=headers,
                                      json={"images": [value], "name": {"pt-PT": "Should not persist"}})
        assert response.status_code == code, response.text
        saved = await client.get(f"/api/v1/admin/products/{result['id']}", headers=headers)
        assert saved.json()["images"] == result["images"]
        assert saved.json()["name"] == result["name"]
    assert (await client.get(result["images"][0])).content == data
    deleted = await client.delete(f"/api/v1/admin/products/{result['id']}", headers=headers)
    assert deleted.status_code == 204
    assert (await client.get(result["images"][0])).status_code == 404


@pytest.mark.asyncio
async def test_existing_base64_converts_on_save_and_urls_are_preserved(client, admin_token):
    images = [data_url(picture()), "assets/old.jpg", "https://example.com/image.jpg"]
    await db_manager.db.products.insert_one({**product(images, "old"), "id": "legacy"})
    response = await client.patch("/api/v1/admin/products/legacy",
                                  headers={"Authorization": f"Bearer {admin_token}"},
                                  json={"featured": True})
    assert response.status_code == 200
    assert response.json()["images"][1:] == images[1:]
    assert (await client.get(response.json()["images"][0])).content == picture()


def test_document_size_limit():
    document = {"value": b""}
    overhead = len(BSON.encode(document))
    document["value"] = b"x" * (16 * 1024 * 1024 - overhead)
    validate_product_document(document)
    document["value"] += b"x"
    with pytest.raises(HTTPException) as error:
        validate_product_document(document)
    assert error.value.status_code == 413


@pytest.mark.asyncio
async def test_failed_write_preserves_previous_binary(client, admin_token, monkeypatch):
    headers = {"Authorization": f"Bearer {admin_token}"}
    created = await client.post("/api/v1/admin/products", headers=headers, json=product([data_url(picture())]))
    result = created.json()
    monkeypatch.setattr(type(db_manager.db.products), "update_one", AsyncMock(side_effect=OperationFailure("test")))
    failed = await client.patch(f"/api/v1/admin/products/{result['id']}", headers=headers,
                                json={"images": [data_url(picture(color="blue"))]})
    assert failed.status_code == 503
    assert (await client.get(result["images"][0])).content == picture()
