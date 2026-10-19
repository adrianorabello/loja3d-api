from typing import List
from fastapi import APIRouter, Depends
from app.database import get_database
from app.models.category import Category

router = APIRouter(prefix="/categories", tags=["Categories"])

INITIAL_CATEGORIES = [
    {
        "id": "cat-figuras",
        "slug": "figuras",
        "name": {
            "pt-PT": "Figuras e Colecionáveis",
            "en": "Figures & Collectibles"
        }
    },
    {
        "id": "cat-acessorios",
        "slug": "acessorios",
        "name": {
            "pt-PT": "Acessórios",
            "en": "Accessories"
        }
    },
    {
        "id": "cat-casa-escritorio",
        "slug": "casa-e-escritorio",
        "name": {
            "pt-PT": "Casa e Escritório",
            "en": "Home & Office"
        }
    },
    {
        "id": "cat-personalizados",
        "slug": "personalizados",
        "name": {
            "pt-PT": "Personalizados",
            "en": "Personalised"
        }
    }
]


@router.get("", response_model=List[Category])
async def list_categories(db=Depends(get_database)):
    """List product categories. Auto-seeds defaults if the collection is empty."""
    count = await db.categories.count_documents({})
    if count == 0:
        await db.categories.insert_many(INITIAL_CATEGORIES)

    cursor = db.categories.find({}, {"_id": 0}).sort("slug", 1)
    items = await cursor.to_list(length=100)
    return [Category(**item) for item in items]
