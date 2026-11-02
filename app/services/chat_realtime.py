import asyncio
import hashlib
import json
import logging
import secrets
import time
from contextlib import asynccontextmanager

from bson import ObjectId
from fastapi import HTTPException
from redis.asyncio import Redis

from app.config import settings

logger = logging.getLogger("loja3d.chat")
CHANNEL = "chat:events"


def redis_client():
    return Redis.from_url(settings.CHAT_REDIS_URL, decode_responses=True, socket_timeout=5)


async def limit(redis, uid, action, maximum, seconds=60):
    key = f"chat:rate:{uid}:{action}:{int(time.time()) // seconds}"
    count = await redis.eval(
        "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n",
        1, key, seconds,
    )
    if count > maximum:
        raise HTTPException(429, "Chat rate limit exceeded.", headers={"Retry-After": str(seconds)})


@asynccontextmanager
async def upload_lock(redis, uid):
    lock = redis.lock(f"chat:upload:{uid}", timeout=90, blocking_timeout=0)
    if not await lock.acquire(blocking=False):
        raise HTTPException(429, "Another upload is in progress.", headers={"Retry-After": "5"})
    try:
        yield
    finally:
        await lock.release()


async def create_ticket(redis, user, exp, origin):
    await limit(redis, str(user["_id"]), "ticket", 20)
    ticket = secrets.token_urlsafe(32)
    key = "chat:ticket:" + hashlib.sha256(ticket.encode()).hexdigest()
    await redis.set(key, json.dumps({
        "uid": str(user["_id"]), "exp": exp, "origin": origin
    }), ex=30)
    return ticket


async def consume_ticket(redis, ticket):
    key = "chat:ticket:" + hashlib.sha256(ticket.encode()).hexdigest()
    raw = await redis.getdel(key)
    return json.loads(raw) if raw else None


async def socket_user(db, identity):
    if identity["exp"] <= time.time():
        return None
    uid = identity["uid"]
    query = {"_id": ObjectId(uid) if ObjectId.is_valid(uid) else uid}
    user = await db.users.find_one(query, {"_id": 1, "role": 1, "is_active": 1})
    return user if user and user.get("is_active", True) and user.get("role") in {"ADMIN", "CUSTOMER"} else None


async def claim_socket(redis, uid, connection_id):
    key = f"chat:sockets:{uid}"
    timestamp = time.time()
    result = await redis.eval(
        "redis.call('ZREMRANGEBYSCORE',KEYS[1],'-inf',ARGV[1]); "
        "if redis.call('ZCARD',KEYS[1])>=5 then return 0 end; "
        "redis.call('ZADD',KEYS[1],ARGV[2],ARGV[3]); redis.call('EXPIRE',KEYS[1],60); return 1",
        1, key, timestamp, timestamp + 60, connection_id,
    )
    return bool(result)


async def relay(socket, db, identity, connection_id):
    async with redis_client() as redis:
        async with redis.pubsub() as pubsub:
            await pubsub.subscribe(CHANNEL)
            await socket.send_json({"v": 1, "type": "ready"})
            last_ping = time.monotonic()
            while True:
                user = await socket_user(db, identity)
                if not user:
                    await socket.close(code=4401)
                    return
                item = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
                if item:
                    event = json.loads(item["data"])
                    if user["role"] == "ADMIN" or event["customer_id"] == identity["uid"]:
                        await asyncio.wait_for(socket.send_json(event["event"]), 5)
                if time.monotonic() - last_ping >= 20:
                    await redis.zadd(f"chat:sockets:{identity['uid']}", {connection_id: time.time() + 60})
                    await redis.expire(f"chat:sockets:{identity['uid']}", 60)
                    await asyncio.wait_for(socket.send_json({"v": 1, "type": "ping"}), 5)
                    last_ping = time.monotonic()
