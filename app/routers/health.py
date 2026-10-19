from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from app.database import db_manager

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check():
    """Health check endpoint verifying API and MongoDB connectivity."""
    db_status = "disconnected"
    status_code = status.HTTP_200_OK

    if db_manager.client is not None:
        try:
            await db_manager.client.admin.command("ping")
            db_status = "connected"
        except Exception:
            db_status = "error"
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    response_data = {
        "status": "ok" if status_code == status.HTTP_200_OK else "degraded",
        "database": db_status
    }
    return JSONResponse(status_code=status_code, content=response_data)
