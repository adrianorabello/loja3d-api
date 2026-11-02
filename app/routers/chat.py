import asyncio
import json
import logging
import time
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, StreamingResponse
from motor.motor_asyncio import AsyncIOMotorGridFSBucket
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError

from app.config import settings
from app.core.dependencies import get_current_user, security_bearer
from app.core.security import decode_access_token
from app.database import get_database
from app.models.chat import ChatMessageInput, ChatReadInput
from app.services import chat as service
from app.services.chat_attachments import store_upload
from app.services.chat_realtime import (
    claim_socket, consume_ticket, create_ticket, limit, redis_client, relay, socket_user, upload_lock,
)

logger = logging.getLogger("loja3d.chat")


async def chat_enabled():
    if not settings.CHAT_ENABLED:
        raise HTTPException(503, "Support chat is not available.")


router = APIRouter(prefix="/chat", tags=["Chat"], dependencies=[Depends(chat_enabled)])


async def redis_dependency():
    async with redis_client() as redis:
        yield redis


@router.get("/conversations")
async def conversations(
    cursor: str = Query(default="", max_length=1024), limit: int = Query(default=50, ge=1, le=100),
    q: str = Query(default="", max_length=100), user=Depends(get_current_user), db=Depends(get_database),
):
    return await service.list_conversations(db, user, cursor, limit, q)


@router.post("/conversations")
async def create_conversation(user=Depends(get_current_user), db=Depends(get_database)):
    return await service.get_or_create(db, user)


@router.get("/conversations/{cid}")
async def get_conversation(cid: str, user=Depends(get_current_user), db=Depends(get_database)):
    return await service.summary(db, await service.conversation(db, cid, user), user)


@router.get("/conversations/{cid}/messages")
async def messages(
    cid: str, beforeSeq: int = Query(default=None, ge=1), afterSeq: int = Query(default=None, ge=0),
    limit: int = Query(default=50, ge=1, le=100), user=Depends(get_current_user), db=Depends(get_database),
):
    await service.conversation(db, cid, user)
    if beforeSeq is not None and afterSeq is not None:
        raise HTTPException(422, "Use beforeSeq or afterSeq, not both.")
    query = {"conversation_id": cid}
    if beforeSeq is not None:
        query["seq"] = {"$lt": beforeSeq}
    if afterSeq is not None:
        query["seq"] = {"$gt": afterSeq}
    direction = 1 if afterSeq is not None else -1
    docs = await db.chat_messages.find(query).sort("seq", direction).limit(limit + 1).to_list(limit + 1)
    page = docs[:limit]
    return {
        "items": [service.message_output(doc) for doc in sorted(page, key=lambda x: x["seq"])],
        "hasMore": len(docs) > limit,
        "nextCursor": page[-1]["seq"] if len(docs) > limit else None,
    }


@router.post("/conversations/{cid}/messages")
async def send(
    cid: str, body: ChatMessageInput, user=Depends(get_current_user),
    db=Depends(get_database), redis=Depends(redis_dependency),
):
    await limit(redis, service.user_id(user), "send", 60)
    return await service.send_message(db, cid, user, body)


@router.put("/conversations/{cid}/read")
async def read(cid: str, body: ChatReadInput, user=Depends(get_current_user), db=Depends(get_database)):
    return await service.mark_read(db, cid, user, body.lastReadSeq)


@router.post("/conversations/{cid}/attachments")
async def upload(
    cid: str, file: UploadFile = File(...), user=Depends(get_current_user),
    db=Depends(get_database), redis=Depends(redis_dependency),
):
    await service.conversation(db, cid, user)
    uid = service.user_id(user)
    await limit(redis, uid, "upload", 30, 86400)
    async with upload_lock(redis, uid):
        doc = await store_upload(db, cid, uid, file)
    return service.attachment_output(doc)


async def attachment(db, cid, aid, user):
    await service.conversation(db, cid, user)
    doc = await db.chat_attachments.find_one({"_id": aid, "conversation_id": cid})
    if not doc or (doc["status"] != "attached" and doc["owner_id"] != service.user_id(user)):
        raise HTTPException(404, "Attachment not found.")
    return doc


@router.get("/conversations/{cid}/attachments/{aid}")
async def attachment_status(cid: str, aid: str, user=Depends(get_current_user), db=Depends(get_database)):
    return service.attachment_output(await attachment(db, cid, aid, user))


@router.delete("/conversations/{cid}/attachments/{aid}", status_code=204)
async def delete_attachment(cid: str, aid: str, user=Depends(get_current_user), db=Depends(get_database)):
    doc = await attachment(db, cid, aid, user)
    if doc["owner_id"] != service.user_id(user) or doc["status"] == "attached":
        raise HTTPException(409, "Sent attachments cannot be removed.")
    # State transition competes atomically with the send transaction and scanner.
    result = await db.chat_attachments.update_one(
        {"_id": aid, "status": {"$ne": "attached"}}, {"$set": {"status": "cancelled"}}
    )
    if not result.modified_count:
        raise HTTPException(409, "Attachment changed; refresh its state.")
    return Response(status_code=204)


@router.get("/conversations/{cid}/attachments/{aid}/content")
async def download(cid: str, aid: str, user=Depends(get_current_user), db=Depends(get_database)):
    doc = await attachment(db, cid, aid, user)
    if doc["status"] not in {"ready", "attached"}:
        raise HTTPException(409, "Attachment is still in quarantine or was rejected.")
    bucket = AsyncIOMotorGridFSBucket(db, bucket_name="chat_files")
    stream = await bucket.open_download_stream(doc["grid_id"])

    async def content():
        try:
            while True:
                chunk = await stream.readchunk()
                if not chunk:
                    break
                yield chunk
        finally:
            stream.close()

    return StreamingResponse(content(), media_type=doc["content_type"], headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        "Content-Disposition": "attachment; filename=\"attachment\"; filename*=UTF-8''" + quote(doc["name"], safe=""),
    })


@router.post("/ws-ticket")
async def ticket(request: Request, response: Response, user=Depends(get_current_user),
                 auth=Depends(security_bearer), redis=Depends(redis_dependency)):
    origin = request.headers.get("origin", "")
    if origin not in settings.CHAT_WS_ORIGINS:
        raise HTTPException(403, "WebSocket origin not allowed.")
    payload = decode_access_token(auth.credentials)
    if not payload:
        raise HTTPException(401, "Session expired.")
    response.headers["Cache-Control"] = "no-store"
    return {"ticket": await create_ticket(redis, user, payload["exp"], origin)}


@router.websocket("/ws")
async def websocket(socket: WebSocket):
    if not settings.CHAT_ENABLED or socket.headers.get("origin") not in settings.CHAT_WS_ORIGINS:
        await socket.close(code=4403)
        return
    await socket.accept()
    identity = None
    connection_id = service.identifier()
    claimed = False
    try:
        async with redis_client() as redis:
            await limit(redis, socket.client.host, "ws-handshake", 30)
        raw = await asyncio.wait_for(socket.receive_text(), 5)
        if len(raw) > 1024:
            await socket.close(code=4400)
            return
        frame = json.loads(raw)
        if not isinstance(frame, dict) or frame.get("type") != "authenticate" or not isinstance(frame.get("ticket"), str):
            await socket.close(code=4401)
            return
        async with redis_client() as redis:
            identity = await consume_ticket(redis, frame["ticket"])
        db = await get_database()
        if not identity or identity["origin"] != socket.headers.get("origin") or not await socket_user(db, identity):
            await socket.close(code=4401)
            return
        async with redis_client() as redis:
            claimed = await claim_socket(redis, identity["uid"], connection_id)
        if not claimed:
            await socket.close(code=4429)
            return

        async def receive():
            frames = 0
            start = time.monotonic()
            while True:
                data = await asyncio.wait_for(socket.receive_text(), 50)
                frames += 1
                if len(data) > 1024 or frames > 60:
                    await socket.close(code=4408)
                    return
                if time.monotonic() - start > 60:
                    frames, start = 0, time.monotonic()
                if data != '{"type":"pong"}':
                    await socket.close(code=4400)
                    return

        tasks = [asyncio.create_task(relay(socket, db, identity, connection_id)), asyncio.create_task(receive())]
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    except WebSocketDisconnect:
        logger.info("Chat socket disconnected.")
    except asyncio.TimeoutError:
        logger.info("Chat socket timed out.")
        await socket.close(code=4408)
    except HTTPException:
        await socket.close(code=4429)
    except (ValueError, KeyError, TypeError):
        await socket.close(code=4400)
    except (RedisError, PyMongoError, OSError):
        logger.exception("Chat realtime infrastructure failed.")
        await socket.close(code=1013)
    finally:
        if claimed:
            try:
                async with redis_client() as redis:
                    await redis.zrem(f"chat:sockets:{identity['uid']}", connection_id)
            except RedisError:
                logger.warning("Chat socket lease cleanup deferred to expiry.")
