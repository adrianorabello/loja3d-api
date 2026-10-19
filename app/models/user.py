from datetime import date
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.core.phone import normalize_phone


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    CUSTOMER = "CUSTOMER"


class UserAddress(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    label: str
    street: str
    unit: Optional[str] = None
    postalCode: str = Field(..., description="Portuguese postal code, e.g. 4000-123")
    city: str
    country: str = "Portugal"


class UserResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    email: EmailStr
    role: UserRole
    dateOfBirth: Optional[str] = None
    phone: Optional[str] = None
    phoneCountry: Optional[str] = None
    emailVerified: bool = False
    avatar: Optional[str] = None
    status: Optional[str] = "online"
    addresses: List[UserAddress] = Field(default_factory=list)


def _check_birth_date(value: Optional[str]) -> Optional[str]:
    if value in (None, ""):
        return None
    try:
        parsed = date.fromisoformat(value[:10])
    except ValueError:
        raise ValueError("Data de nascimento inválida.")
    if parsed > date.today() or parsed.year < 1900:
        raise ValueError("Data de nascimento inválida.")
    return parsed.isoformat()


class SignUpRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=256)
    confirmPassword: Optional[str] = Field(None, exclude=True)
    dateOfBirth: Optional[str] = None
    phone: Optional[str] = Field(None, max_length=40)
    phoneCountry: Optional[str] = Field(None, min_length=2, max_length=2)

    @field_validator("dateOfBirth")
    @classmethod
    def _birth(cls, v):
        return _check_birth_date(v)

    @model_validator(mode="after")
    def _check(self):
        if self.confirmPassword is not None and self.confirmPassword != self.password:
            raise ValueError("A confirmação da senha não coincide.")
        if self.phone:
            normalize_phone(self.phone, self.phoneCountry)
        return self


class SignInRequest(BaseModel):
    email: EmailStr
    password: str
    rememberMe: Optional[bool] = False


class SignInResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    user: UserResponse
    access_token: str
    token_type: str = "bearer"
    refresh_token: Optional[str] = None


class RefreshTokenRequest(BaseModel):
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None


class UserProfileUpdate(BaseModel):
    # Only whitelisted fields; role/status/emailVerified are never accepted.
    model_config = ConfigDict(extra="ignore")

    name: Optional[str] = Field(None, min_length=2, max_length=100)
    email: Optional[EmailStr] = None
    dateOfBirth: Optional[str] = None
    phone: Optional[str] = Field(None, max_length=40)
    phoneCountry: Optional[str] = Field(None, min_length=2, max_length=2)
    addresses: Optional[List[UserAddress]] = None

    @field_validator("dateOfBirth")
    @classmethod
    def _birth(cls, v):
        return _check_birth_date(v)


class EmailRequest(BaseModel):
    email: EmailStr


class TokenRequest(BaseModel):
    token: str = Field(..., min_length=10, max_length=200)


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=10, max_length=200)
    password: str = Field(..., min_length=8, max_length=256)


class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = None


class EmailChangeRequest(BaseModel):
    newEmail: EmailStr
    password: str


class MessageResponse(BaseModel):
    message: str
