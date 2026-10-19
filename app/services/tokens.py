import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from app.core.security import hash_token


async def create_token(db, user_id, purpose: str, ttl: timedelta, data: Optional[Dict[str, Any]] = None) -> str:
    """Issue a single-use token; only its SHA-256 hash is stored. Older tokens of the same purpose are invalidated."""
    await db.auth_tokens.delete_many({"user_id": user_id, "purpose": purpose})
    raw = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    await db.auth_tokens.insert_one({
        "token_hash": hash_token(raw),
        "user_id": user_id,
        "purpose": purpose,
        "data": data or {},
        "created_at": now,
        "expires_at": now + ttl,
    })
    return raw


async def consume_token(db, raw: str, purpose: str) -> Optional[Dict[str, Any]]:
    """Atomically consume a token. Returns the stored document, or None if unknown, expired or already used."""
    doc = await db.auth_tokens.find_one_and_delete({"token_hash": hash_token(raw), "purpose": purpose})
    if not doc:
        return None
    expires_at = doc["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        return None
    return doc
