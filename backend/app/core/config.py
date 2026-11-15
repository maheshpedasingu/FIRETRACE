"""Backend configuration, read from environment variables and backend/.env.

Secrets (the FIRMS MAP_KEY) are held as SecretStr and are never returned by any
endpoint. Only a boolean "is configured" flag may be exposed.
"""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "FIRETRACE"
    app_version: str = "1.1.0"

    firms_map_key: SecretStr | None = None
    firms_api_base: str = "https://firms.modaps.eosdis.nasa.gov/api"
    firms_timeout_seconds: float = 30.0
    firms_max_retries: int = 3
    firms_area_max_day_range: int = 5
    firms_transactions_per_window: int = 5000
    firms_transaction_window_seconds: int = 600

    database_url: str = "sqlite:///../data/firetrace.sqlite"
    raw_data_dir: str = "../data/raw"
    processed_data_dir: str = "../data/processed"
    reference_data_dir: str = "../data/reference"
    ingest_chunk_rows: int = 200_000
    partition_tile_degrees: int = 10

    grid_crs: str = "EPSG:6933"
    grid_resolution_m: int = 1000

    frontend_origin: str = "http://localhost:5173"

    @property
    def firms_map_key_configured(self) -> bool:
        return self.firms_map_key is not None and bool(self.firms_map_key.get_secret_value())


@lru_cache
def get_settings() -> Settings:
    return Settings()
