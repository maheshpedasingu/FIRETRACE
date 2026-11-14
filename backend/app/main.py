from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.analytics import router as analytics_router
from app.api.aoi import router as aoi_router
from app.api.export import router as export_router
from app.api.health import router as health_router
from app.api.ingest import router as ingest_router
from app.api.system import router as system_router
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
    for router in (health_router, system_router, ingest_router, analytics_router,
                   aoi_router, export_router):  # fmt: skip
        app.include_router(router, prefix="/api")
    return app


app = create_app()
