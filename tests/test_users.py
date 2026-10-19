import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_user_profile_and_addresses(client: AsyncClient, customer_token: str):
    headers = {"Authorization": f"Bearer {customer_token}"}

    # 1. Fetch own profile
    get_res = await client.get("/api/v1/users/me", headers=headers)
    assert get_res.status_code == 200
    profile = get_res.json()
    assert profile["email"] == "cliente.teste@example.pt"
    assert profile["role"] == "CUSTOMER"

    # 2. Update profile name and add address
    patch_res = await client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={
            "name": "Cliente Teste Atualizado",
            "dateOfBirth": "1995-10-20",
            "addresses": [
                {
                    "id": "addr-1",
                    "label": "Casa",
                    "street": "Avenida dos Aliados, 100",
                    "unit": "3º",
                    "postalCode": "4000-001",
                    "city": "Porto",
                    "country": "Portugal"
                }
            ]
        }
    )
    assert patch_res.status_code == 200
    updated = patch_res.json()
    assert updated["name"] == "Cliente Teste Atualizado"
    assert updated["dateOfBirth"] == "1995-10-20"
    assert len(updated["addresses"]) == 1
    assert updated["addresses"][0]["city"] == "Porto"

    # 3. Mass assignment: attempt to elevate role to ADMIN via payload is rejected/ignored
    elevate_res = await client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={"role": "ADMIN"}
    )
    # Even if accepted by Pydantic extra="ignore", role must remain CUSTOMER
    get_after = await client.get("/api/v1/users/me", headers=headers)
    assert get_after.json()["role"] == "CUSTOMER"
