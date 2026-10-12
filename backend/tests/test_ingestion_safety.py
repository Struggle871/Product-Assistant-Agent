from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.domain.models import DocumentStatus, JobStatus
from app.rag import service


class ScalarResult:
    def __init__(self, value: object) -> None:
        self.value = value

    def scalar_one_or_none(self) -> object:
        return self.value

    def scalars(self) -> "ScalarResult":
        return self

    def first(self) -> object:
        return self.value


@pytest.mark.asyncio
async def test_duplicate_upload_reuses_document_without_writing_object() -> None:
    document = SimpleNamespace(id="document-1")
    job = SimpleNamespace(id="job-1", status=JobStatus.SUCCEEDED)
    session = AsyncMock()
    session.execute.side_effect = [ScalarResult(document), ScalarResult(job)]
    store = AsyncMock()

    result_document, result_job, should_enqueue = await service.create_document(
        session,
        store,
        content=b"same manual",
        filename="manual.md",
        content_type="text/markdown",
        product_id="product-1",
        product_model_id=None,
        product_version_id=None,
        title=None,
        language="zh-CN",
        document_type="manual",
    )

    assert result_document is document
    assert result_job is job
    assert should_enqueue is False
    store.put.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_ingestion_never_publishes_index(monkeypatch: pytest.MonkeyPatch) -> None:
    document = SimpleNamespace(
        id="document-1",
        object_key="documents/product/manual.md",
        title="manual",
        status=DocumentStatus.UPLOADED,
        error_message=None,
    )
    job = SimpleNamespace(
        id="job-1",
        status=JobStatus.QUEUED,
        attempts=0,
        started_at=None,
        completed_at=None,
        error_message=None,
    )
    session = AsyncMock()
    session.get.side_effect = [document, job, document, job]
    store = AsyncMock()
    store.read.side_effect = RuntimeError("object store unavailable")
    publish = AsyncMock()
    monkeypatch.setattr(service, "publish_index_version", publish)

    with pytest.raises(RuntimeError, match="object store unavailable"):
        await service.process_document(session, store, document.id, job.id)

    assert document.status == DocumentStatus.FAILED
    assert job.status == JobStatus.FAILED
    publish.assert_not_awaited()
    session.rollback.assert_awaited_once()
