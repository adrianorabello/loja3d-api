from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from pymongo.errors import OperationFailure

from app.database import db_manager
from app.services.avatar import MAX_AVATAR_BYTES, normalize_avatar


def picture(fmt="PNG", size=(800, 600)):
    output = BytesIO()
    Image.new("RGB", size, "red").save(output, format=fmt)
    return output.getvalue()


@pytest.mark.asyncio
async def test_avatar_accepts_exactly_ten_mib(client, customer_token):
    assert MAX_AVATAR_BYTES == 10 * 1024 * 1024
    metadata = PngInfo()
    metadata.add_text("padding", "")
    output = BytesIO()
    image = Image.new("RGB", (8, 8), "red")
    image.save(output, format="PNG", pnginfo=metadata)
    padding_size = MAX_AVATAR_BYTES - len(output.getvalue())
    metadata = PngInfo()
    metadata.add_text("padding", "x" * padding_size)
    output = BytesIO()
    image.save(output, format="PNG", pnginfo=metadata)
    data = output.getvalue()
    assert len(data) == 10 * 1024 * 1024
    headers = {"Authorization": f"Bearer {customer_token}"}
    uploaded = await client.post("/api/v1/users/me/avatar", headers=headers,
                                 files={"file": ("large.png", data, "image/png")})
    assert uploaded.status_code == 200, uploaded.text
    downloaded = await client.get("/" + uploaded.json()["avatar"], headers=headers)
    assert downloaded.status_code == 200
    assert len(downloaded.content) <= 512 * 1024


@pytest.mark.asyncio
async def test_avatar_persists_replaces_and_removes(client, customer_token):
    headers = {"Authorization": f"Bearer {customer_token}"}
    before = (await client.get("/api/v1/users/me", headers=headers)).json()
    upload = await client.post("/api/v1/users/me/avatar", headers=headers,
                               files={"file": ("photo.png", picture(), "image/png")})
    assert upload.status_code == 200, upload.text
    first = upload.json()
    assert first["avatarVersion"] and first["avatar"].endswith(first["avatarVersion"])
    assert "avatar_data" not in first
    download = await client.get("/" + first["avatar"], headers=headers)
    assert download.status_code == 200
    assert download.headers["cache-control"] == "private, no-store"
    with Image.open(BytesIO(download.content)) as image:
        assert image.format == "JPEG" and image.size == (512, 384)
        assert not image.getexif()
    stored = await db_manager.db.users.find_one({"email": before["email"]})
    assert bytes(stored["avatar_data"]) == download.content
    login = await client.post("/api/auth/sign-in", json={"email": before["email"], "password": "password123"})
    assert login.status_code == 200
    assert login.json()["user"]["avatar"] == first["avatar"]
    refreshed = await client.post("/api/auth/refresh-access-token", json={"access_token": login.json()["access_token"]})
    assert refreshed.status_code == 200 and refreshed.json()["user"]["avatar"] == first["avatar"]
    second = await client.post("/api/v1/users/me/avatar", headers=headers,
                              files={"file": ("new.jpg", picture("JPEG"), "image/jpeg")})
    assert second.json()["avatarVersion"] != first["avatarVersion"]
    removed = await client.delete("/api/v1/users/me/avatar", headers=headers)
    assert removed.status_code == 200 and removed.json()["avatar"] is None
    assert removed.json()["avatarVersion"] is None
    assert (await client.get("/api/v1/users/me/avatar", headers=headers)).status_code == 404
    assert (await client.get("/api/v1/users/me", headers=headers)).json()["avatar"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("data,mime,code", [
    (b"<svg></svg>", "image/svg+xml", 415),
    (b"not an image", "image/png", 422),
    (b"", "image/png", 413),
    (b"x" * (MAX_AVATAR_BYTES + 1), "image/png", 413),
    (picture(), "image/jpeg", 422),
    (picture(size=(4001, 4000)), "image/png", 422),
])
async def test_invalid_avatar_keeps_previous(client, customer_token, data, mime, code):
    headers = {"Authorization": f"Bearer {customer_token}"}
    first = await client.post("/api/v1/users/me/avatar", headers=headers,
                              files={"file": ("valid.png", picture(), "image/png")})
    rejected = await client.post("/api/v1/users/me/avatar", headers=headers,
                                 files={"file": ("bad", data, mime)})
    assert rejected.status_code == code
    assert (await client.get("/api/v1/users/me", headers=headers)).json()["avatar"] == first.json()["avatar"]


@pytest.mark.asyncio
async def test_avatar_authorization_and_profile_whitelist(client, customer_token):
    for method in ("get", "post", "delete"):
        kwargs = {"files": {"file": ("photo.png", picture(), "image/png")}} if method == "post" else {}
        assert (await getattr(client, method)("/api/v1/users/me/avatar", **kwargs)).status_code == 401
    headers = {"Authorization": f"Bearer {customer_token}"}
    other = await client.post("/api/auth/sign-up", json={
        "name": "Other Customer", "email": "other-avatar@example.com", "password": "password123"})
    upload = await client.post("/api/v1/users/me/avatar", headers=headers,
                               files={"file": ("photo.png", picture(), "image/png")})
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    assert (await client.get("/" + upload.json()["avatar"], headers=other_headers)).status_code == 404
    patched = await client.patch("/api/v1/users/me", headers=headers, json={
        "id": other.json()["user"]["id"], "role": "ADMIN", "emailVerified": True,
        "avatar": "evil", "avatar_version": "evil", "name": "  Valid Name  "})
    assert patched.status_code == 200
    assert patched.json()["name"] == "Valid Name"
    assert patched.json()["role"] == "CUSTOMER" and patched.json()["emailVerified"] is False
    assert patched.json()["avatar"] == upload.json()["avatar"]
    assert (await client.patch("/api/v1/users/me", headers=headers, json={"name": "  "})).status_code == 422
    assert (await client.get("/api/v1/users/me", headers=other_headers)).json()["name"] == "Other Customer"


@pytest.mark.asyncio
async def test_storage_failure_keeps_previous(client, customer_token, monkeypatch):
    headers = {"Authorization": f"Bearer {customer_token}"}
    first = await client.post("/api/v1/users/me/avatar", headers=headers,
                              files={"file": ("photo.png", picture(), "image/png")})
    monkeypatch.setattr(type(db_manager.db.users), "find_one_and_update", AsyncMock(side_effect=OperationFailure("test")))
    failed = await client.post("/api/v1/users/me/avatar", headers=headers,
                               files={"file": ("photo.png", picture(), "image/png")})
    assert failed.status_code == 503
    assert (await client.get("/api/v1/users/me", headers=headers)).json()["avatar"] == first.json()["avatar"]


def test_animation_rejected():
    from fastapi import HTTPException
    output = BytesIO()
    image = Image.new("RGB", (8, 8), "red")
    image.save(output, format="PNG", save_all=True, append_images=[Image.new("RGB", (8, 8), "blue")])
    with pytest.raises(HTTPException) as error:
        normalize_avatar(output.getvalue(), "image/png")
    assert error.value.status_code == 422
