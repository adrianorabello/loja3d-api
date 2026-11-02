import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt

from fastapi import HTTPException
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.models.chat import ChatMessageInput
from app.config import settings


def now():
    return datetime.now(timezone.utc)


def identifier():
    return str(uuid4())


async def init_chat(db):
    hello = await db.command("hello")
    if not hello.get("setName"):
        raise RuntimeError("Chat requires a MongoDB replica set; no standalone fallback.")
    await db.chat_conversations.create_index("customer_id", unique=True)
    await db.chat_conversations.create_index([("updated_at", -1), ("_id", -1)])
    await db.chat_messages.create_index([("conversation_id", 1), ("seq", 1)], unique=True)
    await db.chat_messages.create_index(
        [("conversation_id", 1), ("sender_id", 1), ("client_message_id", 1)], unique=True
    )
    await db.chat_reads.create_index([("conversation_id", 1), ("user_id", 1)], unique=True)
    await db.chat_attachments.create_index([("owner_id", 1), ("status", 1), ("created_at", 1)])
    await db.chat_outbox.create_index([("published", 1), ("created_at", 1)])
    # Create collections before entering transactions.
    for collection in ("chat_reads", "chat_outbox"):
        await db[collection].find_one({})


def user_id(user):
    return str(user["_id"])


async def conversation(db, cid, user, session=None):
    query = {"_id": cid}
    if user.get("role") != "ADMIN":
        query["customer_id"] = user_id(user)
    doc = await db.chat_conversations.find_one(query, session=session)
    if not doc:
        raise HTTPException(404, "Conversation not found.")
    return doc


async def summary(db, doc, user):
    uid = user_id(user)
    marker = await db.chat_reads.find_one({"conversation_id": doc["_id"], "user_id": uid})
    seq = marker["last_read_seq"] if marker else 0
    unread = await db.chat_messages.count_documents({
        "conversation_id": doc["_id"], "seq": {"$gt": seq}, "sender_id": {"$ne": uid}
    })
    return {
        "id": doc["_id"], "customerName": doc["customer_name"],
        "lastSeq": doc["last_seq"], "preview": doc.get("preview", ""),
        "updatedAt": doc["updated_at"], "unread": unread, "lastReadSeq": seq,
    }


async def get_or_create(db, user):
    if user.get("role") != "CUSTOMER":
        raise HTTPException(403, "Only customers can start support conversations.")
    uid = user_id(user)
    try:
        return await create_conversation_document(db, user, uid)
    except DuplicateKeyError:
        doc = await db.chat_conversations.find_one({"customer_id": uid})
        if not doc:
            raise
        return await summary(db, doc, user)


async def create_conversation_document(db, user, uid):
    doc = await db.chat_conversations.find_one_and_update(
        {"customer_id": uid},
        {"$setOnInsert": {
            "_id": identifier(), "customer_id": uid, "customer_name": user["name"],
            "last_seq": 0, "created_at": now(), "updated_at": now(), "preview": "",
        }},
        upsert=True, return_document=ReturnDocument.AFTER,
    )
    return await summary(db, doc, user)


async def list_conversations(db, user, cursor, limit, q):
    query = {} if user.get("role") == "ADMIN" else {"customer_id": user_id(user)}
    if q:
        query["customer_name"] = {"$regex": re.escape(q), "$options": "i"}
    if cursor:
        try:
            data = jwt.decode(cursor, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM],
                              audience="chat-cursor", issuer="chat-cursor")
            if data["uid"] != user_id(user) or data["q"] != q:
                raise ValueError("Cursor filters changed.")
            timestamp = datetime.fromisoformat(data["time"])
            position = str(UUID(data["id"]))
        except (jwt.PyJWTError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(422, "Invalid or expired conversation cursor.") from exc
        query["$or"] = [
            {"updated_at": {"$lt": timestamp}}, {"updated_at": timestamp, "_id": {"$lt": position}}
        ]
    docs = await db.chat_conversations.find(query).sort([("updated_at", -1), ("_id", -1)]).limit(limit + 1).to_list(limit + 1)
    next_cursor = None
    if len(docs) > limit:
        last = docs[limit - 1]
        next_cursor = jwt.encode({
            "iss": "chat-cursor", "aud": "chat-cursor", "uid": user_id(user), "q": q,
            "time": last["updated_at"].isoformat(), "id": last["_id"],
            "exp": now() + timedelta(hours=1),
        }, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return {
        "items": [await summary(db, doc, user) for doc in docs[:limit]],
        "hasMore": len(docs) > limit,
        "nextCursor": next_cursor,
    }


def attachment_output(doc):
    return {
        "id": doc["_id"], "name": doc["name"], "contentType": doc["content_type"],
        "size": doc["size"], "status": doc["status"], "error": doc.get("error"),
    }


def message_output(doc):
    return {
        "id": doc["_id"], "conversationId": doc["conversation_id"],
        "seq": doc["seq"], "sender": doc["sender"], "text": doc["text"],
        "clientMessageId": doc["client_message_id"], "createdAt": doc["created_at"],
        "attachments": doc.get("attachments", []),
    }


async def emit(db, conv, kind, data, session=None):
    await db.chat_outbox.insert_one({
        "_id": identifier(), "customer_id": conv["customer_id"], "published": False,
        "created_at": now(),
        "event": {"v": 1, "eventId": identifier(), "type": kind,
                  "conversationId": conv["_id"], "seq": conv["last_seq"], "data": data},
    }, session=session)


async def send_message(db, cid, user, body: ChatMessageInput):
    uid = user_id(user)
    await conversation(db, cid, user)
    key = {"conversation_id": cid, "sender_id": uid, "client_message_id": str(body.clientMessageId)}
    fingerprint = hashlib.sha256(json.dumps(
        {"text": body.text, "attachments": body.attachmentIds}, sort_keys=True
    ).encode()).hexdigest()

    async def transaction(session):
        previous = await db.chat_messages.find_one(key, session=session)
        if previous:
            if previous["fingerprint"] != fingerprint:
                raise HTTPException(409, "Idempotency key already used with different content.")
            return message_output(previous)
        conv = await conversation(db, cid, user, session)
        files = []
        for aid in body.attachmentIds:
            item = await db.chat_attachments.find_one({
                "_id": aid, "conversation_id": cid, "owner_id": uid, "status": "ready"
            }, session=session)
            if not item:
                raise HTTPException(409, "Attachment is not ready or does not belong to this message.")
            files.append(item)
        conv = await db.chat_conversations.find_one_and_update(
            {"_id": cid}, {"$inc": {"last_seq": 1}, "$set": {
                "updated_at": now(), "preview": body.text[:160] or files[0]["name"],
            }}, return_document=ReturnDocument.AFTER, session=session,
        )
        doc = {
            "_id": identifier(), **key, "seq": conv["last_seq"], "text": body.text,
            "sender": {"id": uid, "name": user["name"], "role": user["role"]},
            "fingerprint": fingerprint, "created_at": now(),
            "attachments": [{**attachment_output(item), "status": "attached"} for item in files],
        }
        await db.chat_messages.insert_one(doc, session=session)
        for item in files:
            await db.chat_attachments.update_one({"_id": item["_id"], "status": "ready"}, {
                "$set": {"status": "attached", "message_id": doc["_id"]}
            }, session=session)
        await emit(db, conv, "message.created", {"messageId": doc["_id"]}, session)
        return message_output(doc)

    try:
        async with await db.client.start_session() as session:
            return await session.with_transaction(transaction)
    except DuplicateKeyError:
        previous = await db.chat_messages.find_one(key)
        if not previous or previous["fingerprint"] != fingerprint:
            raise HTTPException(409, "Conflicting message retry.")
        return message_output(previous)


async def mark_read(db, cid, user, seq):
    conv = await conversation(db, cid, user)
    if seq > conv["last_seq"]:
        raise HTTPException(422, "Read marker exceeds the last message.")
    async def transaction(session):
        doc = await db.chat_reads.find_one_and_update(
            {"conversation_id": cid, "user_id": user_id(user)},
            {"$max": {"last_read_seq": seq}, "$set": {"updated_at": now()}},
            upsert=True, return_document=ReturnDocument.AFTER, session=session,
        )
        await emit(db, conv, "read.updated", {}, session)
        return {"lastReadSeq": doc["last_read_seq"]}

    async with await db.client.start_session() as session:
        return await session.with_transaction(transaction)
