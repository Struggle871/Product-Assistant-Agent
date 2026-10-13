import asyncio
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError
from sqlalchemy.exc import DBAPIError

from app import health


@pytest.mark.parametrize(
    ("sqlstate", "expected"),
    [("28P01", "invalid_credentials"), ("3D000", "database_missing"), ("08003", "connection_lost")],
)
def test_database_error_codes_do_not_expose_secrets(sqlstate: str, expected: str) -> None:
    error = Exception("secret-password must never appear in readiness")
    error.sqlstate = sqlstate  # type: ignore[attr-defined]
    wrapped = DBAPIError("SELECT sensitive_statement", {}, error)
    assert health.failure_detail(wrapped) == expected


def test_bucket_missing_is_distinguished_from_wrong_credentials() -> None:
    missing = ClientError({"Error": {"Code": "NoSuchBucket"}}, "HeadBucket")
    denied = ClientError({"Error": {"Code": "AccessDenied"}}, "HeadBucket")
    assert health.failure_detail(missing) == "bucket_missing"
    assert health.failure_detail(denied) == "invalid_credentials"


async def test_stalled_database_connection_returns_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    class StalledConnection:
        async def __aenter__(self) -> None:
            await asyncio.Event().wait()

        async def __aexit__(self, *_: object) -> None:
            pass

    monkeypatch.setattr(health, "engine", SimpleNamespace(connect=StalledConnection))
    monkeypatch.setattr(
        health, "get_settings", lambda: SimpleNamespace(dependency_timeout_seconds=0.01)
    )
    result = await asyncio.wait_for(health.check_database(), timeout=1)
    assert result == health.DependencyStatus("postgresql", False, "timeout")


async def test_unavailable_dependency_does_not_report_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def database() -> health.DependencyStatus:
        return health.DependencyStatus("postgresql", True, "ok")

    async def redis() -> health.DependencyStatus:
        return health.DependencyStatus("redis", False, "connection_unavailable")

    async def minio() -> health.DependencyStatus:
        return health.DependencyStatus("minio", True, "ok")

    monkeypatch.setattr(health, "check_database", database)
    monkeypatch.setattr(health, "check_redis", redis)
    monkeypatch.setattr(health, "check_minio", minio)
    ready, statuses = await health.readiness()
    assert not ready
    assert len(statuses) == 3
