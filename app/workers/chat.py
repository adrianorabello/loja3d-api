import asyncio
import json
import logging
import sys
from datetime import timedelta

from gridfs.errors import NoFile
from motor.motor_asyncio import AsyncIOMotorGridFSBucket
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError

from app.config import settings
from app.database import close_mongo_connection, connect_to_mongo, get_database
from app.services.chat import init_chat, now
from app.services.chat_attachments import process_attachment
from app.services.chat_realtime import CHANNEL, redis_client

logger = logging.getLogger("loja3d.chat.worker")


async def cleanup(db):
    cutoff = now() - timedelta(hours=24)
    bucket = AsyncIOMotorGridFSBucket(db, bucket_name="chat_files")
    async for doc in db.chat_attachments.find({
        "$or": [{"status": "cancelled"}, {"status": {"$ne": "attached"}, "created_at": {"$lt": cutoff}}]
    }):
        # Claim before deleting: it can no longer be bound in a message transaction.
        claimed = await db.chat_attachments.find_one_and_update(
            {"_id": doc["_id"], "status": {"$ne": "attached"}}, {"$set": {"status": "cancelled"}}
        )
        if claimed:
            try:
                await bucket.delete(claimed["grid_id"])
            except NoFile:
                logger.warning("Pending chat file was already absent: %s", claimed["_id"])
            await db.chat_attachments.delete_one({"_id": claimed["_id"], "status": "cancelled"})
    # GridFS has no transaction with metadata; remove files left by interrupted normalization/uploads.
    async for file in db["chat_files.files"].find({"uploadDate": {"$lt": cutoff}}):
        if not await db.chat_attachments.find_one({"grid_id": file["_id"]}):
            await bucket.delete(file["_id"])
    # Chunks without a files entry can result from an interrupted stream.
    async for chunk in db["chat_files.chunks"].aggregate([
        {"$group": {"_id": "$files_id"}}, {"$limit": 1000}
    ]):
        if not await db["chat_files.files"].find_one({"_id": chunk["_id"]}) and not await db.chat_attachments.find_one({"grid_id": chunk["_id"]}):
            await db["chat_files.chunks"].delete_many({"files_id": chunk["_id"]})
    await db.chat_outbox.delete_many({"published": True, "created_at": {"$lt": cutoff}})


async def tick(db, redis):
    async for item in db.chat_outbox.find({"published": False}).sort("created_at", 1).limit(100):
        await redis.publish(CHANNEL, json.dumps({
            "customer_id": item["customer_id"], "event": item["event"]
        }))
        await db.chat_outbox.update_one({"_id": item["_id"]}, {"$set": {"published": True}})
    async for doc in db.chat_attachments.find({"status": "quarantined"}).limit(1):
        await process_attachment(db, doc)


async def main():
    if not settings.CHAT_ENABLED:
        raise RuntimeError("Enable CHAT_ENABLED explicitly before starting the worker.")
    if not sys.platform.startswith("linux"):
        logger.warning("Development parser uses CPU/wall-time limits; production memory isolation requires Linux.")
    await connect_to_mongo()
    try:
        db = await get_database()
        await init_chat(db)
        async with redis_client() as redis:
            await redis.ping()
            while True:
                # One scanning/cleanup leader. Outbox is at-least-once; clients reconcile over REST.
                lock = redis.lock("chat:worker", timeout=300, blocking_timeout=1)
                try:
                    if await lock.acquire(blocking=True):
                        try:
                            await tick(db, redis)
                            await cleanup(db)
                        finally:
                            await lock.release()
                except (PyMongoError, RedisError, OSError, NoFile):
                    logger.exception("Chat worker failed; files remain private and the next cycle retries.")
                await asyncio.sleep(1)
    finally:
        await close_mongo_connection()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
