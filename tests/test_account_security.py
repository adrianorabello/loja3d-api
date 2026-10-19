import re
import pytest
from httpx import AsyncClient
from app.core.phone import normalize_phone
from app.core.security import hash_password, verify_password
from app.database import db_manager
from app.services import email as email_service

BASE = "/api/v1/auth"


def last_token(path_hint: str) -> str:
    for msg in reversed(email_service.outbox):
        m = re.search(r"(?i)token=([\w\-]+)", msg["body"]) if path_hint in msg["body"] else None
        if m:
            return m.group(1)
    raise AssertionError("e-mail not found")


async def signup(client, **over):
    body = {"name": "Ana Teste", "email": "ana@example.pt", "password": "senha-segura-1"}
    body.update(over)
    return await client.post(f"{BASE}/sign-up", json=body)


@pytest.mark.asyncio
async def test_signup_forces_customer_and_stores_argon2(client: AsyncClient):
    res = await signup(client, role="ADMIN", emailVerified=True, confirmPassword="senha-segura-1")
    assert res.status_code == 201
    user = res.json()["user"]
    assert user["role"] == "CUSTOMER" and user["emailVerified"] is False
    doc = await db_manager.db.users.find_one({"email": "ana@example.pt"})
    assert doc["password_hash"].startswith("$argon2id$")
    assert "confirmPassword" not in doc


@pytest.mark.asyncio
async def test_signup_validation(client: AsyncClient):
    assert (await signup(client, password="curta")).status_code == 422
    assert (await signup(client, confirmPassword="outra-senha-1")).status_code == 422
    assert (await signup(client, dateOfBirth="2999-01-01")).status_code == 422
    assert (await signup(client, phone="123")).status_code == 422
    ok = await signup(client, phone="+351 912 345 678", dateOfBirth="2015-05-01")
    assert ok.status_code == 201
    assert ok.json()["user"]["phone"] == "+351912345678"
    assert ok.json()["user"]["phoneCountry"] == "PT"


def test_phone_regions():
    for raw, country, e164 in [
        ("+44 7400 123456", None, "+447400123456"),
        ("+1 202 555 0143", None, "+12025550143"),
        ("11 91234-5678", "BR", "+5511912345678"),
        ("+52 55 1234 5678", None, "+525512345678"),
    ]:
        assert normalize_phone(raw, country)[0] == e164
    with pytest.raises(ValueError):
        normalize_phone("12345", "PT")


def test_legacy_bcrypt_still_verifies():
    import bcrypt
    legacy = bcrypt.hashpw(b"antiga", bcrypt.gensalt(4)).decode()
    assert verify_password("antiga", legacy)
    assert not verify_password("errada", legacy)
    assert verify_password("nova", hash_password("nova"))


@pytest.mark.asyncio
async def test_verify_email_single_use(client: AsyncClient):
    await signup(client)
    token = last_token("confirmation-required")
    assert (await client.post(f"{BASE}/verify-email", json={"token": token})).status_code == 200
    doc = await db_manager.db.users.find_one({"email": "ana@example.pt"})
    assert doc["email_verified"] is True
    assert (await client.post(f"{BASE}/verify-email", json={"token": token})).status_code == 400
    assert (await client.post(f"{BASE}/verify-email", json={"token": "x" * 30})).status_code == 400


@pytest.mark.asyncio
async def test_forgot_and_reset_password(client: AsyncClient):
    signed = (await signup(client)).json()
    # Same answer for existing and unknown accounts
    a = await client.post(f"{BASE}/forgot-password", json={"email": "ana@example.pt"})
    b = await client.post(f"{BASE}/forgot-password", json={"email": "nao@example.pt"})
    assert a.status_code == b.status_code == 200 and a.json() == b.json()
    token = last_token("reset-password")
    stored = await db_manager.db.auth_tokens.find_one({"purpose": "reset_password"})
    assert stored["token_hash"] != token  # only the hash is stored

    assert (await client.post(f"{BASE}/reset-password", json={"token": token, "password": "nova-senha-123"})).status_code == 200
    assert (await client.post(f"{BASE}/reset-password", json={"token": token, "password": "outra-senha-123"})).status_code == 400
    assert (await client.post(f"{BASE}/sign-in", json={"email": "ana@example.pt", "password": "senha-segura-1"})).status_code == 401
    assert (await client.post(f"{BASE}/sign-in", json={"email": "ana@example.pt", "password": "nova-senha-123"})).status_code == 200
    # Old refresh token revoked by the reset
    refresh = await client.post(f"{BASE}/refresh", json={"refresh_token": signed["refresh_token"]})
    assert refresh.status_code == 401


@pytest.mark.asyncio
async def test_expired_token_rejected(client: AsyncClient):
    await signup(client)
    await client.post(f"{BASE}/forgot-password", json={"email": "ana@example.pt"})
    token = last_token("reset-password")
    from datetime import datetime, timedelta, timezone
    await db_manager.db.auth_tokens.update_many({}, {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(minutes=1)}})
    res = await client.post(f"{BASE}/reset-password", json={"token": token, "password": "nova-senha-123"})
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_logout_revokes_refresh_and_me(client: AsyncClient):
    data = (await signup(client)).json()
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    assert (await client.get(f"{BASE}/me", headers=headers)).json()["email"] == "ana@example.pt"
    assert (await client.get(f"{BASE}/me")).status_code == 401
    assert (await client.post(f"{BASE}/logout", json={"refresh_token": data["refresh_token"]})).status_code == 200
    assert (await client.post(f"{BASE}/refresh", json={"refresh_token": data["refresh_token"]})).status_code == 401


@pytest.mark.asyncio
async def test_patch_me_whitelist_and_email_change(client: AsyncClient):
    data = (await signup(client)).json()
    h = {"Authorization": f"Bearer {data['access_token']}"}
    res = await client.patch("/api/v1/users/me", headers=h, json={
        "name": "Ana Nova", "role": "ADMIN", "emailVerified": True, "status": "x", "phone": "+351912345678"})
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "Ana Nova" and body["role"] == "CUSTOMER" and body["emailVerified"] is False
    assert body["phone"] == "+351912345678"
    assert (await client.patch("/api/v1/users/me", headers=h, json={"phone": "12"})).status_code == 422
    assert (await client.patch("/api/v1/users/me", headers=h, json={"email": "outro@example.pt"})).status_code == 400

    wrong = await client.post("/api/v1/users/me/email-change", headers=h, json={"newEmail": "outro@example.pt", "password": "errada-errada"})
    assert wrong.status_code == 403
    ok = await client.post("/api/v1/users/me/email-change", headers=h, json={"newEmail": "outro@example.pt", "password": "senha-segura-1"})
    assert ok.status_code == 200
    token = last_token("emailChangeToken")
    assert (await client.post("/api/v1/users/me/email-change/confirm", headers=h, json={"token": token})).status_code == 200
    assert (await client.get(f"{BASE}/me", headers=h)).json()["email"] == "outro@example.pt"


@pytest.mark.asyncio
async def test_rate_limit_sign_in(client: AsyncClient):
    codes = [(await client.post(f"{BASE}/sign-in", json={"email": "x@example.pt", "password": "errada-12"})).status_code for _ in range(12)]
    assert codes[0] == 401 and codes[-1] == 429
