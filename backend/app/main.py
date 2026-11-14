from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="FIRETRACE API",
        version=settings.app_version,
        description=(
            "Global satellite fire intelligence API for NASA FIRMS MODIS and VIIRS "
            "active-fire detections."
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.include_router(health_router, prefix="/api")
    return app


app = create_app()
