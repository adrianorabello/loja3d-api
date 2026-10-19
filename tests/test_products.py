import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_products_crud_and_permissions(client: AsyncClient, admin_token: str, customer_token: str):
    # 1. Customer cannot create a product (403 Forbidden)
    cust_create_res = await client.post(
        "/api/v1/admin/products",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={
            "slug": "vaso-geometrico",
            "name": {"pt-PT": "Vaso Geométrico", "en": "Geometric Vase"},
            "description": {"pt-PT": "Vaso decorativo", "en": "Decorative vase"},
            "categoryId": "cat-casa-escritorio",
            "price": 12.50,
            "stock": 5
        }
    )
    assert cust_create_res.status_code == 403

    # 2. Admin creates a product successfully (201 Created)
    admin_create_res = await client.post(
        "/api/v1/admin/products",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "slug": "vaso-geometrico",
            "name": {"pt-PT": "Vaso Geométrico", "en": "Geometric Vase"},
            "description": {"pt-PT": "Vaso decorativo", "en": "Decorative vase"},
            "categoryId": "cat-casa-escritorio",
            "price": 12.50,
            "dimensions": {"width": 80.0, "height": 120.0, "depth": 80.0, "unit": "mm"},
            "colors": [{"id": "branco", "name": {"pt-PT": "Branco", "en": "White"}, "hex": "#ffffff"}],
            "images": ["assets/images/vaso.jpg"],
            "stock": 5,
            "active": True,
            "featured": True
        }
    )
    assert admin_create_res.status_code == 201
    product = admin_create_res.json()
    product_id = product["id"]
    assert product["slug"] == "vaso-geometrico"
    assert product["price"] == 12.50
    assert product["dimensions"]["unit"] == "mm"

    # 3. Duplicate slug fails with 409 Conflict
    dup_slug_res = await client.post(
        "/api/v1/admin/products",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "slug": "vaso-geometrico",
            "name": {"pt-PT": "Outro Vaso", "en": "Other Vase"},
            "categoryId": "cat-casa-escritorio",
            "price": 15.00
        }
    )
    assert dup_slug_res.status_code == 409

    # 4. Public storefront returns the active product
    public_res = await client.get("/api/v1/products")
    assert public_res.status_code == 200
    items = public_res.json()
    assert any(p["slug"] == "vaso-geometrico" for p in items)

    # 5. Public storefront returns by slug
    slug_res = await client.get("/api/v1/products/vaso-geometrico")
    assert slug_res.status_code == 200
    assert slug_res.json()["name"]["pt-PT"] == "Vaso Geométrico"

    # 6. Admin toggles active to False
    patch_res = await client.patch(
        f"/api/v1/admin/products/{product_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"active": False}
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["active"] is False

    # 7. Inactive product disappears from public storefront and returns 404 by slug
    public_after_res = await client.get("/api/v1/products")
    assert not any(p["slug"] == "vaso-geometrico" for p in public_after_res.json())

    slug_404_res = await client.get("/api/v1/products/vaso-geometrico")
    assert slug_404_res.status_code == 404

    # 8. But admin list still shows all products including inactive ones
    admin_all_res = await client.get(
        "/api/v1/admin/products",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert any(p["slug"] == "vaso-geometrico" for p in admin_all_res.json())

    # 9. Admin deletes product
    del_res = await client.delete(
        f"/api/v1/admin/products/{product_id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert del_res.status_code == 204
