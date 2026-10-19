import logging
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.config import settings
from app.core.security import hash_password
from app.models.user import UserRole
from app.routers.categories import INITIAL_CATEGORIES

logger = logging.getLogger("loja3d.bootstrap")

DEMO_PRODUCTS = [
    {
        "id": "prd-0001",
        "slug": "dragao-articulado",
        "name": {
            "pt-PT": "Dragão Articulado",
            "en": "Articulated Dragon"
        },
        "description": {
            "pt-PT": "Dragão impresso numa só peça, com elos articulados que se movem sem necessitar de montagem. Cerca de 24 cm da cabeça à cauda.",
            "en": "Dragon printed in a single piece, with articulated links that move freely and need no assembly. Roughly 24 cm nose to tail."
        },
        "category_id": "cat-figuras",
        "price_cents": 2490,
        "currency": "EUR",
        "dimensions": {"width": 120.0, "height": 60.0, "depth": 240.0, "unit": "mm"},
        "colors": [
            {"id": "mint", "name": {"pt-PT": "Menta", "en": "Mint"}, "hex": "#5EEAD4"},
            {"id": "preto", "name": {"pt-PT": "Preto", "en": "Black"}, "hex": "#1E293B"},
            {"id": "rosa", "name": {"pt-PT": "Rosa", "en": "Rose"}, "hex": "#FB7185"}
        ],
        "images": [
            "assets/images/clara-rosa/products/dragao-articulado-01.svg",
            "assets/images/clara-rosa/products/dragao-articulado-02.svg"
        ],
        "stock": 8,
        "active": True,
        "made_to_order": False,
        "featured": True,
        "created_at": datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc)
    },
    {
        "id": "prd-0002",
        "slug": "porta-chaves-personalizado",
        "name": {
            "pt-PT": "Porta-chaves Personalizado",
            "en": "Personalised Keychain"
        },
        "description": {
            "pt-PT": "Porta-chaves com o nome ou a palavra que escolher, impresso em duas cores. Indique o texto nas notas da encomenda.",
            "en": "Keychain carrying the name or word of your choice, printed in two colours. Add the text in your order notes."
        },
        "category_id": "cat-personalizados",
        "price_cents": 750,
        "currency": "EUR",
        "dimensions": {"width": 25.0, "height": 6.0, "depth": 70.0, "unit": "mm"},
        "colors": [
            {"id": "mint", "name": {"pt-PT": "Menta", "en": "Mint"}, "hex": "#5EEAD4"},
            {"id": "branco", "name": {"pt-PT": "Branco", "en": "White"}, "hex": "#F8FAFC"},
            {"id": "preto", "name": {"pt-PT": "Preto", "en": "Black"}, "hex": "#1E293B"},
            {"id": "rosa", "name": {"pt-PT": "Rosa", "en": "Rose"}, "hex": "#FB7185"},
            {"id": "ambar", "name": {"pt-PT": "Âmbar", "en": "Amber"}, "hex": "#FBBF24"}
        ],
        "images": [
            "assets/images/clara-rosa/products/porta-chaves-personalizado-01.svg",
            "assets/images/clara-rosa/products/porta-chaves-personalizado-02.svg"
        ],
        "stock": 0,
        "active": True,
        "made_to_order": True,
        "featured": True,
        "created_at": datetime(2026, 10, 2, 9, 30, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 10, 2, 9, 30, tzinfo=timezone.utc)
    },
    {
        "id": "prd-0003",
        "slug": "suporte-telemovel",
        "name": {
            "pt-PT": "Suporte para Telemóvel",
            "en": "Phone Stand"
        },
        "description": {
            "pt-PT": "Suporte de secretária com inclinação de 60°, compatível com telemóveis até 9 mm de espessura. Base com apoio antiderrapante.",
            "en": "Desk stand angled at 60°, fits phones up to 9 mm thick. Non-slip pads on the base."
        },
        "category_id": "cat-casa-escritorio",
        "price_cents": 1200,
        "currency": "EUR",
        "dimensions": {"width": 80.0, "height": 95.0, "depth": 85.0, "unit": "mm"},
        "colors": [
            {"id": "branco", "name": {"pt-PT": "Branco", "en": "White"}, "hex": "#F8FAFC"},
            {"id": "preto", "name": {"pt-PT": "Preto", "en": "Black"}, "hex": "#1E293B"},
            {"id": "mint", "name": {"pt-PT": "Menta", "en": "Mint"}, "hex": "#5EEAD4"}
        ],
        "images": [
            "assets/images/clara-rosa/products/suporte-telemovel-01.svg",
            "assets/images/clara-rosa/products/suporte-telemovel-02.svg"
        ],
        "stock": 2,
        "active": True,
        "made_to_order": False,
        "featured": False,
        "created_at": datetime(2026, 8, 14, 15, 45, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 8, 14, 15, 45, tzinfo=timezone.utc)
    },
    {
        "id": "prd-0004",
        "slug": "miniatura-decorativa",
        "name": {
            "pt-PT": "Miniatura Decorativa",
            "en": "Decorative Miniature"
        },
        "description": {
            "pt-PT": "Miniatura de 7 cm sobre base redonda, impressa em camadas de 0,1 mm para um acabamento fino. Ideal para prateleira ou secretária.",
            "en": ""
        },
        "category_id": "cat-figuras",
        "price_cents": 1575,
        "currency": "EUR",
        "dimensions": {"width": 45.0, "height": 70.0, "depth": 45.0, "unit": "mm"},
        "colors": [
            {"id": "branco", "name": {"pt-PT": "Branco", "en": "White"}, "hex": "#F8FAFC"},
            {"id": "mint", "name": {"pt-PT": "Menta", "en": "Mint"}, "hex": "#5EEAD4"}
        ],
        "images": [
            "assets/images/clara-rosa/products/miniatura-decorativa-01.svg",
            "assets/images/clara-rosa/products/miniatura-decorativa-02.svg"
        ],
        "stock": 0,
        "active": True,
        "made_to_order": False,
        "featured": False,
        "created_at": datetime(2026, 7, 21, 11, 10, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 7, 21, 11, 10, tzinfo=timezone.utc)
    },
    {
        "id": "prd-0005",
        "slug": "porta-lapis",
        "name": {
            "pt-PT": "Porta-lápis",
            "en": "Pencil Holder"
        },
        "description": {
            "pt-PT": "Porta-lápis hexagonal com três compartimentos, 10 cm de altura. Paredes com textura de linhas de impressão visível.",
            "en": "Hexagonal pencil holder with three compartments, 10 cm tall. Walls keep a visible layer-line texture."
        },
        "category_id": "cat-casa-escritorio",
        "price_cents": 1125,
        "currency": "EUR",
        "dimensions": {"width": 90.0, "height": 100.0, "depth": 80.0, "unit": "mm"},
        "colors": [
            {"id": "mint", "name": {"pt-PT": "Menta", "en": "Mint"}, "hex": "#5EEAD4"},
            {"id": "rosa", "name": {"pt-PT": "Rosa", "en": "Rose"}, "hex": "#FB7185"},
            {"id": "ambar", "name": {"pt-PT": "Âmbar", "en": "Amber"}, "hex": "#FBBF24"}
        ],
        "images": [
            "assets/images/clara-rosa/products/porta-lapis-01.svg",
            "assets/images/clara-rosa/products/porta-lapis-02.svg"
        ],
        "stock": 14,
        "active": True,
        "made_to_order": False,
        "featured": False,
        "created_at": datetime(2026, 9, 5, 8, 20, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 9, 5, 8, 20, tzinfo=timezone.utc)
    },
    {
        "id": "prd-0006",
        "slug": "placa-de-nome",
        "name": {
            "pt-PT": "Placa de Nome",
            "en": "Nameplate"
        },
        "description": {
            "pt-PT": "Placa de porta ou secretária com texto em relevo, até 18 caracteres. Inclui fita adesiva dupla face.",
            "en": "Door or desk plate with raised lettering, up to 18 characters. Double-sided tape included."
        },
        "category_id": "cat-personalizados",
        "price_cents": 1840,
        "currency": "EUR",
        "dimensions": {"width": 180.0, "height": 45.0, "depth": 10.0, "unit": "mm"},
        "colors": [
            {"id": "branco", "name": {"pt-PT": "Branco", "en": "White"}, "hex": "#F8FAFC"},
            {"id": "preto", "name": {"pt-PT": "Preto", "en": "Black"}, "hex": "#1E293B"},
            {"id": "mint", "name": {"pt-PT": "Menta", "en": "Mint"}, "hex": "#5EEAD4"},
            {"id": "rosa", "name": {"pt-PT": "Rosa", "en": "Rose"}, "hex": "#FB7185"}
        ],
        "images": [
            "assets/images/clara-rosa/products/placa-de-nome-01.svg",
            "assets/images/clara-rosa/products/placa-de-nome-02.svg"
        ],
        "stock": 5,
        "active": True,
        "made_to_order": True,
        "featured": True,
        "created_at": datetime(2026, 10, 8, 16, 5, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 10, 8, 16, 5, tzinfo=timezone.utc)
    },
    {
        "id": "prd-0007",
        "slug": "suporte-auscultadores",
        "name": {
            "pt-PT": "Suporte para Auscultadores",
            "en": "Headphone Stand"
        },
        "description": {
            "pt-PT": "Produto descontinuado, mantido apenas para testar que itens inativos não aparecem na loja.",
            "en": "Discontinued product, kept only to prove inactive items never reach the storefront."
        },
        "category_id": "cat-acessorios",
        "price_cents": 1600,
        "currency": "EUR",
        "dimensions": {"width": 110.0, "height": 220.0, "depth": 110.0, "unit": "mm"},
        "colors": [
            {"id": "preto", "name": {"pt-PT": "Preto", "en": "Black"}, "hex": "#1E293B"}
        ],
        "images": [],
        "stock": 3,
        "active": False,
        "made_to_order": False,
        "featured": False,
        "created_at": datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    }
]


async def bootstrap_admin(db: AsyncIOMotorDatabase) -> None:
    """Idempotently ensure the initial administrator, demo customer and catalog exist."""
    if not settings.BOOTSTRAP_ADMIN_ENABLED:
        logger.info("Admin bootstrap is disabled via configuration.")
        return

    admin_email = (settings.ADMIN_INITIAL_EMAIL or "").strip().lower()
    admin_password = settings.ADMIN_INITIAL_PASSWORD
    admin_name = settings.ADMIN_INITIAL_NAME or "Clara Rosa Admin"

    if not admin_email or not admin_password:
        logger.warning("Admin bootstrap skipped: ADMIN_INITIAL_EMAIL or ADMIN_INITIAL_PASSWORD not configured.")
        return

    now = datetime.now(timezone.utc)

    # 1. Admin account
    existing_admin = await db.users.find_one({"email": admin_email})
    if not existing_admin:
        new_admin = {
            "email": admin_email,
            "password_hash": hash_password(admin_password),
            "name": admin_name,
            "role": UserRole.ADMIN.value,
            "is_active": True,
            "email_verified": True,
            "status": "online",
            "avatar": "assets/images/avatars/brian-hughes.jpg",
            "addresses": [],
            "created_at": now,
            "updated_at": now
        }
        await db.users.insert_one(new_admin)
        logger.info("Admin user '%s' provisioned.", admin_email)
    elif existing_admin.get("role") != UserRole.ADMIN.value:
        logger.error("Conflict: email '%s' belongs to non-admin.", admin_email)

    # 2. Demo customer account (for seamless testing with cliente@clararosa.pt / cliente)
    demo_cust_email = "cliente@clararosa.pt"
    existing_cust = await db.users.find_one({"email": demo_cust_email})
    if not existing_cust:
        new_cust = {
            "id": "b4f0a8e2-1c3d-4a5b-9e7f-2d6c8a1b3e5f",
            "email": demo_cust_email,
            "password_hash": hash_password("cliente"),
            "name": "Cliente Demo",
            "role": UserRole.CUSTOMER.value,
            "is_active": True,
            "email_verified": True,
            "status": "online",
            "avatar": "assets/images/avatars/female-01.jpg",
            "addresses": [
                {
                    "id": "address-1729245000000-0",
                    "label": "Casa",
                    "street": "Rua de Santa Catarina, 450",
                    "unit": "2º Dto",
                    "postal_code": "4000-442",
                    "city": "Porto",
                    "country": "Portugal"
                }
            ],
            "created_at": now,
            "updated_at": now
        }
        await db.users.insert_one(new_cust)
        logger.info("Demo customer user '%s' provisioned.", demo_cust_email)

    # 3. Seed categories if empty
    cat_count = await db.categories.count_documents({})
    if cat_count == 0:
        await db.categories.insert_many(INITIAL_CATEGORIES)
        logger.info("Initial categories provisioned.")

    # 4. Seed products if empty
    prod_count = await db.products.count_documents({})
    if prod_count == 0:
        await db.products.insert_many(DEMO_PRODUCTS)
        logger.info("Initial demo products provisioned.")

