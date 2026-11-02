import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId
from httpx import AsyncClient

from app.database import db_manager


BASE_PATH = "/api/v1/print-requests"


@pytest.mark.asyncio
async def test_admin_navigation_includes_print_requests(client: AsyncClient):
    response = await client.get("/api/common/navigation")
    assert response.status_code == 200
    navigation = response.json()["default"]
    request_entry = next(item for item in navigation if item.get("id") == "admin.print-requests")
    assert request_entry["link"] == "/admin/requests"
    assert request_entry["meta"]["roles"] == ["ADMIN"]


def request_payload(title="Peça personalizada"):
    return {
        "title": title,
        "description": "Pretendo uma peça personalizada para oferecer.",
        "quantity": 2,
        "dimensions": "10 x 5 x 3 cm",
        "material": "PLA",
        "color": "Azul",
        "referenceLinks": ["https://example.com/reference"],
    }


def auth(token):
    return {"Authorization": f"Bearer {token}"}


async def create_request(client, token, title="Peça personalizada"):
    response = await client.post(BASE_PATH, headers=auth(token), json=request_payload(title))
    assert response.status_code == 201, response.text
    return response.json()


async def move_admin(client, token, request, next_status, message="Atualização da equipa.", **extra):
    response = await client.post(
        f"/api/v1/admin/print-requests/{request['id']}/transition",
        headers=auth(token),
        json={
            "version": request["version"],
            "status": next_status,
            "message": message,
            **extra,
        },
    )
    return response


@pytest.mark.asyncio
async def test_create_ownership_and_admin_authorization(client: AsyncClient, customer_token: str, admin_token: str):
    created = await create_request(client, customer_token)
    assert created["reference"].startswith("CR-")
    assert created["status"] == "submitted"
    assert created["version"] == 1
    assert created["ownerId"]
    assert created["history"][0]["kind"] == "request_submitted"
    assert created["referenceLinks"] == ["https://example.com/reference"]

    second_customer = await client.post("/api/v1/auth/sign-up", json={
        "name": "Outro Cliente",
        "email": "outro.cliente@example.pt",
        "password": "password123",
    })
    assert second_customer.status_code == 201
    other_token = second_customer.json()["access_token"]

    assert (await client.get(BASE_PATH, headers=auth(other_token))).json()["total"] == 0
    assert (await client.get(
        f"{BASE_PATH}/{created['id']}", headers=auth(other_token)
    )).status_code == 404
    assert (await client.post(
        f"{BASE_PATH}/{created['id']}/messages",
        headers=auth(other_token),
        json={"version": 1, "message": "Não autorizado."},
    )).status_code == 404

    assert (await client.get(
        "/api/v1/admin/print-requests", headers=auth(customer_token)
    )).status_code == 403
    assert (await client.post(
        BASE_PATH, headers=auth(admin_token), json=request_payload()
    )).status_code == 403
    assert (await client.get(
        BASE_PATH, headers=auth(admin_token)
    )).json()["total"] == 0
    assert (await client.get(
        f"/api/v1/admin/print-requests/{created['id']}", headers=auth(admin_token)
    )).status_code == 200


@pytest.mark.asyncio
async def test_create_validation_and_server_pagination_search(client: AsyncClient, customer_token: str, admin_token: str):
    invalid = request_payload()
    invalid["quantity"] = 0
    assert (await client.post(BASE_PATH, headers=auth(customer_token), json=invalid)).status_code == 422
    invalid = request_payload()
    invalid["referenceLinks"] = ["file:///private/file.stl"]
    assert (await client.post(BASE_PATH, headers=auth(customer_token), json=invalid)).status_code == 422
    invalid = request_payload()
    invalid["referenceLinks"] = ["https://example.com"] * 6
    assert (await client.post(BASE_PATH, headers=auth(customer_token), json=invalid)).status_code == 422
    invalid = request_payload()
    invalid["referenceLinks"] = ["https://user:password@example.com/reference"]
    assert (await client.post(BASE_PATH, headers=auth(customer_token), json=invalid)).status_code == 422
    invalid = request_payload()
    invalid["title"] = "ab"
    assert (await client.post(BASE_PATH, headers=auth(customer_token), json=invalid)).status_code == 422

    await create_request(client, customer_token, "Vaso azul")
    await create_request(client, customer_token, "Suporte de livros")
    await create_request(client, customer_token, "Vaso vermelho")

    first_page = await client.get(
        "/api/v1/admin/print-requests?page=1&pageSize=2&sort=oldest",
        headers=auth(admin_token),
    )
    assert first_page.status_code == 200
    assert len(first_page.json()["items"]) == 2
    assert first_page.json()["total"] == 3
    assert first_page.json()["page"] == 1
    second_page = await client.get(
        "/api/v1/admin/print-requests?page=2&pageSize=2&sort=oldest",
        headers=auth(admin_token),
    )
    assert len(second_page.json()["items"]) == 1

    matching = await client.get(
        "/api/v1/admin/print-requests?q=vermelho",
        headers=auth(admin_token),
    )
    assert matching.json()["total"] == 1
    assert matching.json()["items"][0]["title"] == "Vaso vermelho"


@pytest.mark.asyncio
async def test_quote_versions_expiry_and_optimistic_updates(
    client: AsyncClient, customer_token: str, admin_token: str
):
    request = await create_request(client, customer_token)
    request = (await move_admin(
        client, admin_token, request, "under_review"
    )).json()
    quote_payload = {
        "version": request["version"],
        "amountCents": 1250,
        "currency": "EUR",
        "scope": "Impressão em PLA azul",
        "leadDays": 7,
        "validUntil": (datetime.now(timezone.utc) + timedelta(days=10)).isoformat(),
    }
    published = await client.post(
        f"/api/v1/admin/print-requests/{request['id']}/quote",
        headers=auth(admin_token),
        json=quote_payload,
    )
    assert published.status_code == 200, published.text
    request = published.json()
    assert request["status"] == "awaiting_quote_approval"
    assert request["quotes"][0]["version"] == 1

    stale = await client.post(
        f"{BASE_PATH}/{request['id']}/actions",
        headers=auth(customer_token),
        json={
            "version": request["version"] - 1,
            "action": "approve_quote",
            "quoteVersion": 1,
            "message": "Aceito.",
        },
    )
    assert stale.status_code == 409

    await db_manager.db.print_requests.update_one(
        {"_id": ObjectId(request["id"])},
        {"$set": {"quotes.0.valid_until": datetime.now(timezone.utc) - timedelta(seconds=1)}},
    )
    expired = await client.post(
        f"{BASE_PATH}/{request['id']}/actions",
        headers=auth(customer_token),
        json={
            "version": request["version"],
            "action": "approve_quote",
            "quoteVersion": 1,
            "message": "Aceito.",
        },
    )
    assert expired.status_code == 409

    revision = await client.post(
        f"/api/v1/admin/print-requests/{request['id']}/quote",
        headers=auth(admin_token),
        json={
            **quote_payload,
            "version": request["version"],
            "amountCents": 1500,
            "validUntil": (datetime.now(timezone.utc) + timedelta(days=10)).isoformat(),
        },
    )
    assert revision.status_code == 200, revision.text
    revised = revision.json()
    assert [quote["version"] for quote in revised["quotes"]] == [1, 2]
    wrong_revision = await client.post(
        f"{BASE_PATH}/{request['id']}/actions",
        headers=auth(customer_token),
        json={
            "version": revised["version"],
            "action": "approve_quote",
            "quoteVersion": 1,
            "message": "Aceito.",
        },
    )
    assert wrong_revision.status_code == 409

    approved = await client.post(
        f"{BASE_PATH}/{request['id']}/actions",
        headers=auth(customer_token),
        json={
            "version": revised["version"],
            "action": "approve_quote",
            "quoteVersion": 2,
            "message": "Aceito a versão atual.",
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "awaiting_payment"
    assert approved.json()["quotes"][1]["approvedAt"]
    assert approved.json()["version"] == revised["version"] + 1


@pytest.mark.asyncio
@pytest.mark.parametrize("tracking", [{}, {"trackingUrl": None}, {"trackingUrl": ""}, {"trackingUrl": "   "}, {"trackingUrl": "https://tracking.example/abc"}])
async def test_information_reply_payment_shipping_and_delivery(
    client: AsyncClient, customer_token: str, admin_token: str, tracking
):
    request = await create_request(client, customer_token)
    request = (await move_admin(client, admin_token, request, "under_review")).json()
    request = (await move_admin(
        client, admin_token, request, "information_required", "Indique a utilização pretendida."
    )).json()
    reply = await client.post(
        f"{BASE_PATH}/{request['id']}/messages",
        headers=auth(customer_token),
        json={"version": request["version"], "message": "É para uso decorativo."},
    )
    assert reply.status_code == 200, reply.text
    request = reply.json()
    assert request["status"] == "under_review"
    assert request["history"][-1]["kind"] == "customer_message"

    quote = await client.post(
        f"/api/v1/admin/print-requests/{request['id']}/quote",
        headers=auth(admin_token),
        json={
            "version": request["version"],
            "amountCents": 1000,
            "currency": "EUR",
            "scope": "Impressão solicitada",
            "leadDays": 4,
            "validUntil": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
        },
    )
    request = quote.json()
    request = (await client.post(
        f"{BASE_PATH}/{request['id']}/actions",
        headers=auth(customer_token),
        json={
            "version": request["version"],
            "action": "approve_quote",
            "quoteVersion": 1,
            "message": "Aceito.",
        },
    )).json()
    request = (await move_admin(
        client, admin_token, request, "payment_confirmed", "Pagamento verificado manualmente."
    )).json()
    request = (await move_admin(
        client, admin_token, request, "in_production", "Produção iniciada."
    )).json()

    invalid_tracking = await move_admin(client, admin_token, request, "shipped", trackingUrl="not-a-url")
    assert invalid_tracking.status_code == 422
    shipped = await move_admin(
        client, admin_token, request, "shipped", "Encomenda expedida.",
        **tracking,
        estimatedShipping="2026-10-28",
    )
    assert shipped.status_code == 200, shipped.text
    request = shipped.json()
    if (tracking.get("trackingUrl") or "").strip():
        assert request["trackingUrl"] == "https://tracking.example/abc"
    else:
        assert "trackingUrl" not in request
    persisted = await client.get(f"{BASE_PATH}/{request['id']}", headers=auth(customer_token))
    assert persisted.status_code == 200
    assert persisted.json().get("trackingUrl") == request.get("trackingUrl")
    assert request["estimatedShipping"] == "2026-10-28"

    delivered = await move_admin(client, admin_token, request, "delivered", "Entrega concluída.")
    assert delivered.status_code == 200
    assert delivered.json()["status"] == "delivered"
    assert delivered.json()["history"][-1]["message"] == "Entrega concluída."


@pytest.mark.asyncio
async def test_customer_cancellation_in_payment_verification_and_stale_message(
    client: AsyncClient, customer_token: str, admin_token: str
):
    request = await create_request(client, customer_token)
    request = (await move_admin(client, admin_token, request, "under_review")).json()
    request = (await move_admin(client, admin_token, request, "information_required")).json()
    reply = await client.post(
        f"{BASE_PATH}/{request['id']}/messages",
        headers=auth(customer_token),
        json={"version": request["version"], "message": "Resposta."},
    )
    request = reply.json()
    stale_message = await client.post(
        f"{BASE_PATH}/{request['id']}/messages",
        headers=auth(customer_token),
        json={"version": request["version"] - 1, "message": "Stale."},
    )
    assert stale_message.status_code == 409

    quote = await client.post(
        f"/api/v1/admin/print-requests/{request['id']}/quote",
        headers=auth(admin_token),
        json={
            "version": request["version"],
            "amountCents": 1000,
            "currency": "EUR",
            "scope": "Impressão",
            "leadDays": 3,
            "validUntil": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
        },
    )
    request = quote.json()
    request = (await client.post(
        f"{BASE_PATH}/{request['id']}/actions",
        headers=auth(customer_token),
        json={
            "version": request["version"],
            "action": "approve_quote",
            "quoteVersion": 1,
            "message": "Aceito.",
        },
    )).json()
    request = (await move_admin(client, admin_token, request, "payment_verification")).json()
    cancelled = await client.post(
        f"{BASE_PATH}/{request['id']}/actions",
        headers=auth(customer_token),
        json={
            "version": request["version"],
            "action": "cancel",
            "message": "Já não pretendo continuar.",
        },
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["history"][-1]["actorRole"] == "customer"


@pytest.mark.asyncio
async def test_empty_approval_message_utc_quotes_and_optional_fields(
    client: AsyncClient, customer_token: str, admin_token: str
):
    response = await client.post(BASE_PATH, headers=auth(customer_token), json={
        "title": "Peça sem preferências",
        "description": "Objeto decorativo sem preferências de material.",
        "quantity": 1,
        "dimensions": "20 mm",
        "referenceLinks": [],
    })
    assert response.status_code == 201, response.text
    request = response.json()
    for optional in ("material", "color", "trackingUrl", "estimatedShipping"):
        assert optional not in request
    assert request["allowedTransitions"] == []
    assert request["allowedActions"] == ["message", "cancel"]
    request = (await move_admin(client, admin_token, request, "under_review")).json()
    response = await client.post(
        f"/api/v1/admin/print-requests/{request['id']}/quote",
        headers=auth(admin_token),
        json={
            "version": request["version"], "amountCents": 1000, "currency": "EUR",
            "scope": "Peça decorativa", "leadDays": 365,
            "validUntil": (datetime.now(timezone(timedelta(hours=2))) + timedelta(days=5)).isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    request = response.json()
    assert "approvedAt" not in request["quotes"][-1]
    assert request["quotes"][-1]["validUntil"].endswith("Z")
    assert request["quotes"][-1]["createdAt"].endswith("Z")
    response = await client.post(
        f"{BASE_PATH}/{request['id']}/actions",
        headers=auth(customer_token),
        json={"version": request["version"], "action": "approve_quote", "quoteVersion": 1, "message": ""},
    )
    assert response.status_code == 200, response.text
    assert response.json()["quotes"][-1]["approvedAt"].endswith("Z")
    assert response.json()["history"][-1]["message"]


@pytest.mark.asyncio
async def test_quote_limits_and_required_reasons(client, customer_token, admin_token):
    request = await create_request(client, customer_token)
    request = (await move_admin(client, admin_token, request, "under_review")).json()
    quote = {
        "version": request["version"], "amountCents": 1000, "currency": "EUR",
        "scope": "Peça decorativa", "leadDays": 366,
        "validUntil": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
    }
    response = await client.post(
        f"/api/v1/admin/print-requests/{request['id']}/quote", headers=auth(admin_token), json=quote
    )
    assert response.status_code == 422
    response = await client.post(
        f"/api/v1/admin/print-requests/{request['id']}/quote", headers=auth(admin_token),
        json={**quote, "leadDays": 5, "validUntil": "2030-01-01T00:00:00"},
    )
    assert response.status_code == 422
    for action in ("cancel", "request_changes"):
        response = await client.post(
            f"{BASE_PATH}/{request['id']}/actions", headers=auth(customer_token),
            json={"version": request["version"], "action": action, "message": ""},
        )
        assert response.status_code == 422
    for token, path in (
        (customer_token, f"{BASE_PATH}/{request['id']}/messages"),
        (admin_token, f"/api/v1/admin/print-requests/{request['id']}/messages"),
    ):
        assert (await client.post(
            path, headers=auth(token), json={"version": request["version"], "message": ""}
        )).status_code == 422
    assert (await move_admin(client, admin_token, request, "cancelled", "")).status_code == 422


@pytest.mark.asyncio
async def test_concurrent_messages_are_atomic_and_persist_in_mongo(client, customer_token):
    request = await create_request(client, customer_token)
    responses = await asyncio.gather(*(
        client.post(
            f"{BASE_PATH}/{request['id']}/messages", headers=auth(customer_token),
            json={"version": request["version"], "message": f"Mensagem concorrente {number}."},
        ) for number in range(2)
    ))
    assert sorted(response.status_code for response in responses) == [200, 409]
    persisted = await db_manager.db.print_requests.find_one({"_id": ObjectId(request["id"])})
    assert persisted["version"] == 2
    assert len(persisted["history"]) == 2
    assert persisted["history"][-1]["kind"] == "customer_message"
    assert persisted["history"][-1]["message"].startswith("Mensagem concorrente")
    retrieved = await client.get(f"{BASE_PATH}/{request['id']}", headers=auth(customer_token))
    assert retrieved.json()["version"] == persisted["version"]
    indexes = await db_manager.db.print_requests.index_information()
    assert indexes["idx_print_requests_reference_unique"]["unique"] is True
    assert "idx_print_requests_owner_created" in indexes
    assert "idx_print_requests_status_created" in indexes


@pytest.mark.asyncio
@pytest.mark.parametrize("approval_message", [{}, {"message": ""}, {"message": "   "}])
async def test_expired_quote_actions_and_approval_without_message(
    client, customer_token, admin_token, approval_message
):
    request = await create_request(client, customer_token)
    request = (await move_admin(client, admin_token, request, "under_review")).json()
    payload = {
        "version": request["version"], "amountCents": 1000, "currency": "EUR",
        "scope": "Impressão em PLA", "leadDays": 7,
        "validUntil": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
    }
    quote_response = await client.post(
        f"/api/v1/admin/print-requests/{request['id']}/quote", headers=auth(admin_token), json=payload
    )
    assert quote_response.status_code == 200
    request = quote_response.json()
    await db_manager.db.print_requests.update_one(
        {"_id": ObjectId(request["id"])},
        {"$set": {"quotes.0.valid_until": datetime.now(timezone.utc) - timedelta(days=1)}},
    )
    expired = (await client.get(f"{BASE_PATH}/{request['id']}", headers=auth(customer_token))).json()
    assert "approve_quote" not in expired["allowedActions"]
    assert "request_changes" in expired["allowedActions"]
    revision = await client.post(
        f"/api/v1/admin/print-requests/{request['id']}/quote",
        headers=auth(admin_token), json={**payload, "version": request["version"]},
    )
    assert revision.status_code == 200
    request = revision.json()
    approval = await client.post(
        f"{BASE_PATH}/{request['id']}/actions", headers=auth(customer_token),
        json={
            "version": request["version"], "action": "approve_quote", "quoteVersion": 2,
            **approval_message,
        },
    )
    assert approval.status_code == 200, approval.text
    request = approval.json()
    assert request["history"][-1]["message"] == "Quotation version 2 approved."
    request = (await move_admin(client, admin_token, request, "payment_confirmed", "Verificado manualmente.")).json()
    customer_view = (await client.get(f"{BASE_PATH}/{request['id']}", headers=auth(customer_token))).json()
    assert customer_view["allowedActions"] == ["message"]
    assert (await client.post(
        f"{BASE_PATH}/{request['id']}/actions", headers=auth(customer_token),
        json={"version": request["version"], "action": "cancel", "message": "Não permitido."},
    )).status_code == 409
    assert (await move_admin(client, admin_token, request, "rejected", "Não permitido.")).status_code == 409
    cancelled = await move_admin(client, admin_token, request, "cancelled", "Cancelamento após pagamento; tratar reembolso fora da API.")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["allowedActions"] == []
    assert cancelled.json()["allowedTransitions"] == []
    assert cancelled.json()["quotes"][-1]["approvedAt"]


@pytest.mark.asyncio
async def test_search_literal_regex_and_invalid_pagination(client, customer_token, admin_token):
    await create_request(client, customer_token, "Peça [especial]")
    for query in ("[especial]", "a" * 99 + "[", ".*"):
        response = await client.get(
            "/api/v1/admin/print-requests", headers=auth(admin_token), params={"q": query}
        )
        assert response.status_code == 200, response.text
        assert response.json()["total"] == (1 if query == "[especial]" else 0)
    for params in ({"page": 0}, {"pageSize": 101}, {"sort": "invalid"}, {"status": "paid"}):
        assert (await client.get(BASE_PATH, headers=auth(customer_token), params=params)).status_code == 422
