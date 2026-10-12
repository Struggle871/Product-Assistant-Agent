from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Product Assistant Agent"
    app_env: str = "development"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"
    database_url: str = (
        "postgresql+asyncpg://product_assistant:product_assistant@localhost:5432/"
        "product_assistant"
    )
    redis_url: str = "redis://localhost:6379/0"
    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "product-assistant"
    minio_secure: bool = False
    admin_api_key: str = Field(default="change-me", repr=False)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
