# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false

import asyncio
from dataclasses import dataclass

import boto3
from redis.asyncio import Redis
from sqlalchemy import text

from app.config import get_settings
from app.db import engine


@dataclass(frozen=True)
class DependencyStatus:
    name: str
    ok: bool
    detail: str


async def check_database() -> DependencyStatus:
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text(
                    "SELECT extname FROM pg_extension "
                    "WHERE extname IN ('vector', 'pg_search') ORDER BY extname"
                )
            )
            extensions = set(result.scalars())
            missing = {"vector", "pg_search"} - extensions
            if missing:
                return DependencyStatus(
                    "postgresql",
                    False,
                    f"missing_extensions:{','.join(sorted(missing))}",
                )
        return DependencyStatus("postgresql", True, "ok")
    except Exception as exc:  # noqa: BLE001
        return DependencyStatus("postgresql", False, type(exc).__name__)


async def check_redis() -> DependencyStatus:
    client = Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        await client.ping()
        return DependencyStatus("redis", True, "ok")
    except Exception as exc:  # noqa: BLE001
        return DependencyStatus("redis", False, type(exc).__name__)
    finally:
        await client.aclose()


def _check_minio_sync() -> DependencyStatus:
    settings = get_settings()
    client = boto3.client(
        "s3",
        endpoint_url=settings.minio_endpoint,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        use_ssl=settings.minio_secure,
    )
    try:
        client.head_bucket(Bucket=settings.minio_bucket)
        return DependencyStatus("minio", True, "ok")
    except Exception as exc:  # noqa: BLE001
        return DependencyStatus("minio", False, type(exc).__name__)


async def check_minio() -> DependencyStatus:
    return await asyncio.to_thread(_check_minio_sync)


async def readiness() -> tuple[bool, list[DependencyStatus]]:
    statuses = await asyncio.gather(check_database(), check_redis(), check_minio())
    return all(status.ok for status in statuses), list(statuses)
