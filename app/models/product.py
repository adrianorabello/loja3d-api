from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ProductColor(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: Dict[str, str]
    hex: str


class ProductDimensions(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    width: float = Field(..., gt=0)
    height: float = Field(..., gt=0)
    depth: float = Field(..., gt=0)
    unit: str = "mm"


class ProductCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    slug: str = Field(..., min_length=2, max_length=150)
    name: Dict[str, str]
    description: Dict[str, str] = Field(default_factory=dict)
    categoryId: str
    price: float = Field(..., gt=0)
    currency: str = "EUR"
    dimensions: Optional[ProductDimensions] = None
    colors: List[ProductColor] = Field(default_factory=list)
    images: List[str] = Field(default_factory=list)
    stock: int = Field(0, ge=0)
    active: bool = True
    madeToOrder: bool = False
    featured: bool = False


class ProductUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    slug: Optional[str] = None
    name: Optional[Dict[str, str]] = None
    description: Optional[Dict[str, str]] = None
    categoryId: Optional[str] = None
    price: Optional[float] = None
    dimensions: Optional[ProductDimensions] = None
    colors: Optional[List[ProductColor]] = None
    images: Optional[List[str]] = None
    stock: Optional[int] = None
    active: Optional[bool] = None
    madeToOrder: Optional[bool] = None
    featured: Optional[bool] = None


class ProductResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    slug: str
    name: Dict[str, str]
    description: Dict[str, str]
    categoryId: str
    price: float
    currency: str = "EUR"
    dimensions: Optional[ProductDimensions] = None
    colors: List[ProductColor] = Field(default_factory=list)
    images: List[str] = Field(default_factory=list)
    stock: int
    active: bool
    madeToOrder: bool
    featured: bool
    createdAt: str


def format_product_document(doc: Dict[str, Any]) -> ProductResponse:
    """Format a raw MongoDB product document into a typed ProductResponse matching Angular model."""
    doc_id = str(doc.get("id") or doc.get("_id"))

    # Convert integer cents to EUR float with 2 decimal places
    if "price_cents" in doc:
        price = round(doc["price_cents"] / 100.0, 2)
    else:
        price = round(float(doc.get("price", 0.0)), 2)

    created_at = doc.get("created_at") or doc.get("createdAt")
    if isinstance(created_at, datetime):
        created_at_str = created_at.isoformat()
    elif isinstance(created_at, str):
        created_at_str = created_at
    else:
        created_at_str = datetime.now(timezone.utc).isoformat()

    dimensions_raw = doc.get("dimensions")
    dimensions = None
    if dimensions_raw and isinstance(dimensions_raw, dict):
        dimensions = ProductDimensions(
            width=float(dimensions_raw.get("width", 0)),
            height=float(dimensions_raw.get("height", 0)),
            depth=float(dimensions_raw.get("depth", 0)),
            unit=dimensions_raw.get("unit", "mm")
        )

    colors_raw = doc.get("colors", [])
    colors = [
        ProductColor(
            id=c.get("id", ""),
            name=c.get("name", {}),
            hex=c.get("hex", "#ffffff")
        )
        for c in colors_raw
    ]

    return ProductResponse(
        id=doc_id,
        slug=doc.get("slug", ""),
        name=doc.get("name", {}),
        description=doc.get("description", {}),
        categoryId=doc.get("category_id") or doc.get("categoryId", ""),
        price=price,
        currency=doc.get("currency", "EUR"),
        dimensions=dimensions,
        colors=colors,
        images=doc.get("images", []),
        stock=int(doc.get("stock", 0)),
        active=bool(doc.get("active", True)),
        madeToOrder=bool(doc.get("made_to_order", doc.get("madeToOrder", False))),
        featured=bool(doc.get("featured", False)),
        createdAt=created_at_str
    )
