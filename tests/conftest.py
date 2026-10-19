import os
import pytest
from httpx import AsyncClient, ASGITransport
from motor.motor_asyncio import AsyncIOMotorClient

# Use test database
os.environ["MONGODB_DB_NAME"] = "clara_rosa_test_store"
os.environ["BOOTSTRAP_ADMIN_ENABLED"] = "true"
os.environ["ADMIN_INITIAL_EMAIL"] = "admin@clararosa.pt"
os.environ["ADMIN_INITIAL_PASSWORD"] = "admin123"

from app.config import settings
from app.database import close_mongo_connection, connect_to_mongo, db_manager
from app.core.rate_limit import reset_rate_limits
from main import app


@pytest.fixture(scope="session", autouse=True)
async def setup_test_db():
    await connect_to_mongo()
    yield
    # Drop test database on finish
    if db_manager.client:
        await db_manager.client.drop_database("clara_rosa_test_store")
    await close_mongo_connection()


@pytest.fixture(autouse=True)
async def clean_collections():
    reset_rate_limits()
    # Keep bootstrap admin if present, clean up products and normal customers
    if db_manager.db is not None:
        await db_manager.db.products.delete_many({})
        await db_manager.db.categories.delete_many({})
        await db_manager.db.refresh_tokens.delete_many({})
        await db_manager.db.auth_tokens.delete_many({})
        # delete non-admin test users
        await db_manager.db.users.delete_many({"role": "CUSTOMER"})
    yield


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def admin_token(client: AsyncClient):
    # Ensure bootstrap admin exists
    from app.core.bootstrap import bootstrap_admin
    await bootstrap_admin(db_manager.db)

    res = await client.post("/api/v1/auth/sign-in", json={
        "email": "admin@clararosa.pt",
        "password": "admin123"
    })
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


@pytest.fixture
async def customer_token(client: AsyncClient):
    res = await client.post("/api/v1/auth/sign-up", json={
        "name": "Cliente Teste",
        "email": "cliente.teste@example.pt",
        "password": "password123"
    })
    assert res.status_code == 201, res.text
    return res.json()["access_token"]
