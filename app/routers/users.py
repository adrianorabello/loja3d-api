from datetime import datetime, timezone
import logging
from uuid import uuid4
from bson import Binary
from typing import Any, Dict
from pymongo.errors import DuplicateKeyError
from pydantic import ValidationError
from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from starlette.concurrency import run_in_threadpool
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError
from app.core.dependencies import format_user_document, get_current_user
from app.core.phone import normalize_phone
from app.core.rate_limit import rate_limit
from app.core.security import verify_password
from app.database import get_database
from app.models.user import EmailChangeRequest, MessageResponse, TokenRequest, UserProfileUpdate, UserResponse
from app.services.email import send_email
from app.services.tokens import consume_token, create_token
from app.services.avatar import MAX_AVATAR_BYTES, normalize_avatar
from app.config import settings
from datetime import timedelta

router = APIRouter(tags=["Users & Profile"])
logger = logging.getLogger("loja3d.profile")


@router.post("/users/me/avatar", response_model=UserResponse,
             dependencies=[Depends(rate_limit("avatar-upload", 10, 60))])
async def upload_my_avatar(
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db=Depends(get_database),
):
    try:
        data = await file.read(MAX_AVATAR_BYTES + 1)
    finally:
        await file.close()
    normalized = await run_in_threadpool(normalize_avatar, data, file.content_type or "")
    try:
        user = await db.users.find_one_and_update(
            {"_id": current_user["_id"]},
            {"$set": {"avatar_data": Binary(normalized), "avatar_version": uuid4().hex,
                      "avatar": None, "updated_at": datetime.now(timezone.utc)}},
            projection={"avatar_data": 0}, return_document=ReturnDocument.AFTER,
        )
    except PyMongoError as exc:
        logger.exception("Avatar persistence failed for user %s", current_user["_id"])
        raise HTTPException(503, detail="Could not save the photo. Please try again.") from exc
    if user is None:
        raise HTTPException(404, detail="User not found.")
    return format_user_document(user)


@router.get("/users/me/avatar")
async def get_my_avatar(
    current_user: Dict[str, Any] = Depends(get_current_user),
    db=Depends(get_database),
):
    user = await db.users.find_one({"_id": current_user["_id"]}, {"avatar_data": 1})
    if not user or not user.get("avatar_data"):
        raise HTTPException(404, detail="No profile photo.")
    return Response(bytes(user["avatar_data"]), media_type="image/jpeg",
                    headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.delete("/users/me/avatar", response_model=UserResponse)
async def remove_my_avatar(
    current_user: Dict[str, Any] = Depends(get_current_user),
    db=Depends(get_database),
):
    try:
        user = await db.users.find_one_and_update(
            {"_id": current_user["_id"]},
            {"$unset": {"avatar_data": "", "avatar_version": ""},
             "$set": {"avatar": None, "updated_at": datetime.now(timezone.utc)}},
            projection={"avatar_data": 0}, return_document=ReturnDocument.AFTER,
        )
    except PyMongoError as exc:
        logger.exception("Avatar removal failed for user %s", current_user["_id"])
        raise HTTPException(503, detail="Could not remove the photo. Please try again.") from exc
    if user is None:
        raise HTTPException(404, detail="User not found.")
    return format_user_document(user)


@router.get("/users/me", response_model=UserResponse)
@router.get("/common/user", response_model=UserResponse)
async def get_my_profile(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Retrieve the currently authenticated user's profile and addresses."""
    return format_user_document(current_user)


@router.patch("/users/me", response_model=UserResponse)
@router.patch("/common/user", response_model=UserResponse)
async def update_my_profile(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Update the authenticated user's personal details and delivery addresses.
    Supports both direct payload and legacy Fuse shape { user: ... }.
    Strictly forbids role elevation and sensitive field modification.
    """
    raw_body = await request.json()
    if not isinstance(raw_body, dict) or not isinstance(raw_body.get("user", raw_body), dict):
        raise HTTPException(422, detail=[{"loc": ["body"], "msg": "Expected a profile object."}])
    user_data = raw_body.get("user", raw_body)
    try:
        payload = UserProfileUpdate(**user_data)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=[{"msg": e["msg"], "loc": ["body", *e["loc"]]} for e in exc.errors()])

    update_fields: Dict[str, Any] = {}

    if payload.name is not None:
        update_fields["name"] = payload.name.strip()

    if payload.email is not None and payload.email.strip().lower() != current_user.get("email"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A alteração de e-mail requer confirmação. Use /users/me/email-change."
        )

    fields_set = payload.model_fields_set
    if "phone" in fields_set:
        if payload.phone:
            try:
                phone, country = normalize_phone(payload.phone, payload.phoneCountry)
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=[{"loc": ["body", "phone"], "msg": str(exc)}])
            update_fields["phone"], update_fields["phone_country"] = phone, country
        else:
            update_fields["phone"], update_fields["phone_country"] = None, None

    if "dateOfBirth" in fields_set:
        update_fields["date_of_birth"] = payload.dateOfBirth

    if payload.addresses is not None:
        update_fields["addresses"] = [addr.model_dump() for addr in payload.addresses]

    update_fields["updated_at"] = datetime.now(timezone.utc)

    await db.users.update_one(
        {"_id": current_user["_id"]},
        {"$set": update_fields}
    )

    updated_user = await db.users.find_one({"_id": current_user["_id"]}, {"avatar_data": 0})
    return format_user_document(updated_user)


@router.post("/users/me/email-change", response_model=MessageResponse,
             dependencies=[Depends(rate_limit("email-change", 5, 900))])
async def request_email_change(
    payload: EmailChangeRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db=Depends(get_database),
):
    """Start an e-mail change: requires the current password and a confirmation sent to the new address."""
    if not verify_password(payload.password, current_user.get("password_hash", "")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Senha incorreta.")
    new_email = payload.newEmail.strip().lower()
    if await db.users.find_one({"email": new_email}):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="O e-mail indicado já se encontra associado a outra conta.")
    token = await create_token(
        db, current_user["_id"], "change_email",
        timedelta(hours=settings.EMAIL_VERIFICATION_EXPIRE_HOURS), {"new_email": new_email},
    )
    link = f"{settings.FRONTEND_URL}/confirmation-required?emailChangeToken={token}"
    send_email(new_email, "Confirme o novo e-mail - Printoy 3D", f"Confirme a alteração de e-mail:\n{link}\n")
    return MessageResponse(message="Enviámos um e-mail de confirmação para o novo endereço.")


@router.post("/users/me/email-change/confirm", response_model=MessageResponse)
async def confirm_email_change(
    payload: TokenRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db=Depends(get_database),
):
    doc = await consume_token(db, payload.token, "change_email")
    if not doc or doc["user_id"] != current_user["_id"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Link inválido ou expirado.")
    try:
        await db.users.update_one(
            {"_id": current_user["_id"]},
            {"$set": {"email": doc["data"]["new_email"], "email_verified": True, "updated_at": datetime.now(timezone.utc)}},
        )
    except DuplicateKeyError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="O e-mail indicado já se encontra associado a outra conta.")
    return MessageResponse(message="E-mail atualizado.")
