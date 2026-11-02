import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi import Request
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError
from app.config import settings
from app.core.bootstrap import bootstrap_admin
from app.core.chat_body_limit import ChatBodyLimitMiddleware
from app.database import close_mongo_connection, connect_to_mongo, get_database
from app.routers import admin_products, auth, categories, common, health, print_requests, products, users
from app.routers import chat
from app.services.chat import init_chat
from app.services.chat_realtime import redis_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("loja3d.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown lifecycle."""
    logger.info("Initializing Clara Rosa Webstore API...")
    await connect_to_mongo()
    db = await get_database()
    await bootstrap_admin(db)
    if settings.CHAT_ENABLED:
        await init_chat(db)
        async with redis_client() as redis:
            await redis.ping()
    yield
    logger.info("Shutting down Clara Rosa Webstore API...")
    await close_mongo_connection()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="API REST assíncrona com MongoDB para a Clara Rosa Webstore.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# CORS Configuration
origins = settings.CORS_ORIGINS if isinstance(settings.CORS_ORIGINS, list) else [str(settings.CORS_ORIGINS)]
app.add_middleware(ChatBodyLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Custom OpenAPI schema to include BearerAuth in Swagger UI
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Insira o token JWT retornado no login ou cadastro para testar rotas protegidas."
        }
    }
    # Apply security globally to Swagger UI definitions
    openapi_schema["security"] = [{"BearerAuth": []}]
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

# Health check (root and versioned)
app.include_router(health.router)
app.include_router(health.router, prefix=settings.API_V1_STR)

# Versioned API routes (/api/v1/...)
app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(users.router, prefix=settings.API_V1_STR)
app.include_router(categories.router, prefix=settings.API_V1_STR)
app.include_router(products.router, prefix=settings.API_V1_STR)
app.include_router(admin_products.router, prefix=settings.API_V1_STR)
app.include_router(print_requests.customer_router, prefix=settings.API_V1_STR)
app.include_router(print_requests.admin_router, prefix=settings.API_V1_STR)
app.include_router(chat.router, prefix=settings.API_V1_STR)


@app.exception_handler(RedisError)
@app.exception_handler(PyMongoError)
async def chat_infrastructure_error(request: Request, exc):
    if not request.url.path.startswith(settings.API_V1_STR + "/chat"):
        raise exc
    logger.error("Chat infrastructure failure: %s", type(exc).__name__)
    return JSONResponse(status_code=503, content={"detail": "Support infrastructure unavailable. Please retry."})

# Legacy compatibility routes for direct frontend mock substitution:
# 1. /api/auth/...
app.include_router(auth.router, prefix="/api")
# 2. /api/common/...
app.include_router(users.router, prefix="/api")
app.include_router(common.router, prefix="/api")
# 3. /api/clara-rosa/...
app.include_router(categories.router, prefix="/api/clara-rosa")
app.include_router(products.router, prefix="/api/clara-rosa")
app.include_router(admin_products.router, prefix="/api/clara-rosa")
