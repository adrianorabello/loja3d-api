import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_customer_signup_and_signin(client: AsyncClient):
    # 1. Sign up new customer
    signup_res = await client.post("/api/v1/auth/sign-up", json={
        "name": "Maria Silva",
        "email": "maria@clararosa.pt",
        "password": "segredo_seguro"
    })
    assert signup_res.status_code == 201
    data = signup_res.json()
    assert data["user"]["email"] == "maria@clararosa.pt"
    assert data["user"]["role"] == "CUSTOMER"
    assert "access_token" in data
    assert "refresh_token" in data

    # 2. Duplicate signup returns 409 Conflict
    dup_res = await client.post("/api/v1/auth/sign-up", json={
        "name": "Maria Outra",
        "email": "maria@clararosa.pt",
        "password": "outra_password"
    })
    assert dup_res.status_code == 409
    assert "já está registado" in dup_res.json()["detail"]

    # 3. Sign in with correct password
    signin_res = await client.post("/api/v1/auth/sign-in", json={
        "email": "maria@clararosa.pt",
        "password": "segredo_seguro"
    })
    assert signin_res.status_code == 200
    assert signin_res.json()["user"]["name"] == "Maria Silva"

    # 4. Sign in with wrong password returns 401
    wrong_pwd_res = await client.post("/api/v1/auth/sign-in", json={
        "email": "maria@clararosa.pt",
        "password": "wrong_password"
    })
    assert wrong_pwd_res.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_rotation(client: AsyncClient):
    signup_res = await client.post("/api/v1/auth/sign-up", json={
        "name": "Joao Santos",
        "email": "joao@clararosa.pt",
        "password": "password123"
    })
    assert signup_res.status_code == 201
    refresh_token = signup_res.json()["refresh_token"]

    # Refresh
    refresh_res = await client.post("/api/v1/auth/refresh", json={
        "refresh_token": refresh_token
    })
    assert refresh_res.status_code == 200
    new_data = refresh_res.json()
    assert new_data["access_token"] != signup_res.json()["access_token"]
    assert new_data["refresh_token"] != refresh_token

    # Re-using the old revoked refresh token fails
    reused_res = await client.post("/api/v1/auth/refresh", json={
        "refresh_token": refresh_token
    })
    assert reused_res.status_code == 401
