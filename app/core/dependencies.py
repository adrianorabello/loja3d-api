from typing import Any, Dict, List, Optional
from bson import ObjectId
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.config import settings
from app.core.security import decode_access_token
from app.database import get_database
from app.models.user import UserAddress, UserResponse, UserRole

security_bearer = HTTPBearer(auto_error=False)


def format_user_document(doc: Dict[str, Any]) -> UserResponse:
    """Map a raw MongoDB user document to UserResponse schema."""
    addresses_raw = doc.get("addresses", [])
    addresses = [
        UserAddress(
            id=addr.get("id", ""),
            label=addr.get("label", ""),
            street=addr.get("street", ""),
            unit=addr.get("unit"),
            postalCode=addr.get("postal_code") or addr.get("postalCode", ""),
            city=addr.get("city", ""),
            country=addr.get("country", "Portugal")
        )
        for addr in addresses_raw
    ]

    return UserResponse(
        id=str(doc["_id"]),
        name=doc.get("name", ""),
        email=doc.get("email", ""),
        role=UserRole(doc.get("role", UserRole.CUSTOMER)),
        dateOfBirth=doc.get("date_of_birth"),
        phone=doc.get("phone"),
        phoneCountry=doc.get("phone_country"),
        emailVerified=bool(doc.get("email_verified", False)),
        avatar=doc.get("avatar"),
        status=doc.get("status", "online"),
        addresses=addresses
    )


async def get_current_user(
    auth: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
    db=Depends(get_database)
) -> Dict[str, Any]:
    """Extract and validate the JWT Bearer token and return the raw user document."""
    if not auth or not auth.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação necessária.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = auth.credentials
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token sem identificação do utilizador.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    try:
        user_query = {"_id": ObjectId(user_id)}
    except Exception:
        user_query = {"_id": user_id}

    user = await db.users.find_one(user_query)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilizador não encontrado.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Utilizador desativado."
        )

    return user


def require_role(allowed_roles: List[UserRole]):
    """Dependency factory restricting access to users holding at least one of allowed_roles."""
    async def role_checker(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        user_role = current_user.get("role")
        if user_role not in [role.value for role in allowed_roles]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acesso não autorizado para o perfil atual."
            )
        return current_user

    return role_checker
