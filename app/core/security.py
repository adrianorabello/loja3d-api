import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import bcrypt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
import jwt
from app.config import settings


_argon2 = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a password with Argon2id (no length truncation)."""
    return _argon2.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against an Argon2id hash or a legacy bcrypt hash."""
    if not hashed_password:
        return False
    try:
        if hashed_password.startswith("$argon2"):
            return _argon2.verify(hashed_password, plain_password)
        return bcrypt.checkpw(plain_password.encode("utf-8")[:72], hashed_password.encode("utf-8"))
    except (VerifyMismatchError, InvalidHashError, VerificationError, ValueError):
        return False


def password_needs_rehash(hashed_password: str) -> bool:
    """True for legacy bcrypt hashes or Argon2 hashes with outdated parameters."""
    if not hashed_password.startswith("$argon2"):
        return True
    return _argon2.check_needs_rehash(hashed_password)


def create_access_token(subject: str, role: str, email: str, expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT access token matching the Angular AuthService expected payload."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode: Dict[str, Any] = {
        "sub": str(subject),
        "email": email.strip().lower(),
        "role": role,
        "iss": "loja3d-api",
        "jti": secrets.token_hex(8),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp())
    }
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            issuer="loja3d-api"
        )
        return payload
    except jwt.PyJWTError:
        return None


def generate_refresh_token() -> str:
    """Generate a high-entropy cryptographically secure random token string."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Hash a refresh token using SHA-256 for secure database storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
