from datetime import datetime, timezone
import secrets
from typing import Any, Dict, List, Optional
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from app.core.dependencies import require_role
from app.database import get_database
from app.models.product import (
    ProductCreate,
    ProductResponse,
    ProductUpdate,
    format_product_document,
)
from app.models.user import UserRole

router = APIRouter(tags=["Admin Products"])

admin_required = require_role([UserRole.ADMIN])


def get_product_query(id_or_slug: str) -> Dict[str, Any]:
    """Build a MongoDB query that matches either a custom string id, an ObjectId, or a slug."""
    try:
        oid = ObjectId(id_or_slug)
        return {"$or": [{"id": id_or_slug}, {"_id": oid}]}
    except Exception:
        return {"$or": [{"id": id_or_slug}, {"_id": id_or_slug}]}


# -----------------------------------------------------------------------------------------------------
# @ GET All Products (Admin)
# -----------------------------------------------------------------------------------------------------
@router.get("/admin/products", response_model=List[ProductResponse], dependencies=[Depends(admin_required)])
async def get_all_products_admin(db=Depends(get_database)):
    """Fetch every product in the database (both active and inactive) for the admin table."""
    cursor = db.products.find({}).sort("created_at", -1)
    docs = await cursor.to_list(length=500)
    return [format_product_document(doc) for doc in docs]


# -----------------------------------------------------------------------------------------------------
# @ GET Single Product (Admin / Edit Resolver)
# -----------------------------------------------------------------------------------------------------
@router.get("/admin/products/{id}", response_model=ProductResponse, dependencies=[Depends(admin_required)])
@router.get("/product/{id}", response_model=ProductResponse, dependencies=[Depends(admin_required)])
async def get_product_by_id(id: str, db=Depends(get_database)):
    """Fetch a single product by its unique ID for editing."""
    query = get_product_query(id)
    doc = await db.products.find_one(query)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto não encontrado."
        )
    return format_product_document(doc)


# -----------------------------------------------------------------------------------------------------
# @ POST Create Product
# -----------------------------------------------------------------------------------------------------
@router.post(
    "/admin/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(admin_required)]
)
@router.post(
    "/product",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(admin_required)]
)
async def create_product(
    request: Request,
    db=Depends(get_database)
):
    """Create a new product. Accepts either raw ProductCreate or { product: ProductCreate }."""
    raw_body = await request.json()
    product_data = raw_body.get("product", raw_body)
    payload = ProductCreate(**product_data)

    slug_normalized = payload.slug.strip().lower()

    # Check for slug collision
    existing = await db.products.find_one({"slug": slug_normalized})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="O slug indicado já se encontra em uso."
        )

    now = datetime.now(timezone.utc)
    custom_id = f"prd-{secrets.token_hex(4)}"

    doc = {
        "id": custom_id,
        "slug": slug_normalized,
        "name": payload.name,
        "description": payload.description,
        "category_id": payload.categoryId,
        "price_cents": int(round(payload.price * 100)),
        "currency": payload.currency,
        "dimensions": payload.dimensions.model_dump() if payload.dimensions else None,
        "colors": [c.model_dump() for c in payload.colors],
        "images": payload.images,
        "stock": payload.stock,
        "active": payload.active,
        "made_to_order": payload.madeToOrder,
        "featured": payload.featured,
        "created_at": now,
        "updated_at": now
    }

    result = await db.products.insert_one(doc)
    doc["_id"] = result.inserted_id

    return format_product_document(doc)


# -----------------------------------------------------------------------------------------------------
# @ PATCH Update Product
# -----------------------------------------------------------------------------------------------------
@router.patch("/admin/products/{id}", response_model=ProductResponse, dependencies=[Depends(admin_required)])
@router.patch("/product", response_model=ProductResponse, dependencies=[Depends(admin_required)])
async def update_product(
    request: Request,
    id: Optional[str] = None,
    db=Depends(get_database)
):
    """Update a product. Supports REST URL /admin/products/{id} and legacy body { id, product }."""
    raw_body = await request.json()
    target_id = id or raw_body.get("id")
    if not target_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Identificador do produto é obrigatório."
        )

    product_data = raw_body.get("product", raw_body)
    payload = ProductUpdate(**product_data)

    query = get_product_query(target_id)
    existing = await db.products.find_one(query)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto não encontrado."
        )

    update_fields: Dict[str, Any] = {}

    if payload.slug is not None:
        slug_norm = payload.slug.strip().lower()
        if slug_norm != existing.get("slug"):
            conflict = await db.products.find_one({"slug": slug_norm, "_id": {"$ne": existing["_id"]}})
            if conflict:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="O slug indicado já se encontra em uso."
                )
            update_fields["slug"] = slug_norm

    if payload.name is not None:
        update_fields["name"] = payload.name
    if payload.description is not None:
        update_fields["description"] = payload.description
    if payload.categoryId is not None:
        update_fields["category_id"] = payload.categoryId
    if payload.price is not None:
        update_fields["price_cents"] = int(round(payload.price * 100))
    if payload.dimensions is not None:
        update_fields["dimensions"] = payload.dimensions.model_dump()
    if payload.colors is not None:
        update_fields["colors"] = [c.model_dump() for c in payload.colors]
    if payload.images is not None:
        update_fields["images"] = payload.images
    if payload.stock is not None:
        update_fields["stock"] = payload.stock
    if payload.active is not None:
        update_fields["active"] = payload.active
    if payload.madeToOrder is not None:
        update_fields["made_to_order"] = payload.madeToOrder
    if payload.featured is not None:
        update_fields["featured"] = payload.featured

    update_fields["updated_at"] = datetime.now(timezone.utc)

    await db.products.update_one(
        {"_id": existing["_id"]},
        {"$set": update_fields}
    )

    updated_doc = await db.products.find_one({"_id": existing["_id"]})
    return format_product_document(updated_doc)


# -----------------------------------------------------------------------------------------------------
# @ DELETE Remove Product
# -----------------------------------------------------------------------------------------------------
@router.delete("/admin/products/{id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(admin_required)])
@router.delete("/product", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(admin_required)])
async def delete_product(
    id: Optional[str] = None,
    product_id_param: Optional[str] = Query(None, alias="id"),
    db=Depends(get_database)
):
    """Delete a product by ID, supporting either path param or query param ?id=..."""
    target_id = id or product_id_param
    if not target_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Identificador do produto é obrigatório."
        )

    query = get_product_query(target_id)
    result = await db.products.delete_one(query)
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto não encontrado."
        )

    return None
