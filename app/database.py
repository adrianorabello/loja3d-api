import logging
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.config import settings

logger = logging.getLogger("loja3d.database")


class DatabaseManager:
    client: Optional[AsyncIOMotorClient] = None
    db: Optional[AsyncIOMotorDatabase] = None


db_manager = DatabaseManager()


async def get_database() -> AsyncIOMotorDatabase:
    if db_manager.db is None:
        raise RuntimeError("Database connection has not been initialized.")
    return db_manager.db


async def init_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create essential unique and search indexes for all collections."""
    try:
        # Users
        await db.users.create_index([("email", 1)], unique=True, name="idx_users_email_unique")
        await db.users.create_index([("role", 1), ("is_active", 1)], name="idx_users_role_status")

        # Products
        await db.products.create_index([("slug", 1)], unique=True, name="idx_products_slug_unique")
        await db.products.create_index([("active", 1), ("featured", -1), ("created_at", -1)], name="idx_products_storefront")
        await db.products.create_index([("active", 1), ("category_id", 1)], name="idx_products_category")

        # Categories
        await db.categories.create_index([("id", 1)], unique=True, name="idx_categories_id_unique")
        await db.categories.create_index([("slug", 1)], unique=True, name="idx_categories_slug_unique")

        # Refresh Tokens
        await db.refresh_tokens.create_index([("token_hash", 1)], unique=True, name="idx_refresh_tokens_hash")
        await db.refresh_tokens.create_index([("user_id", 1)], name="idx_refresh_tokens_user")
        await db.refresh_tokens.create_index([("expires_at", 1)], expireAfterSeconds=0, name="idx_refresh_tokens_ttl")

        # Single-use auth tokens (e-mail verification, password reset, e-mail change)
        await db.auth_tokens.create_index([("token_hash", 1)], unique=True, name="idx_auth_tokens_hash")
        await db.auth_tokens.create_index([("expires_at", 1)], expireAfterSeconds=0, name="idx_auth_tokens_ttl")

        logger.info("Database indexes initialized successfully.")
    except Exception as e:
        logger.warning("Could not initialize some indexes: %s", e)


async def connect_to_mongo() -> None:
    logger.info("Connecting to MongoDB at %s...", settings.MONGODB_URL)
    db_manager.client = AsyncIOMotorClient(
        settings.MONGODB_URL,
        serverSelectionTimeoutMS=5000,
        uuidRepresentation="standard"
    )
    db_manager.db = db_manager.client[settings.MONGODB_DB_NAME]
    # Ping database to confirm connection
    await db_manager.client.admin.command("ping")
    logger.info("Connected to MongoDB database '%s'.", settings.MONGODB_DB_NAME)
    await init_indexes(db_manager.db)


async def close_mongo_connection() -> None:
    logger.info("Closing MongoDB connection...")
    if db_manager.client:
        db_manager.client.close()
        db_manager.client = None
        db_manager.db = None
    logger.info("MongoDB connection closed.")
