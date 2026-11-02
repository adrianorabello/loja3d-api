import re
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.dependencies import require_role
from app.database import get_database
from app.models.print_request import (
    AdminTransitionInput,
    CustomerAction,
    CustomerActionInput,
    HistoryResponse,
    MessageInput,
    PrintRequest,
    PrintRequestPage,
    PrintRequestStatus,
    QuoteInput,
    QuoteResponse,
    RequestInput,
    RequestSort,
    iso_utc,
)
from app.models.user import UserRole

customer_router = APIRouter(prefix="/print-requests", tags=["Print Requests"])
admin_router = APIRouter(prefix="/admin/print-requests", tags=["Admin Print Requests"])

customer_required = require_role([UserRole.CUSTOMER])
request_reader_required = require_role([UserRole.CUSTOMER, UserRole.ADMIN])
admin_required = require_role([UserRole.ADMIN])

PREPAYMENT_STATUSES = {
    PrintRequestStatus.SUBMITTED.value,
    PrintRequestStatus.UNDER_REVIEW.value,
    PrintRequestStatus.INFORMATION_REQUIRED.value,
    PrintRequestStatus.AWAITING_QUOTE_APPROVAL.value,
    PrintRequestStatus.QUOTE_CHANGES_REQUESTED.value,
    PrintRequestStatus.AWAITING_PAYMENT.value,
    PrintRequestStatus.PAYMENT_VERIFICATION.value,
}
TERMINAL_STATUSES = {
    PrintRequestStatus.DELIVERED.value,
    PrintRequestStatus.REJECTED.value,
    PrintRequestStatus.CANCELLED.value,
}
QUOTE_STATUSES = {
    PrintRequestStatus.UNDER_REVIEW.value,
    PrintRequestStatus.QUOTE_CHANGES_REQUESTED.value,
    PrintRequestStatus.AWAITING_QUOTE_APPROVAL.value,
}
ADMIN_TRANSITIONS = {
    "submitted": {"under_review"},
    "under_review": {"information_required"},
    "information_required": set(),
    "quote_changes_requested": set(),
    "awaiting_quote_approval": set(),
    "awaiting_payment": {"payment_verification", "payment_confirmed"},
    "payment_verification": {"payment_confirmed", "awaiting_payment"},
    "payment_confirmed": {"in_production"},
    "in_production": {"production_paused", "shipped"},
    "production_paused": {"in_production"},
    "shipped": {"delivered"},
}


def _request_object_id(request_id: str) -> ObjectId:
    try:
        return ObjectId(request_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Print request not found.")


def _event(kind: str, actor: Dict[str, Any], message: str, request_status: str, now: datetime) -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "kind": kind,
        "actor_role": actor.get("role", "CUSTOMER").lower(),
        "actor_name": actor.get("name", ""),
        "message": message,
        "status": request_status,
        "created_at": now,
    }


def _allowed_transitions(request_status: str, is_admin: bool) -> List[str]:
    if not is_admin:
        return []
    transitions = set(ADMIN_TRANSITIONS.get(request_status, set()))
    if request_status in PREPAYMENT_STATUSES:
        transitions.add(PrintRequestStatus.REJECTED.value)
    if request_status not in TERMINAL_STATUSES:
        transitions.add(PrintRequestStatus.CANCELLED.value)
    return sorted(transitions)


def _allowed_actions(request_status: str, is_admin: bool) -> List[str]:
    if request_status in TERMINAL_STATUSES:
        return []
    actions = ["message"]
    if is_admin:
        if request_status in QUOTE_STATUSES:
            actions.append("publish_quote")
    else:
        if request_status in PREPAYMENT_STATUSES:
            actions.append("cancel")
        if request_status == PrintRequestStatus.AWAITING_QUOTE_APPROVAL.value:
            actions.extend(["approve_quote", "request_changes"])
    return actions


def _format_request(doc: Dict[str, Any], is_admin: bool) -> PrintRequest:
    actions = _allowed_actions(doc["status"], is_admin)
    if "approve_quote" in actions:
        quote = doc.get("quotes", [])[-1] if doc.get("quotes") else None
        valid_until = quote["valid_until"] if quote else None
        if valid_until is not None and valid_until.tzinfo is None:
            valid_until = valid_until.replace(tzinfo=timezone.utc)
        if not quote or quote.get("approved_at") or valid_until <= datetime.now(timezone.utc):
            actions.remove("approve_quote")
    quotes = [
        QuoteResponse(
            version=quote["version"],
            amountCents=quote["amount_cents"],
            currency=quote["currency"],
            scope=quote["scope"],
            leadDays=quote["lead_days"],
            validUntil=iso_utc(quote["valid_until"]),
            createdAt=iso_utc(quote["created_at"]),
            approvedAt=iso_utc(quote["approved_at"]) if quote.get("approved_at") else None,
        )
        for quote in doc.get("quotes", [])
    ]
    history = [
        HistoryResponse(
            id=item["id"],
            kind=item["kind"],
            actorRole=item["actor_role"],
            actorName=item["actor_name"],
            message=item["message"],
            status=item["status"],
            createdAt=iso_utc(item["created_at"]),
        )
        for item in doc.get("history", [])
    ]
    return PrintRequest(
        id=str(doc["_id"]),
        reference=doc["reference"],
        ownerId=doc["owner_id"],
        customerName=doc["customer_name"],
        customerEmail=doc["customer_email"],
        title=doc["title"],
        description=doc["description"],
        quantity=doc["quantity"],
        dimensions=doc["dimensions"],
        material=doc.get("material"),
        color=doc.get("color"),
        referenceLinks=doc.get("reference_links", []),
        status=doc["status"],
        version=doc["version"],
        createdAt=iso_utc(doc["created_at"]),
        updatedAt=iso_utc(doc["updated_at"]),
        quotes=quotes,
        history=history,
        trackingUrl=doc.get("tracking_url"),
        estimatedShipping=(
            doc["estimated_shipping"].isoformat()
            if hasattr(doc.get("estimated_shipping"), "isoformat")
            else doc.get("estimated_shipping")
        ),
        allowedTransitions=_allowed_transitions(doc["status"], is_admin),
        allowedActions=actions,
    )


def _list_filter(
    owner_id: Optional[str],
    query: Optional[str],
    request_status: Optional[PrintRequestStatus],
) -> Dict[str, Any]:
    clauses: List[Dict[str, Any]] = []
    if owner_id is not None:
        clauses.append({"owner_id": owner_id})
    if request_status is not None:
        clauses.append({"status": request_status.value})
    if query and query.strip():
        pattern = re.escape(query.strip())
        clauses.append({
            "$or": [
                {"reference": {"$regex": pattern, "$options": "i"}},
                {"title": {"$regex": pattern, "$options": "i"}},
                {"customer_name": {"$regex": pattern, "$options": "i"}},
                {"customer_email": {"$regex": pattern, "$options": "i"}},
            ]
        })
    return {"$and": clauses} if clauses else {}


async def _list_requests(
    db: Any,
    owner_id: Optional[str],
    page: int,
    page_size: int,
    query: Optional[str],
    request_status: Optional[PrintRequestStatus],
    sort: RequestSort,
    is_admin: bool,
) -> PrintRequestPage:
    filters = _list_filter(owner_id, query, request_status)
    direction = -1 if sort == RequestSort.NEWEST else 1
    total = await db.print_requests.count_documents(filters)
    docs = await db.print_requests.find(filters).sort(
        [("created_at", direction), ("_id", direction)]
    ).skip((page - 1) * page_size).limit(page_size).to_list(length=page_size)
    return PrintRequestPage(
        items=[_format_request(doc, is_admin) for doc in docs],
        total=total,
        page=page,
        pageSize=page_size,
    )


async def _get_request(db: Any, request_id: str, owner_id: Optional[str] = None) -> Dict[str, Any]:
    filters: Dict[str, Any] = {"_id": _request_object_id(request_id)}
    if owner_id is not None:
        filters["owner_id"] = owner_id
    doc = await db.print_requests.find_one(filters)
    if not doc:
        raise HTTPException(status_code=404, detail="Print request not found.")
    return doc


def _stale_or_invalid() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="The request changed or this action is not valid for its current state.",
    )


async def _mutate(
    db: Any,
    request_id: str,
    version: int,
    owner_id: Optional[str],
    status_filter: Optional[str],
    updates: Dict[str, Any],
    event: Dict[str, Any],
    array_filters: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    query: Dict[str, Any] = {"_id": _request_object_id(request_id), "version": version}
    if owner_id is not None:
        query["owner_id"] = owner_id
    if status_filter is not None:
        query["status"] = status_filter
    result = await db.print_requests.find_one_and_update(
        query,
        {
            "$set": {**updates, "updated_at": event["created_at"]},
            "$inc": {"version": 1},
            "$push": {"history": event},
        },
        return_document=ReturnDocument.AFTER,
        array_filters=array_filters,
    )
    if result is None:
        raise _stale_or_invalid()
    return result


@customer_router.post("", response_model=PrintRequest, response_model_exclude_none=True, status_code=status.HTTP_201_CREATED)
async def create_print_request(
    payload: RequestInput,
    current_user: Dict[str, Any] = Depends(customer_required),
    db=Depends(get_database),
):
    now = datetime.now(timezone.utc)
    request_id = ObjectId()
    request_status = PrintRequestStatus.SUBMITTED.value
    doc: Dict[str, Any] = {
        "_id": request_id,
        "reference": "",
        "owner_id": str(current_user["_id"]),
        "customer_name": current_user.get("name", ""),
        "customer_email": current_user.get("email", ""),
        "title": payload.title,
        "description": payload.description,
        "quantity": payload.quantity,
        "dimensions": payload.dimensions,
        "material": payload.material,
        "color": payload.color,
        "reference_links": payload.referenceLinks,
        "status": request_status,
        "version": 1,
        "created_at": now,
        "updated_at": now,
        "quotes": [],
        "history": [
            _event("request_submitted", current_user, "Custom print request submitted.", request_status, now)
        ],
    }
    for _ in range(3):
        doc["reference"] = f"CR-{now:%y%m}-{secrets.token_hex(4).upper()}"
        try:
            await db.print_requests.insert_one(doc)
            return _format_request(doc, False)
        except DuplicateKeyError:
            continue
    raise HTTPException(status_code=503, detail="Could not allocate a unique request reference.")


@customer_router.get("", response_model=PrintRequestPage, response_model_exclude_none=True)
async def list_customer_requests(
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    q: Optional[str] = Query(None, max_length=200),
    request_status: Optional[PrintRequestStatus] = Query(None, alias="status"),
    sort: RequestSort = Query(RequestSort.NEWEST),
    current_user: Dict[str, Any] = Depends(request_reader_required),
    db=Depends(get_database),
):
    is_admin = current_user.get("role") == UserRole.ADMIN.value
    return await _list_requests(
        db, str(current_user["_id"]), page, pageSize, q, request_status, sort, is_admin
    )


@customer_router.get("/{request_id}", response_model=PrintRequest, response_model_exclude_none=True)
async def get_customer_request(
    request_id: str,
    current_user: Dict[str, Any] = Depends(request_reader_required),
    db=Depends(get_database),
):
    doc = await _get_request(db, request_id, str(current_user["_id"]))
    return _format_request(doc, current_user.get("role") == UserRole.ADMIN.value)


@customer_router.post("/{request_id}/messages", response_model=PrintRequest, response_model_exclude_none=True)
async def customer_message(
    request_id: str,
    payload: MessageInput,
    current_user: Dict[str, Any] = Depends(customer_required),
    db=Depends(get_database),
):
    doc = await _get_request(db, request_id, str(current_user["_id"]))
    if doc["status"] in TERMINAL_STATUSES:
        raise _stale_or_invalid()
    new_status = (
        PrintRequestStatus.UNDER_REVIEW.value
        if doc["status"] == PrintRequestStatus.INFORMATION_REQUIRED.value
        else doc["status"]
    )
    now = datetime.now(timezone.utc)
    updated = await _mutate(
        db,
        request_id,
        payload.version,
        str(current_user["_id"]),
        doc["status"],
        {"status": new_status},
        _event("customer_message", current_user, payload.message, new_status, now),
    )
    return _format_request(updated, False)


@customer_router.post("/{request_id}/actions", response_model=PrintRequest, response_model_exclude_none=True)
async def customer_action(
    request_id: str,
    payload: CustomerActionInput,
    current_user: Dict[str, Any] = Depends(customer_required),
    db=Depends(get_database),
):
    doc = await _get_request(db, request_id, str(current_user["_id"]))
    current_status = doc["status"]
    now = datetime.now(timezone.utc)
    updates: Dict[str, Any]
    event_kind: str
    target_status: str
    filters: Optional[List[Dict[str, Any]]] = None

    if payload.action == CustomerAction.CANCEL:
        if current_status not in PREPAYMENT_STATUSES:
            raise _stale_or_invalid()
        target_status = PrintRequestStatus.CANCELLED.value
        event_kind = "customer_cancelled"
        updates = {"status": target_status}
    elif payload.action in {CustomerAction.APPROVE_QUOTE, CustomerAction.REQUEST_CHANGES}:
        if current_status != PrintRequestStatus.AWAITING_QUOTE_APPROVAL.value or not doc.get("quotes"):
            raise _stale_or_invalid()
        latest_quote = doc["quotes"][-1]
        if payload.quoteVersion != latest_quote["version"]:
            raise _stale_or_invalid()
        if payload.action == CustomerAction.APPROVE_QUOTE:
            valid_until = latest_quote["valid_until"]
            if valid_until.tzinfo is None:
                valid_until = valid_until.replace(tzinfo=timezone.utc)
            if valid_until <= now or latest_quote.get("approved_at"):
                raise _stale_or_invalid()
            target_status = PrintRequestStatus.AWAITING_PAYMENT.value
            event_kind = "quote_approved"
            updates = {"status": target_status}
            filters = [{"quote.version": payload.quoteVersion}]
            updates["quotes.$[quote].approved_at"] = now
        else:
            target_status = PrintRequestStatus.QUOTE_CHANGES_REQUESTED.value
            event_kind = "quote_changes_requested"
            updates = {"status": target_status}
    else:
        raise _stale_or_invalid()

    updated = await _mutate(
        db,
        request_id,
        payload.version,
        str(current_user["_id"]),
        current_status,
        updates,
        _event(
            event_kind, current_user,
            payload.message or f"Quotation version {payload.quoteVersion} approved.",
            target_status, now,
        ),
        filters,
    )
    return _format_request(updated, False)


@admin_router.get("", response_model=PrintRequestPage, response_model_exclude_none=True)
async def list_admin_requests(
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    q: Optional[str] = Query(None, max_length=200),
    request_status: Optional[PrintRequestStatus] = Query(None, alias="status"),
    sort: RequestSort = Query(RequestSort.NEWEST),
    _admin: Dict[str, Any] = Depends(admin_required),
    db=Depends(get_database),
):
    return await _list_requests(db, None, page, pageSize, q, request_status, sort, True)


@admin_router.get("/{request_id}", response_model=PrintRequest, response_model_exclude_none=True)
async def get_admin_request(
    request_id: str,
    _admin: Dict[str, Any] = Depends(admin_required),
    db=Depends(get_database),
):
    return _format_request(await _get_request(db, request_id), True)


@admin_router.post("/{request_id}/messages", response_model=PrintRequest, response_model_exclude_none=True)
async def admin_message(
    request_id: str,
    payload: MessageInput,
    current_user: Dict[str, Any] = Depends(admin_required),
    db=Depends(get_database),
):
    doc = await _get_request(db, request_id)
    if doc["status"] in TERMINAL_STATUSES:
        raise _stale_or_invalid()
    now = datetime.now(timezone.utc)
    updated = await _mutate(
        db,
        request_id,
        payload.version,
        None,
        doc["status"],
        {"status": doc["status"]},
        _event("admin_message", current_user, payload.message, doc["status"], now),
    )
    return _format_request(updated, True)


@admin_router.post("/{request_id}/quote", response_model=PrintRequest, response_model_exclude_none=True)
async def publish_quote(
    request_id: str,
    payload: QuoteInput,
    current_user: Dict[str, Any] = Depends(admin_required),
    db=Depends(get_database),
):
    doc = await _get_request(db, request_id)
    latest_version = doc["quotes"][-1]["version"] if doc.get("quotes") else 0
    now = datetime.now(timezone.utc)
    if (
        doc["status"] not in QUOTE_STATUSES
        or payload.version != doc["version"]
        or payload.validUntil <= now
    ):
        raise _stale_or_invalid()
    quote_version = latest_version + 1
    quote = {
        "version": quote_version,
        "amount_cents": payload.amountCents,
        "currency": payload.currency,
        "scope": payload.scope,
        "lead_days": payload.leadDays,
        "valid_until": payload.validUntil,
        "created_at": now,
    }
    target_status = PrintRequestStatus.AWAITING_QUOTE_APPROVAL.value
    update = await db.print_requests.find_one_and_update(
        {
            "_id": _request_object_id(request_id),
            "version": payload.version,
            "status": doc["status"],
        },
        {
            "$push": {"quotes": quote, "history": _event(
                "quote_published", current_user, f"Quotation version {quote_version} published.",
                target_status, now
            )},
            "$set": {"status": target_status, "updated_at": now},
            "$inc": {"version": 1},
        },
        return_document=ReturnDocument.AFTER,
    )
    if update is None:
        raise _stale_or_invalid()
    return _format_request(update, True)


@admin_router.post("/{request_id}/transition", response_model=PrintRequest, response_model_exclude_none=True)
async def transition_request(
    request_id: str,
    payload: AdminTransitionInput,
    current_user: Dict[str, Any] = Depends(admin_required),
    db=Depends(get_database),
):
    doc = await _get_request(db, request_id)
    current_status = doc["status"]
    target_status = payload.status.value
    allowed = _allowed_transitions(current_status, True)
    if target_status not in allowed:
        raise _stale_or_invalid()
    if target_status == PrintRequestStatus.REJECTED.value and current_status not in PREPAYMENT_STATUSES:
        raise _stale_or_invalid()
    now = datetime.now(timezone.utc)
    updates: Dict[str, Any] = {"status": target_status}
    if target_status == PrintRequestStatus.SHIPPED.value:
        updates["tracking_url"] = payload.trackingUrl
        if payload.estimatedShipping:
            updates["estimated_shipping"] = payload.estimatedShipping.isoformat()
    updated = await _mutate(
        db,
        request_id,
        payload.version,
        None,
        current_status,
        updates,
        _event("status_changed", current_user, payload.message, target_status, now),
    )
    return _format_request(updated, True)
