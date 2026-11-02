from datetime import date, datetime, timezone
from enum import Enum
from typing import List, Optional
from urllib.parse import urlparse

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator, model_validator

HTTP_URL_ADAPTER = TypeAdapter(AnyHttpUrl)


class PrintRequestStatus(str, Enum):
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    INFORMATION_REQUIRED = "information_required"
    AWAITING_QUOTE_APPROVAL = "awaiting_quote_approval"
    QUOTE_CHANGES_REQUESTED = "quote_changes_requested"
    AWAITING_PAYMENT = "awaiting_payment"
    PAYMENT_VERIFICATION = "payment_verification"
    PAYMENT_CONFIRMED = "payment_confirmed"
    IN_PRODUCTION = "in_production"
    PRODUCTION_PAUSED = "production_paused"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class RequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=3, max_length=150)
    description: str = Field(min_length=10, max_length=5000)
    quantity: int = Field(gt=0, le=1000, strict=True)
    dimensions: str = Field(min_length=2, max_length=200)
    material: Optional[str] = Field(default=None, max_length=100)
    color: Optional[str] = Field(default=None, max_length=100)
    referenceLinks: List[str] = Field(default_factory=list, max_length=5)

    @field_validator("title", "description", "dimensions")
    @classmethod
    def trim_required_text(cls, value: str, info) -> str:
        value = value.strip()
        minimum_lengths = {"title": 3, "description": 10, "dimensions": 2}
        if len(value) < minimum_lengths[info.field_name]:
            raise ValueError("This field is too short.")
        return value

    @field_validator("material", "color")
    @classmethod
    def trim_optional_text(cls, value: Optional[str]) -> Optional[str]:
        value = value.strip() if value is not None else None
        return value or None

    @field_validator("referenceLinks")
    @classmethod
    def validate_reference_links(cls, values: List[str]) -> List[str]:
        cleaned = []
        for value in values:
            value = value.strip()
            parsed = urlparse(value)
            if (
                len(value) > 2048
                or parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.username is not None
                or parsed.password is not None
            ):
                raise ValueError("Reference links must be valid http(s) URLs.")
            try:
                HTTP_URL_ADAPTER.validate_python(value)
            except ValidationError as exc:
                raise ValueError("Reference links must be valid http(s) URLs.") from exc
            cleaned.append(value)
        return cleaned


class MessageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1, strict=True)
    message: str = Field(min_length=1, max_length=5000)

    @field_validator("message")
    @classmethod
    def trim_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message cannot be blank.")
        return value


class CustomerAction(str, Enum):
    APPROVE_QUOTE = "approve_quote"
    REQUEST_CHANGES = "request_changes"
    CANCEL = "cancel"


class CustomerActionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1, strict=True)
    action: CustomerAction
    quoteVersion: Optional[int] = Field(default=None, ge=1, strict=True)
    message: str = Field(default="", max_length=5000)

    @model_validator(mode="after")
    def validate_action_message(self):
        self.message = self.message.strip()
        if self.action != CustomerAction.APPROVE_QUOTE and not self.message:
            raise ValueError("A reason is required for cancellation or quote changes.")
        return self


class QuoteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1, strict=True)
    amountCents: int = Field(gt=0, le=100_000_000, strict=True)
    currency: str = Field(pattern="^EUR$")
    scope: str = Field(min_length=2, max_length=5000)
    leadDays: int = Field(gt=0, le=365, strict=True)
    validUntil: datetime

    @field_validator("scope")
    @classmethod
    def trim_scope(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Quote scope cannot be blank.")
        return value

    @field_validator("validUntil")
    @classmethod
    def normalize_valid_until(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("validUntil must include a timezone.")
        return value.astimezone(timezone.utc)


class AdminTransitionInput(MessageInput):
    status: PrintRequestStatus
    trackingUrl: Optional[str] = Field(default=None, max_length=2048)
    estimatedShipping: Optional[date] = None

    @field_validator("trackingUrl")
    @classmethod
    def validate_tracking_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        parsed = urlparse(value)
        if (
            parsed.scheme not in {"http", "https"} or not parsed.netloc
            or parsed.username is not None or parsed.password is not None
        ):
            raise ValueError("Tracking URL must be a valid http(s) URL.")
        try:
            HTTP_URL_ADAPTER.validate_python(value)
        except ValidationError as exc:
            raise ValueError("Tracking URL must be a valid http(s) URL.") from exc
        return value


class QuoteResponse(BaseModel):
    version: int
    amountCents: int
    currency: str
    scope: str
    leadDays: int
    validUntil: str
    createdAt: str
    approvedAt: Optional[str] = None


class HistoryResponse(BaseModel):
    id: str
    kind: str
    actorRole: str
    actorName: str
    message: str
    status: PrintRequestStatus
    createdAt: str


class PrintRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    reference: str
    ownerId: str
    customerName: str
    customerEmail: str
    title: str
    description: str
    quantity: int
    dimensions: str
    material: Optional[str] = None
    color: Optional[str] = None
    referenceLinks: List[str]
    status: PrintRequestStatus
    version: int
    createdAt: str
    updatedAt: str
    quotes: List[QuoteResponse]
    history: List[HistoryResponse]
    trackingUrl: Optional[str] = None
    estimatedShipping: Optional[str] = None
    allowedTransitions: List[str]
    allowedActions: List[str]


class PrintRequestPage(BaseModel):
    items: List[PrintRequest]
    total: int
    page: int
    pageSize: int


class RequestSort(str, Enum):
    NEWEST = "newest"
    OLDEST = "oldest"


def iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
