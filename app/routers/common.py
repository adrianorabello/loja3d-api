from typing import Any, Dict, List
from fastapi import APIRouter
from app.config import settings

router = APIRouter(prefix="/common", tags=["Common UI Data"])

ADMIN_NAVIGATION: List[Dict[str, Any]] = [
    {
        "id": "admin.products",
        "title": "Produtos",
        "type": "collapsable",
        "icon": "heroicons_outline:cube",
        "meta": {"roles": ["ADMIN"]},
        "children": [
            {
                "id": "admin.products.list",
                "title": "Lista de produtos",
                "type": "basic",
                "link": "/admin/products",
                "meta": {"roles": ["ADMIN"]}
            },
            {
                "id": "admin.products.new",
                "title": "Cadastrar produto",
                "type": "basic",
                "link": "/admin/products/new",
                "meta": {"roles": ["ADMIN"]}
            }
        ]
    },
    {
        "id": "admin.print-requests",
        "title": "Pedidos personalizados",
        "type": "basic",
        "icon": "heroicons_outline:clipboard-list",
        "link": "/admin/requests",
        "meta": {"roles": ["ADMIN"]}
    },
    {
        "id": "admin.divider",
        "type": "divider",
        "meta": {"roles": ["ADMIN"]}
    },
    {
        "id": "admin.back-to-store",
        "title": "Ver loja",
        "type": "basic",
        "icon": "heroicons_outline:shopping-bag",
        "link": "/",
        "exactMatch": True
    }
]


@router.get("/navigation")
async def get_navigation():
    """Return navigation structures required by the admin shell layout."""
    navigation = list(ADMIN_NAVIGATION)
    if settings.CHAT_ENABLED:
        navigation.insert(2, {
            "id": "admin.chat", "title": "Atendimento", "type": "basic",
            "icon": "heroicons_outline:chat-alt-2", "link": "/admin/chat",
            "meta": {"roles": ["ADMIN"]}
        })
    return {key: navigation for key in ("default", "compact", "futuristic", "horizontal")}


@router.get("/messages")
async def get_messages():
    """Return initial messages list."""
    return []


@router.get("/notifications")
async def get_notifications():
    """Return initial notifications list."""
    return []


@router.get("/shortcuts")
async def get_shortcuts():
    """Return initial shortcuts list."""
    return []
