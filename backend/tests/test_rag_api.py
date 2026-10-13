from dataclasses import replace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api import rag
from app.db import get_session
from app.main import app
from app.rag.answer import AnswerResult, CitedExcerpt
from app.rag.retrieval import (
    Answerability,
    Evidence,
    RetrievalFilters,
    RetrievalResult,
    RetrievalTrace,
)


def test_search_serializes_evidence_and_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    item = Evidence(
        "chunk",
        "doc",
        "version",
        "按住重置按钮十秒",
        "重置",
        2,
        "product",
        None,
        None,
        document_title="Manual",
    )
    result = RetrievalResult(
        [replace(item, rrf_score=0.02)],
        RetrievalTrace("如何重置？", RetrievalFilters(product_id="product")),
        Answerability.ANSWERABLE,
        ["covered"],
    )
    search = AsyncMock(return_value=result)
    monkeypatch.setattr(rag, "hybrid_search", search)
    app.dependency_overrides[get_session] = lambda: AsyncMock()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/rag/search",
                json={
                    "query": " 如何重置？ ",
                    "product_id": "product",
                },
            )
        assert response.status_code == 200
        assert response.json()["evidence"][0]["citation"] == "Manual · 第 2 页 · 重置"
        assert response.json()["answerability"] == "ANSWERABLE"
        assert search.await_args is not None
        assert search.await_args.args[1] == "如何重置？"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "payload",
    [
        {"query": " "},
        {"query": "question", "limit": 0},
        {"query": "question", "limit": 21},
    ],
)
def test_search_rejects_invalid_requests(payload: dict[str, object]) -> None:
    with TestClient(app) as client:
        assert client.post("/api/v1/rag/search", json=payload).status_code == 422


def test_answer_serializes_only_validated_quotes(monkeypatch: pytest.MonkeyPatch) -> None:
    result = RetrievalResult(
        [],
        RetrievalTrace("question", RetrievalFilters(product_id="product")),
        Answerability.ANSWERABLE,
        [],
    )
    grounded = AnswerResult(
        result,
        Answerability.ANSWERABLE,
        "按住Reset按钮10秒。 [1]",
        [],
        [CitedExcerpt(chunk_id="chunk", quote="按住Reset按钮10秒。", citation="Manual · 重置")],
        model="Qwen/Qwen3-8B",
    )
    monkeypatch.setattr(rag, "answer_question", AsyncMock(return_value=grounded))
    app.dependency_overrides[get_session] = lambda: AsyncMock()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/rag/answer", json={"query": "如何重置？", "product_id": "product"}
            )
        assert response.status_code == 200
        assert response.json()["excerpts"][0]["citation"] == "Manual · 重置"
        assert response.json()["model"] == "Qwen/Qwen3-8B"
    finally:
        app.dependency_overrides.clear()
