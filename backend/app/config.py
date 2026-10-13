from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
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
    dependency_timeout_seconds: float = Field(default=5, gt=0, le=30)
    api_prefix: str = "/api/v1"
    database_url: str = (
        "postgresql+asyncpg://product_assistant:product_assistant@localhost:5433/product_assistant"
    )
    redis_url: str = "redis://localhost:6379/0"
    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "product-assistant"
    minio_secure: bool = False
    admin_api_key: str = Field(default="change-me", repr=False)
    # Expression indexes support the configured model's vector dimension.
    embedding_dimensions: int = 1024
    embedding_provider: Literal["hash", "openai"] = "hash"
    embedding_model: str = "BAAI/bge-m3"
    embedding_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_api_key: str = Field(default="", repr=False)
    embedding_send_dimensions: bool = False
    embedding_timeout_seconds: float = Field(default=30, gt=0, le=120)
    embedding_batch_size: int = Field(default=32, ge=1, le=128)
    chat_provider: Literal["disabled", "openai"] = "disabled"
    chat_base_url: str = "https://api.siliconflow.cn/v1"
    chat_model: str = "Qwen/Qwen3-8B"
    chat_api_key: str = Field(default="", repr=False)
    chat_timeout_seconds: float = Field(default=45, gt=0, le=120)
    chat_max_tokens: int = Field(default=2048, ge=256, le=8192)
    chat_enable_thinking: bool = False
    chat_thinking_budget: int = Field(default=1024, ge=128, le=8192)
    chat_structured_output: Literal["json_object", "json_schema"] = "json_object"

    @field_validator("embedding_dimensions")
    @classmethod
    def supported_dimensions(cls, value: int) -> int:
        if value not in {1024, 1536}:
            raise ValueError("Embedding dimensions must be 1024 or 1536")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
