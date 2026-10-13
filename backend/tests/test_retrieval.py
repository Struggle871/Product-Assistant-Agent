from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from app.infrastructure.embeddings import EmbeddingError
from app.rag import retrieval
from app.rag.evaluation import DEMO_EVAL_CASES, evaluate_cases
from app.rag.retrieval import (
    Answerability,
    Evidence,
    RetrievalFilters,
    assess_answerability,
    reciprocal_rank_fusion,
)


def evidence(
    chunk_id: str,
    document_id: str,
    *,
    vector_rank: int | None = None,
    bm25_rank: int | None = None,
) -> Evidence:
    return Evidence(
        chunk_id=chunk_id,
        document_id=document_id,
        document_version_id="version",
        text="manual text",
        heading="Setup",
        page_number=1,
        product_id="product",
        product_model_id=None,
        product_version_id=None,
        vector_rank=vector_rank,
        bm25_rank=bm25_rank,
    )


def test_rrf_fuses_shared_results_and_keeps_ranks() -> None:
    fused = reciprocal_rank_fusion(
        [evidence("a", "doc-a", vector_rank=1), evidence("b", "doc-b", vector_rank=2)],
        [evidence("b", "doc-b", bm25_rank=1), evidence("c", "doc-c", bm25_rank=2)],
        limit=3,
    )

    assert fused[0].chunk_id == "b"
    assert fused[0].vector_rank == 2
    assert fused[0].bm25_rank == 1
    assert fused[0].rrf_score > fused[1].rrf_score


def test_answerability_does_not_treat_one_score_as_probability() -> None:
    state, reasons = assess_answerability(
        "如何重置？",
        [evidence("a", "doc-a", vector_rank=1)],
        RetrievalFilters(product_id="product"),
    )

    assert state == Answerability.UNANSWERABLE
    assert reasons


def test_evaluation_cases_report_reciprocal_rank() -> None:
    result = evaluate_cases(
        DEMO_EVAL_CASES[:1],
        lambda _: ([evidence("a", "archer-ax55")], True),
    )[0]

    assert result.hit_at_k is True
    assert result.reciprocal_rank == 1.0


@pytest.mark.parametrize(
    "query,items,filters,expected",
    [
        ("如何重置？", [], RetrievalFilters(), Answerability.MISSING_CONTEXT),
        ("如何重置？", [], RetrievalFilters(product_id="product"), Answerability.UNANSWERABLE),
        (
            "如何升级固件？",
            [replace(evidence("a", "doc"), text="连接 Wi-Fi 网络")],
            RetrievalFilters(product_id="product"),
            Answerability.UNANSWERABLE,
        ),
        (
            "如何连接并升级固件？",
            [replace(evidence("a", "doc"), text="连接 Wi-Fi 网络")],
            RetrievalFilters(product_id="product"),
            Answerability.PARTIAL,
        ),
        (
            "如何重置？",
            [replace(evidence("a", "doc"), text="按住 Reset 重置按钮十秒")],
            RetrievalFilters(product_id="product"),
            Answerability.ANSWERABLE,
        ),
        (
            "如何重置？",
            [replace(evidence("a", "doc"), product_id="other")],
            RetrievalFilters(product_id="product"),
            Answerability.CONFLICTED,
        ),
        (
            "如何重置？",
            [replace(evidence("a", "doc"), product_version_id="v2")],
            RetrievalFilters(product_id="product", product_version_id="v1"),
            Answerability.CONFLICTED,
        ),
        (
            "如何重置？",
            [replace(evidence("a", "doc"), text="按住 Reset 重置按钮十秒")],
            RetrievalFilters(product_id="product", product_version_id="v1"),
            Answerability.PARTIAL,
        ),
        (
            "如何重置？",
            [replace(evidence("a", "doc"), text="按住重置按钮", source_type="web")],
            RetrievalFilters(product_id="product"),
            Answerability.UNANSWERABLE,
        ),
    ],
)
def test_five_way_assessment(
    query: str, items: list[Evidence], filters: RetrievalFilters, expected: Answerability
) -> None:
    assert assess_answerability(query, items, filters)[0] == expected


def test_high_rrf_scores_do_not_make_irrelevant_evidence_answerable() -> None:
    items = [replace(evidence("a", "doc"), rrf_score=1.0)]
    assert (
        assess_answerability("如何重置？", items, RetrievalFilters(product_id="product"))[0]
        == Answerability.UNANSWERABLE
    )


def test_citations_include_page_and_heading_after_fusion() -> None:
    item = replace(evidence("a", "doc"), document_title="Manual", page_number=4)
    assert reciprocal_rank_fusion([item], [item])[0].citation == "Manual · 第 4 页 · Setup"


@pytest.mark.parametrize("query", ["Tapo C200 如何拆机？", "AX55 电源冒烟怎么办？"])
def test_generic_manual_cannot_authorize_unsafe_repair(query: str) -> None:
    items = [replace(evidence("a", "doc"), text="接通电源，等待状态灯稳定", rrf_score=1.0)]
    assert assess_answerability(query, items, RetrievalFilters(product_id="product"))[0] == (
        Answerability.UNANSWERABLE
    )


@pytest.mark.asyncio
async def test_embedding_outage_still_returns_keyword_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        retrieval, "vector_search", AsyncMock(side_effect=EmbeddingError("timeout"))
    )
    monkeypatch.setattr(
        retrieval,
        "bm25_search",
        AsyncMock(
            return_value=[
                replace(evidence("a", "doc", bm25_rank=1), text="按住重置按钮十秒"),
            ]
        ),
    )
    result = await retrieval.hybrid_search(
        AsyncMock(), "如何重置？", RetrievalFilters(product_id="product")
    )
    assert result.evidence[0].chunk_id == "a"
    assert "timeout" in result.trace.warnings


@pytest.mark.asyncio
async def test_bm25_outage_returns_vector_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        retrieval,
        "vector_search",
        AsyncMock(
            return_value=[
                replace(evidence("a", "doc", vector_rank=1), text="按住重置按钮十秒"),
            ]
        ),
    )
    monkeypatch.setattr(
        retrieval, "bm25_search", AsyncMock(side_effect=RuntimeError("unavailable"))
    )
    result = await retrieval.hybrid_search(
        AsyncMock(), "如何重置？", RetrievalFilters(product_id="product")
    )
    assert result.trace.vector_candidates == 1
    assert result.trace.bm25_candidates == 0
    assert any("BM25 unavailable" in warning for warning in result.trace.warnings)
