from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
import logging
from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.config import settings
from app.core.dependencies import format_user_document, get_current_user
from app.core.phone import normalize_phone
from app.core.rate_limit import rate_limit
from app.services.email import send_email
from app.services.tokens import consume_token, create_token
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    password_needs_rehash,
    verify_password,
)
from app.database import get_database
from app.models.user import (
    EmailRequest,
    LogoutRequest,
    MessageResponse,
    ResetPasswordRequest,
    TokenRequest,
    RefreshTokenRequest,
    SignInRequest,
    SignInResponse,
    SignUpRequest,
    UserRole,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])
optional_bearer = HTTPBearer(auto_error=False)
logger = logging.getLogger("loja3d.auth")

GENERIC_RESET_MESSAGE = "Se existir uma conta com esse e-mail, enviámos as instruções."


async def send_verification_email(db, user: Dict[str, Any]) -> None:
    token = await create_token(
        db, user["_id"], "verify_email",
        timedelta(hours=settings.EMAIL_VERIFICATION_EXPIRE_HOURS),
        {"email": user["email"]},
    )
    link = f"{settings.FRONTEND_URL}/confirmation-required?token={token}"
    send_email(
        user["email"],
        "Confirme o seu e-mail - Printoy 3D",
        f"Olá {user.get('name', '')},\n\nConfirme o seu e-mail através deste link "
        f"(válido por {settings.EMAIL_VERIFICATION_EXPIRE_HOURS} horas):\n{link}\n",
    )


@router.post("/sign-up", response_model=SignInResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(rate_limit("sign-up", 10, 3600))])
@router.post("/register", response_model=SignInResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(rate_limit("sign-up", 10, 3600))])
async def sign_up(payload: SignUpRequest, db=Depends(get_database)):
    """Register a new customer account, establish session and return tokens."""
    normalized_email = payload.email.strip().lower()

    existing = await db.users.find_one({"email": normalized_email})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este e-mail já está registado."
        )

    now = datetime.now(timezone.utc)
    new_user_doc = {
        "name": payload.name.strip(),
        "email": normalized_email,
        "password_hash": hash_password(payload.password),
        "role": UserRole.CUSTOMER.value,
        "is_active": True,
        "email_verified": False,
        "status": "online",
        "avatar": "assets/images/avatars/female-01.jpg",
        "addresses": [],
        "date_of_birth": payload.dateOfBirth,
        "created_at": now,
        "updated_at": now
    }

    if payload.phone:
        new_user_doc["phone"], new_user_doc["phone_country"] = normalize_phone(payload.phone, payload.phoneCountry)

    try:
        result = await db.users.insert_one(new_user_doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Este e-mail já está registado.")
    user_id = str(result.inserted_id)
    new_user_doc["_id"] = result.inserted_id

    try:
        await send_verification_email(db, new_user_doc)
    except HTTPException:
        logger.warning("Verification e-mail could not be sent for user %s", user_id)

    # Create tokens
    access_token = create_access_token(
        subject=user_id,
        role=UserRole.CUSTOMER.value,
        email=normalized_email
    )
    raw_refresh = generate_refresh_token()
    refresh_expires = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    await db.refresh_tokens.insert_one({
        "token_hash": hash_token(raw_refresh),
        "user_id": result.inserted_id,
        "expires_at": refresh_expires,
        "revoked": False,
        "created_at": now
    })

    return SignInResponse(
        user=format_user_document(new_user_doc),
        access_token=access_token,
        token_type="bearer",
        refresh_token=raw_refresh
    )


@router.post("/sign-in", response_model=SignInResponse,
             dependencies=[Depends(rate_limit("sign-in", 10, 60))])
@router.post("/login", response_model=SignInResponse,
             dependencies=[Depends(rate_limit("sign-in", 10, 60))])
async def sign_in(payload: SignInRequest, db=Depends(get_database)):
    """Authenticate with email and password and return access and refresh tokens."""
    normalized_email = payload.email.strip().lower()

    user = await db.users.find_one({"email": normalized_email})
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Utilizador desativado."
        )

    now = datetime.now(timezone.utc)
    user_id = str(user["_id"])
    role = user.get("role", UserRole.CUSTOMER.value)

    # Create tokens
    access_token = create_access_token(
        subject=user_id,
        role=role,
        email=normalized_email
    )
    raw_refresh = generate_refresh_token()
    refresh_expires = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    await db.refresh_tokens.insert_one({
        "token_hash": hash_token(raw_refresh),
        "user_id": user["_id"],
        "expires_at": refresh_expires,
        "revoked": False,
        "created_at": now
    })

    # Update last login timestamp; transparently upgrade legacy password hashes to Argon2id
    login_update = {"last_login_at": now, "status": "online"}
    if password_needs_rehash(user.get("password_hash", "")):
        login_update["password_hash"] = hash_password(payload.password)
    await db.users.update_one({"_id": user["_id"]}, {"$set": login_update})

    return SignInResponse(
        user=format_user_document(user),
        access_token=access_token,
        token_type="bearer",
        refresh_token=raw_refresh
    )


@router.post("/refresh", response_model=SignInResponse)
@router.post("/refresh-access-token", response_model=SignInResponse)
async def refresh_tokens(payload: RefreshTokenRequest, db=Depends(get_database)):
    """Refresh the access token using either a refresh token or a valid/restorable access token."""
    user = None
    now = datetime.now(timezone.utc)

    # Case A: Refresh token provided
    if payload.refresh_token:
        hashed = hash_token(payload.refresh_token)
        stored_token = await db.refresh_tokens.find_one({
            "token_hash": hashed,
            "revoked": False,
            "expires_at": {"$gt": now}
        })
        if stored_token:
            user = await db.users.find_one({"_id": stored_token["user_id"]})
            # Rotate: revoke used refresh token
            await db.refresh_tokens.update_one(
                {"_id": stored_token["_id"]},
                {"$set": {"revoked": True, "revoked_at": now}}
            )

    # Case B: Angular fallback - sends access_token in body
    if not user and payload.access_token:
        decoded = decode_access_token(payload.access_token)
        if decoded and decoded.get("sub"):
            try:
                user = await db.users.find_one({"_id": ObjectId(decoded["sub"])})
            except Exception:
                user = await db.users.find_one({"_id": decoded["sub"]})

    if not user or not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão expirada ou inválida. Por favor, inicie sessão novamente.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    user_id = str(user["_id"])
    role = user.get("role", UserRole.CUSTOMER.value)
    email = user.get("email", "")

    new_access_token = create_access_token(subject=user_id, role=role, email=email)
    new_raw_refresh = generate_refresh_token()
    refresh_expires = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    await db.refresh_tokens.insert_one({
        "token_hash": hash_token(new_raw_refresh),
        "user_id": user["_id"],
        "expires_at": refresh_expires,
        "revoked": False,
        "created_at": now
    })

    return SignInResponse(
        user=format_user_document(user),
        access_token=new_access_token,
        token_type="bearer",
        refresh_token=new_raw_refresh
    )


@router.post("/sign-out")
async def sign_out(
    auth: HTTPAuthorizationCredentials = Security(optional_bearer),
    db=Depends(get_database)
):
    """Sign out user and revoke active session tokens."""
    if auth and auth.credentials:
        payload = decode_access_token(auth.credentials)
        if payload and payload.get("sub"):
            try:
                uid = ObjectId(payload["sub"])
            except Exception:
                uid = payload["sub"]

            await db.refresh_tokens.update_many(
                {"user_id": uid, "revoked": False},
                {"$set": {"revoked": True, "revoked_at": datetime.now(timezone.utc)}}
            )

    return {"success": True}


@router.get("/me")
async def auth_me(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Return the currently authenticated user."""
    return format_user_document(current_user)


@router.post("/logout", response_model=MessageResponse)
async def logout(payload: LogoutRequest, db=Depends(get_database)):
    """Revoke the given refresh token (idempotent)."""
    if payload.refresh_token:
        await db.refresh_tokens.update_one(
            {"token_hash": hash_token(payload.refresh_token)},
            {"$set": {"revoked": True, "revoked_at": datetime.now(timezone.utc)}},
        )
    return MessageResponse(message="Sessão terminada.")


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(payload: TokenRequest, db=Depends(get_database)):
    doc = await consume_token(db, payload.token, "verify_email")
    if not doc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Link inválido ou expirado.")
    await db.users.update_one(
        {"_id": doc["user_id"], "email": doc["data"].get("email")},
        {"$set": {"email_verified": True, "updated_at": datetime.now(timezone.utc)}},
    )
    return MessageResponse(message="E-mail confirmado com sucesso.")


@router.post("/resend-verification", response_model=MessageResponse,
             dependencies=[Depends(rate_limit("resend-verification", 5, 900))])
async def resend_verification(payload: EmailRequest, db=Depends(get_database)):
    user = await db.users.find_one({"email": payload.email.strip().lower()})
    if user and user.get("is_active", True) and not user.get("email_verified", False):
        await send_verification_email(db, user)
    return MessageResponse(message="Se a conta existir e ainda não estiver confirmada, enviámos um novo e-mail.")


@router.post("/forgot-password", response_model=MessageResponse,
             dependencies=[Depends(rate_limit("forgot-password", 5, 900))])
async def forgot_password(payload: EmailRequest, db=Depends(get_database)):
    """Always answers the same message so account existence is not disclosed."""
    user = await db.users.find_one({"email": payload.email.strip().lower()})
    if user and user.get("is_active", True):
        token = await create_token(
            db, user["_id"], "reset_password",
            timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES),
        )
        link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        send_email(
            user["email"],
            "Redefinir senha - Printoy 3D",
            f"Recebemos um pedido para redefinir a sua senha.\n"
            f"Use este link (válido por {settings.PASSWORD_RESET_EXPIRE_MINUTES} minutos):\n{link}\n\n"
            "Se não fez este pedido, ignore este e-mail.",
        )
    return MessageResponse(message=GENERIC_RESET_MESSAGE)


@router.post("/reset-password", response_model=MessageResponse,
             dependencies=[Depends(rate_limit("reset-password", 10, 900))])
async def reset_password(payload: ResetPasswordRequest, db=Depends(get_database)):
    doc = await consume_token(db, payload.token, "reset_password")
    if not doc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Link inválido ou expirado.")
    now = datetime.now(timezone.utc)
    await db.users.update_one(
        {"_id": doc["user_id"]},
        {"$set": {"password_hash": hash_password(payload.password), "updated_at": now}},
    )
    # Invalidate every active session after a password change
    await db.refresh_tokens.update_many(
        {"user_id": doc["user_id"], "revoked": False},
        {"$set": {"revoked": True, "revoked_at": now}},
    )
    return MessageResponse(message="Senha redefinida com sucesso.")
