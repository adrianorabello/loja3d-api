import re
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.database import get_database
from app.models.product import ProductResponse, format_product_document

router = APIRouter(prefix="/products", tags=["Public Products"])


@router.get("", response_model=List[ProductResponse])
async def get_public_products(
    q: Optional[str] = Query(None, description="Search query across product names and descriptions"),
    category: Optional[str] = Query(None, description="Filter by category ID"),
    sort: Optional[str] = Query("newest", description="Sort option: newest, price-asc, price-desc, name-asc, name-desc"),
    db=Depends(get_database)
):
    """Fetch active products for the public storefront with optional search, filtering and sorting."""
    filter_query = {"active": True}

    if category:
        filter_query["category_id"] = category

    if q and q.strip():
        search_term = q.strip()
        escaped = re.escape(search_term)
        regex = {"$regex": escaped, "$options": "i"}
        filter_query["$or"] = [
            {"name.pt-PT": regex},
            {"name.en": regex},
            {"description.pt-PT": regex},
            {"description.en": regex},
            {"slug": regex}
        ]

    # Resolve sort ordering
    sort_mapping = {
        "newest": [("created_at", -1)],
        "price-asc": [("price_cents", 1)],
        "price-desc": [("price_cents", -1)],
        "name-asc": [("name.pt-PT", 1)],
        "name-desc": [("name.pt-PT", -1)]
    }
    sort_spec = sort_mapping.get(sort, [("created_at", -1)])

    cursor = db.products.find(filter_query).sort(sort_spec)
    docs = await cursor.to_list(length=200)

    return [format_product_document(doc) for doc in docs]


@router.get("/{slug}", response_model=ProductResponse)
async def get_product_by_slug(slug: str, db=Depends(get_database)):
    """Fetch a single active product by its URL slug."""
    doc = await db.products.find_one({"slug": slug, "active": True})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto não encontrado."
        )

    return format_product_document(doc)
