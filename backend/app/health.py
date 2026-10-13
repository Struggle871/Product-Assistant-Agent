# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false

import asyncio
from dataclasses import dataclass

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, EndpointConnectionError
from redis.asyncio import Redis
from sqlalchemy import text

from app.config import get_settings
from app.db import engine


@dataclass(frozen=True)
class DependencyStatus:
    name: str
    ok: bool
    detail: str


def failure_detail(exc: Exception) -> str:
    """Return an actionable code without database URLs, passwords or response bodies."""
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        sqlstate = getattr(current, "sqlstate", None)
        if sqlstate == "28P01":
            return "invalid_credentials"
        if sqlstate == "3D000":
            return "database_missing"
        if sqlstate in {"08003", "08006"}:
            return "connection_lost"
        if isinstance(current, TimeoutError):
            return "timeout"
        if isinstance(current, (ConnectionRefusedError, EndpointConnectionError)):
            return "connection_unavailable"
        if isinstance(current, ClientError):
            code = current.response.get("Error", {}).get("Code")
            if code in {"404", "NoSuchBucket"}:
                return "bucket_missing"
            if code in {"403", "AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch"}:
                return "invalid_credentials"
        original = getattr(current, "orig", None)
        current = original or current.__cause__ or current.__context__
    return type(exc).__name__


async def check_database() -> DependencyStatus:
    try:
        async with (
            asyncio.timeout(get_settings().dependency_timeout_seconds),
            engine.connect() as connection,
        ):
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
        return DependencyStatus("postgresql", False, failure_detail(exc))


async def check_redis() -> DependencyStatus:
    settings = get_settings()
    client = Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=settings.dependency_timeout_seconds,
        socket_timeout=settings.dependency_timeout_seconds,
    )
    try:
        async with asyncio.timeout(settings.dependency_timeout_seconds):
            await client.ping()
        return DependencyStatus("redis", True, "ok")
    except Exception as exc:  # noqa: BLE001
        return DependencyStatus("redis", False, failure_detail(exc))
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
        config=Config(
            connect_timeout=settings.dependency_timeout_seconds / 2,
            read_timeout=settings.dependency_timeout_seconds / 2,
            retries={"total_max_attempts": 1},
        ),
    )
    try:
        client.head_bucket(Bucket=settings.minio_bucket)
        return DependencyStatus("minio", True, "ok")
    except Exception as exc:  # noqa: BLE001
        return DependencyStatus("minio", False, failure_detail(exc))


async def check_minio() -> DependencyStatus:
    try:
        async with asyncio.timeout(get_settings().dependency_timeout_seconds):
            return await asyncio.to_thread(_check_minio_sync)
    except TimeoutError:
        return DependencyStatus("minio", False, "timeout")


async def readiness() -> tuple[bool, list[DependencyStatus]]:
    statuses = await asyncio.gather(check_database(), check_redis(), check_minio())
    return all(status.ok for status in statuses), list(statuses)
