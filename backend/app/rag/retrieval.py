from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Select, func, literal_column, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.domain.models import Document, DocumentChunk, DocumentStatus, DocumentVersion
from app.infrastructure.embeddings import EmbeddingError, embed_texts, embedding_profile


class Answerability(StrEnum):
    ANSWERABLE = "ANSWERABLE"
    PARTIAL = "PARTIAL"
    UNANSWERABLE = "UNANSWERABLE"
    MISSING_CONTEXT = "MISSING_CONTEXT"
    CONFLICTED = "CONFLICTED"


@dataclass(frozen=True)
class RetrievalFilters:
    product_id: str | None = None
    product_model_id: str | None = None
    product_version_id: str | None = None
    language: str | None = None


@dataclass(frozen=True)
class Evidence:
    chunk_id: str
    document_id: str
    document_version_id: str
    text: str
    heading: str | None
    page_number: int | None
    product_id: str
    product_model_id: str | None
    product_version_id: str | None
    vector_rank: int | None = None
    bm25_rank: int | None = None
    rrf_score: float = 0.0
    document_title: str = ""
    source_type: str = "uploaded"

    @property
    def citation(self) -> str:
        locations = [f"第 {self.page_number} 页"] if self.page_number else []
        if self.heading:
            locations.append(self.heading)
        return f"{self.document_title or self.document_id} · {' · '.join(locations) or '正文'}"


@dataclass
class RetrievalTrace:
    query: str
    filters: RetrievalFilters
    started_at: float = field(default_factory=time.perf_counter)
    vector_candidates: int = 0
    bm25_candidates: int = 0
    fused_candidates: int = 0
    vector_latency_ms: float = 0.0
    bm25_latency_ms: float = 0.0
    fusion_latency_ms: float = 0.0
    warnings: list[str] = field(default_factory=lambda: list[str]())
    embedding_profile: str = ""

    @property
    def total_latency_ms(self) -> float:
        return (time.perf_counter() - self.started_at) * 1000


@dataclass(frozen=True)
class RetrievalResult:
    evidence: list[Evidence]
    trace: RetrievalTrace
    answerability: Answerability
    answerability_reasons: list[str]


def _base_query(filters: RetrievalFilters) -> Select[Any]:
    query = (
        select(DocumentChunk, Document)
        .join(DocumentVersion, DocumentChunk.document_version_id == DocumentVersion.id)
        .join(Document, DocumentVersion.document_id == Document.id)
        .where(Document.status == DocumentStatus.READY)
    )
    conditions = {
        "product_id": (Document.product_id, filters.product_id),
        "product_model_id": (Document.product_model_id, filters.product_model_id),
        "product_version_id": (Document.product_version_id, filters.product_version_id),
        "language": (Document.language, filters.language),
    }
    for column, value in conditions.values():
        if value is not None:
            query = query.where(column == value)
    return query  # type: ignore[return-value]


async def vector_search(
    session: AsyncSession,
    query: str,
    filters: RetrievalFilters,
    limit: int,
) -> list[Evidence]:
    vector = (await embed_texts([query]))[0]
    dimensions = get_settings().embedding_dimensions
    statement = _base_query(filters).where(
        DocumentChunk.embedding.is_not(None),
        DocumentChunk.embedding_profile == embedding_profile(),
        func.vector_dims(DocumentChunk.embedding) == literal_column(str(dimensions)),
    )
    statement = statement.order_by(
        DocumentChunk.embedding.cast(Vector(dimensions)).cosine_distance(vector)
    ).limit(limit)
    rows = (await session.execute(statement)).mappings().all()
    results: list[Evidence] = []
    for index, row in enumerate(rows, start=1):
        chunk: DocumentChunk = row[DocumentChunk]
        document: Document = row[Document]
        results.append(_to_evidence(chunk, document, vector_rank=index))
    return results


async def bm25_search(
    session: AsyncSession,
    query: str,
    filters: RetrievalFilters,
    limit: int,
) -> list[Evidence]:
    # ParadeDB's BM25 operator is intentionally isolated here; deployments without
    # pg_search can disable this leg while preserving the rest of the contract.
    filter_sql = ["d.status = 'READY'", "c.text @@@ :query"]
    params: dict[str, Any] = {"query": query, "limit": limit}
    for key, value in (
        ("product_id", filters.product_id),
        ("product_model_id", filters.product_model_id),
        ("product_version_id", filters.product_version_id),
        ("language", filters.language),
    ):
        if value is not None:
            filter_sql.append(f"d.{key} = :{key}")
            params[key] = value
    statement = text(
        "SELECT c.id, c.document_version_id, c.chunk_index, c.text, c.heading, "
        "c.page_number, v.document_id, d.product_id, d.product_model_id, "
        "d.product_version_id, d.title, d.source_type "
        "FROM document_chunks c "
        "JOIN document_versions v ON v.id = c.document_version_id "
        "JOIN documents d ON d.id = v.document_id "
        f"WHERE {' AND '.join(filter_sql)} "
        "ORDER BY paradedb.score(c.id) DESC LIMIT :limit"
    )
    # A failed PostgreSQL statement aborts its transaction. Roll back only this
    # retrieval leg, so the session remains usable by callers after degradation.
    async with session.begin_nested():
        rows = (await session.execute(statement, params)).mappings().all()
    return [
        Evidence(
            chunk_id=str(row["id"]),
            document_id=str(row["document_id"]),
            document_version_id=str(row["document_version_id"]),
            text=str(row["text"]),
            heading=row["heading"],
            page_number=row["page_number"],
            product_id=str(row["product_id"]),
            product_model_id=row["product_model_id"],
            product_version_id=row["product_version_id"],
            document_title=str(row["title"]),
            source_type=str(row["source_type"]),
            bm25_rank=index,
        )
        for index, row in enumerate(rows, start=1)
    ]


def reciprocal_rank_fusion(
    vector_results: list[Evidence],
    bm25_results: list[Evidence],
    *,
    k: int = 60,
    limit: int = 8,
) -> list[Evidence]:
    merged: dict[str, Evidence] = {}
    scores: dict[str, float] = {}
    for result in vector_results:
        merged[result.chunk_id] = result
        scores[result.chunk_id] = scores.get(result.chunk_id, 0.0) + 1 / (
            k + (result.vector_rank or k)
        )
    for result in bm25_results:
        merged.setdefault(result.chunk_id, result)
        scores[result.chunk_id] = scores.get(result.chunk_id, 0.0) + 1 / (
            k + (result.bm25_rank or k)
        )
    ordered = sorted(scores.keys(), key=lambda chunk_id: scores[chunk_id], reverse=True)[:limit]
    by_vector = {item.chunk_id: item.vector_rank for item in vector_results}
    by_bm25 = {item.chunk_id: item.bm25_rank for item in bm25_results}
    return [
        Evidence(
            chunk_id=chunk_id,
            document_id=merged[chunk_id].document_id,
            document_version_id=merged[chunk_id].document_version_id,
            text=merged[chunk_id].text,
            heading=merged[chunk_id].heading,
            page_number=merged[chunk_id].page_number,
            product_id=merged[chunk_id].product_id,
            product_model_id=merged[chunk_id].product_model_id,
            product_version_id=merged[chunk_id].product_version_id,
            vector_rank=by_vector.get(chunk_id),
            bm25_rank=by_bm25.get(chunk_id),
            rrf_score=scores[chunk_id],
            document_title=merged[chunk_id].document_title,
            source_type=merged[chunk_id].source_type,
        )
        for chunk_id in ordered
    ]


def query_terms(value: str) -> set[str]:
    """Conservative lexical coverage; never interpret ranking as correctness."""
    normalized = value.lower()
    for original, replacement in (
        ("reset", "重置"),
        ("复位", "重置"),
        ("恢复出厂", "重置"),
        ("上网", "联网"),
    ):
        normalized = normalized.replace(original, replacement)
    for filler in ("怎么办", "如何", "怎么", "可以", "是否", "请问", "请", "的", "吗", "？"):
        normalized = normalized.replace(filler, " ")
    terms = set(re.findall(r"[a-z0-9]+(?:[-.][a-z0-9]+)*", normalized))
    for run in re.findall(r"[\u4e00-\u9fff]+", normalized):
        terms.update(run[index : index + 2] for index in range(len(run) - 1))
    return terms


def assess_answerability(
    query: str,
    evidence: list[Evidence],
    filters: RetrievalFilters,
    *,
    min_evidence: int = 1,
) -> tuple[Answerability, list[str]]:
    if not query.strip() or not filters.product_id:
        return Answerability.MISSING_CONTEXT, ["需要提供问题并确认产品身份"]
    if any(word in query for word in ("拆机", "拆开", "拆卸", "起火", "冒烟", "漏电", "触电")):
        return Answerability.UNANSWERABLE, ["现有通用资料不足以支持这类维修或安全问题"]
    products = {item.product_id for item in evidence if item.product_id}
    if products - {filters.product_id}:
        return Answerability.CONFLICTED, ["召回证据与已确认产品冲突"]
    for attr in ("product_model_id", "product_version_id"):
        selected = getattr(filters, attr)
        values = {getattr(item, attr) for item in evidence if getattr(item, attr)}
        if selected and values - {selected}:
            return Answerability.CONFLICTED, ["召回证据与已确认型号或版本冲突"]
        if len(values) > 1:
            return Answerability.CONFLICTED, ["召回证据包含不同型号或版本"]
    eligible = [
        item
        for item in evidence
        if item.product_id == filters.product_id and item.source_type in {"uploaded", "official"}
    ]
    terms = query_terms(query)
    relevant = [
        item for item in eligible if query_terms(f"{item.heading or ''} {item.text}") & terms
    ]
    if not relevant:
        return Answerability.UNANSWERABLE, ["没有直接覆盖问题的可信证据"]
    # Identity words must not alone make an unrelated manual answerable. Intent
    # anchors capture the action/limitation the user actually asks about.
    intent_groups = (
        ("重置", "恢复出厂"),
        ("连接", "配网", "首次"),
        ("打印",),
        ("无响应",),
        ("离线",),
        ("联网", "上网"),
        ("5 ghz", "5ghz", "5g网络"),
        ("升级",),
        ("固件",),
        ("保修",),
        ("价格",),
        ("安全",),
        ("电源",),
        ("卡纸", "纸张"),
    )
    intent_query = query.lower().replace("复位", "重置")
    asked = [group for group in intent_groups if any(word in intent_query for word in group)]
    combined = "\n".join(f"{item.heading or ''} {item.text}".lower() for item in relevant)
    combined = combined.replace("复位", "重置")
    missing = [group for group in asked if not any(word in combined for word in group)]
    if asked and len(missing) == len(asked):
        return Answerability.UNANSWERABLE, ["召回结果未覆盖问题所需的操作或限制条件"]
    if missing or len(relevant) < min_evidence:
        return Answerability.PARTIAL, ["证据只覆盖问题的一部分，需要补充资料"]
    for attr in ("product_model_id", "product_version_id"):
        if getattr(filters, attr) and any(getattr(item, attr) is None for item in relevant):
            return Answerability.PARTIAL, ["证据未注明已确认的型号或版本适用范围"]
    if not asked:
        return Answerability.PARTIAL, ["需要更具体的问题或结构化语义评估确认意图覆盖"]
    return Answerability.ANSWERABLE, ["资料的产品适用范围与问题意图匹配"]


async def hybrid_search(
    session: AsyncSession,
    query: str,
    filters: RetrievalFilters | None = None,
    *,
    limit: int = 8,
    candidate_limit: int = 20,
) -> RetrievalResult:
    active_filters = filters or RetrievalFilters()
    trace = RetrievalTrace(
        query=query, filters=active_filters, embedding_profile=embedding_profile()
    )
    if get_settings().embedding_provider == "hash":
        trace.warnings.append("Hash embeddings are an offline baseline, not semantic embeddings")
    vector_start = time.perf_counter()
    try:
        vector_results = await vector_search(session, query, active_filters, candidate_limit)
    except EmbeddingError as exc:
        vector_results = []
        trace.warnings.append(str(exc))
    trace.vector_latency_ms = (time.perf_counter() - vector_start) * 1000
    trace.vector_candidates = len(vector_results)
    bm25_start = time.perf_counter()
    try:
        bm25_results = await bm25_search(session, query, active_filters, candidate_limit)
    except Exception as exc:
        bm25_results = []
        trace.warnings.append(f"BM25 unavailable: {type(exc).__name__}")
    trace.bm25_latency_ms = (time.perf_counter() - bm25_start) * 1000
    trace.bm25_candidates = len(bm25_results)
    fusion_start = time.perf_counter()
    evidence = reciprocal_rank_fusion(vector_results, bm25_results, limit=limit)
    trace.fusion_latency_ms = (time.perf_counter() - fusion_start) * 1000
    trace.fused_candidates = len(evidence)
    answerability, reasons = assess_answerability(query, evidence, active_filters)
    return RetrievalResult(evidence, trace, answerability, reasons)


def _to_evidence(chunk: DocumentChunk, document: Document, *, vector_rank: int) -> Evidence:
    return Evidence(
        chunk_id=chunk.id,
        document_id=document.id,
        document_version_id=chunk.document_version_id,
        text=chunk.text,
        heading=chunk.heading,
        page_number=chunk.page_number,
        product_id=document.product_id,
        product_model_id=document.product_model_id,
        product_version_id=document.product_version_id,
        document_title=document.title,
        source_type=document.source_type,
        vector_rank=vector_rank,
    )
