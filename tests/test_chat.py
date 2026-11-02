import asyncio
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
from contextlib import asynccontextmanager
from io import BytesIO
from uuid import uuid4
from zipfile import ZipFile

import pytest
from bson import ObjectId
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient, ConnectError
from motor.motor_asyncio import AsyncIOMotorClient
from PIL import Image
from pypdf import PdfWriter
import websockets

from app.config import settings
from app.core.security import create_access_token
from app.database import get_database
from app.routers import chat as chat_router
from app.services.chat import init_chat
from app.services.chat_attachments import validate_file
from app.services.chat_realtime import redis_client
from app.workers.chat import cleanup, tick
from main import app


@pytest.fixture
async def chat_env(monkeypatch):
    mongo = AsyncIOMotorClient("mongodb://127.0.0.1:27018/?directConnection=true&replicaSet=chat-rs")
    name = "clara_rosa_chat_test_" + uuid4().hex
    db = mongo[name]
    monkeypatch.setattr(settings, "CHAT_ENABLED", True)
    monkeypatch.setattr(settings, "CHAT_REDIS_URL", "redis://127.0.0.1:6380/15")
    monkeypatch.setattr(settings, "CHAT_WS_ORIGINS", ["http://localhost:4201"])
    await init_chat(db)
    users = {}
    for role, key in [("CUSTOMER", "a"), ("CUSTOMER", "b"), ("ADMIN", "admin")]:
        uid = ObjectId()
        await db.users.insert_one({"_id": uid, "name": key, "role": role, "is_active": True})
        token = create_access_token(str(uid), role, key + "@example.pt")
        users[key] = {"Authorization": "Bearer " + token, "Origin": "http://localhost:4201"}

    async def override():
        return db

    app.dependency_overrides[get_database] = override
    monkeypatch.setattr(chat_router, "get_database", override)
    async with redis_client() as redis:
        # Dedicated Redis DB 15 is reserved for these isolated chat tests.
        await redis.flushdb()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, db, users
    finally:
        app.dependency_overrides.pop(get_database, None)
        await mongo.drop_database(name)
        mongo.close()


async def create(client, headers):
    response = await client.post("/api/v1/chat/conversations", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["id"]


@pytest.mark.asyncio
async def test_chat_authorization_idempotency_and_read(chat_env):
    client, db, users = chat_env
    cid = await create(client, users["a"])
    assert await create(client, users["a"]) == cid
    base = f"/api/v1/chat/conversations/{cid}"
    assert (await client.get(base, headers=users["b"])).status_code == 404
    assert (await client.get(base)).status_code == 401
    assert (await client.post("/api/v1/chat/conversations", headers=users["admin"])).status_code == 403
    body = {"clientMessageId": str(uuid4()), "text": "  <b>Hello</b>  "}
    first, duplicate = await asyncio.gather(*[
        client.post(base + "/messages", headers=users["a"], json=body) for _ in range(2)
    ])
    assert first.status_code == duplicate.status_code == 200, (first.text, duplicate.text)
    assert first.json()["id"] == duplicate.json()["id"]
    assert first.json()["text"] == "<b>Hello</b>"
    assert await db.chat_messages.count_documents({}) == 1
    changed = await client.post(base + "/messages", headers=users["a"], json={**body, "text": "different"})
    assert changed.status_code == 409
    forged = await client.post(base + "/messages", headers=users["a"], json={**body, "senderId": "admin"})
    assert forged.status_code == 422
    reply = await client.post(base + "/messages", headers=users["admin"], json={
        "clientMessageId": str(uuid4()), "text": "Reply"
    })
    assert reply.json()["seq"] == 2
    state = (await client.get(base, headers=users["a"])).json()
    assert state["unread"] == 1
    for seq in [2, 1]:
        read = await client.put(base + "/read", headers=users["a"], json={"lastReadSeq": seq})
        assert read.json()["lastReadSeq"] == 2
    assert (await client.put(base + "/read", headers=users["a"], json={"lastReadSeq": 3})).status_code == 422
    assert (await client.get(base + "/messages", headers=users["b"])).status_code == 404
    assert (await client.get(base + "/messages?afterSeq=0&beforeSeq=3", headers=users["a"])).status_code == 422
    page = (await client.get(base + "/messages?limit=1", headers=users["a"])).json()
    assert page["hasMore"] and page["items"][0]["seq"] == 2
    older = (await client.get(base + "/messages?beforeSeq=2", headers=users["a"])).json()
    assert [item["seq"] for item in older["items"]] == [1]
    assert (await client.get(base + "/messages?afterSeq=1", headers=users["a"])).json()["items"][0]["seq"] == 2


def png():
    buffer = BytesIO()
    Image.new("RGB", (10, 10), "red").save(buffer, "PNG")
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_private_attachment_scan_bind_download_cleanup(chat_env):
    client, db, users = chat_env
    cid = await create(client, users["a"])
    base = f"/api/v1/chat/conversations/{cid}"
    uploaded = await client.post(base + "/attachments", headers=users["a"], files={"file": ("photo.png", png(), "image/png")})
    assert uploaded.status_code == 200, uploaded.text
    aid = uploaded.json()["id"]
    path = base + "/attachments/" + aid
    assert uploaded.json()["status"] == "quarantined"
    assert (await client.get(path + "/content", headers=users["a"])).status_code == 409
    assert (await client.get(path, headers=users["admin"])).status_code == 404
    assert (await client.get(path, headers=users["b"])).status_code == 404
    async with redis_client() as redis:
        await tick(db, redis)  # Actual private ClamAV service, not a clean-file mock.
    ready = (await client.get(path, headers=users["a"])).json()
    assert ready["status"] == "ready", ready
    sent = await client.post(base + "/messages", headers=users["a"], json={
        "clientMessageId": str(uuid4()), "attachmentIds": [aid]
    })
    assert sent.status_code == 200, sent.text
    result = await client.get(path + "/content", headers=users["admin"])
    assert result.status_code == 200
    assert result.headers["cache-control"] == "private, no-store"
    assert result.content.startswith(b"\xff\xd8")
    assert (await client.delete(path, headers=users["a"])).status_code == 409
    assert (await client.get(path + "/content", headers=users["b"])).status_code == 404
    assert (await client.post(base + "/attachments", headers=users["a"], files={
        "file": ("big.png", b"x" * (10 * 1024 * 1024 + 1), "image/png")
    })).status_code == 413
    pending = await client.post(base + "/attachments", headers=users["a"], files={"file": ("bad.png", b"invalid", "image/png")})
    bad_id = pending.json()["id"]
    async with redis_client() as redis:
        await tick(db, redis)
    assert (await client.get(base + "/attachments/" + bad_id, headers=users["a"])).json()["status"] == "rejected"
    await client.delete(base + "/attachments/" + bad_id, headers=users["a"])
    await cleanup(db)
    assert await db.chat_attachments.count_documents({"_id": bad_id}) == 0
    assert await db["chat_files.files"].count_documents({}) == 1
    assert await db["chat_files.chunks"].count_documents({}) == 1


def test_document_validation():
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    pdf = BytesIO()
    writer.write(pdf)
    assert validate_file(pdf.getvalue(), "test.pdf", "application/pdf")[1] == "application/pdf"
    stl = b" " * 80 + struct.pack("<I", 1) + struct.pack("<12fH", *([0.0] * 12), 0)
    assert validate_file(stl, "test.stl", "application/octet-stream")[1] == "model/stl"
    archive = BytesIO()
    with ZipFile(archive, "w") as file:
        file.writestr("3D/3dmodel.model", '<model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"/>')
    assert validate_file(archive.getvalue(), "test.3mf", "model/3mf")[1] == "model/3mf"
    for name, mime, content in [
        ("bad.pdf", "application/pdf", b"%PDF-bad"),
        ("bad.stl", "model/stl", b"solid fake"),
        ("bad.png", "image/png", b"not png"),
        ("bad.zip", "application/zip", b"not zip"),
        ("photo.png", "application/pdf", png()),
    ]:
        with pytest.raises(HTTPException):
            validate_file(content, name, mime)
    bad = BytesIO()
    with ZipFile(bad, "w") as file:
        file.writestr("../bad.model", "<model/>")
    with pytest.raises(HTTPException):
        validate_file(bad.getvalue(), "test.3mf", "model/3mf")


@pytest.mark.asyncio
async def test_ws_ticket_single_use(chat_env):
    client, db, users = chat_env
    ticket_response = await client.post("/api/v1/chat/ws-ticket", headers=users["a"])
    assert ticket_response.status_code == 200
    ticket = ticket_response.json()["ticket"]
    assert ticket_response.headers["cache-control"] == "no-store"
    wrong = await client.post("/api/v1/chat/ws-ticket", headers={**users["a"], "Origin": "https://evil.example"})
    assert wrong.status_code == 403
    async with redis_client() as redis:
        from app.services.chat_realtime import consume_ticket
        assert (await consume_ticket(redis, ticket))["uid"]
        assert await consume_ticket(redis, ticket) is None


@asynccontextmanager
async def live_server(db_name):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {**os.environ,
           "MONGODB_URL": "mongodb://127.0.0.1:27018/?directConnection=true&replicaSet=chat-rs",
           "MONGODB_DB_NAME": db_name, "CHAT_ENABLED": "true",
           "CHAT_REDIS_URL": "redis://127.0.0.1:6380/15", "BOOTSTRAP_ADMIN_ENABLED": "false"}
    with tempfile.TemporaryFile() as logs:
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port),
             "--ws-max-size", "1024", "--ws-max-queue", "8"], env=env, stdout=logs, stderr=logs,
        )
        try:
            async with AsyncClient() as probe:
                for _ in range(100):
                    if proc.poll() is not None:
                        logs.seek(0)
                        raise AssertionError(logs.read().decode())
                    try:
                        result = await probe.get(f"http://127.0.0.1:{port}/health", timeout=1)
                        if result.status_code == 200:
                            break
                    except (OSError, ConnectError):
                        pass
                    await asyncio.sleep(.1)
                else:
                    raise AssertionError("Isolated chat API did not become ready.")
            yield port
        finally:
            proc.terminate()
            await asyncio.to_thread(proc.wait, 10)


@pytest.mark.asyncio
async def test_websocket_cross_process_delivery_and_isolation(chat_env):
    client, db, users = chat_env
    cid = await create(client, users["a"])
    tickets = {}
    for who in ("a", "b", "admin"):
        tickets[who] = (await client.post("/api/v1/chat/ws-ticket", headers=users[who])).json()["ticket"]
    async with live_server(db.name) as port1, live_server(db.name) as port2:
        async with websockets.connect(f"ws://127.0.0.1:{port1}/api/v1/chat/ws", origin="http://localhost:4201") as customer, \
                websockets.connect(f"ws://127.0.0.1:{port2}/api/v1/chat/ws", origin="http://localhost:4201") as admin, \
                websockets.connect(f"ws://127.0.0.1:{port2}/api/v1/chat/ws", origin="http://localhost:4201") as other:
            for ws, who in [(customer, "a"), (admin, "admin"), (other, "b")]:
                await ws.send(json.dumps({"type": "authenticate", "ticket": tickets[who]}))
                assert json.loads(await asyncio.wait_for(ws.recv(), 3))["type"] == "ready"
            sent = await client.post(f"/api/v1/chat/conversations/{cid}/messages", headers=users["a"], json={
                "clientMessageId": str(uuid4()), "text": "Across two API processes"
            })
            assert sent.status_code == 200
            async with redis_client() as redis:
                await tick(db, redis)
            for ws in (customer, admin):
                event = json.loads(await asyncio.wait_for(ws.recv(), 3))
                assert event["type"] == "message.created" and event["conversationId"] == cid
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(other.recv(), .2)
            # Reusing the consumed ticket must never authenticate a second socket.
            async with websockets.connect(f"ws://127.0.0.1:{port1}/api/v1/chat/ws", origin="http://localhost:4201") as invalid:
                await invalid.send(json.dumps({"type": "authenticate", "ticket": tickets["a"]}))
                with pytest.raises(websockets.exceptions.ConnectionClosed):
                    await invalid.recv()


@pytest.mark.asyncio
async def test_chat_flag_disabled(chat_env, monkeypatch):
    client, _, users = chat_env
    monkeypatch.setattr(settings, "CHAT_ENABLED", False)
    assert (await client.get("/api/v1/chat/conversations", headers=users["a"])).status_code == 503
