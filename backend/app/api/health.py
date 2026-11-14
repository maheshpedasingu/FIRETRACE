from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.config import Settings, get_settings

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    app: str
    version: str
    server_time_utc: datetime
    firms_map_key_configured: bool


@router.get("/health", response_model=HealthResponse)
def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    """Liveness check. Reports whether a MAP_KEY is configured, never the key itself."""
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        version=settings.app_version,
        server_time_utc=datetime.now(UTC),
        firms_map_key_configured=settings.firms_map_key_configured,
    )
