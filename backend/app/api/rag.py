from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.rag.answer import CitedExcerpt, answer_question
from app.rag.retrieval import (
    Answerability,
    RetrievalFilters,
    RetrievalResult,
    hybrid_search,
)

router = APIRouter(prefix="/api/v1/rag", tags=["rag"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


class RetrievalRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    product_id: str | None = None
    product_model_id: str | None = None
    product_version_id: str | None = None
    language: str | None = None
    limit: int = Field(default=8, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Query must contain non-whitespace characters")
        return normalized


class EvidenceResponse(BaseModel):
    chunk_id: str
    document_id: str
    document_version_id: str
    text: str
    heading: str | None
    page_number: int | None
    product_id: str
    product_model_id: str | None
    product_version_id: str | None
    vector_rank: int | None
    bm25_rank: int | None
    rrf_score: float
    citation: str
    document_title: str
    source_type: str


class RetrievalTraceResponse(BaseModel):
    query: str
    vector_candidates: int
    bm25_candidates: int
    fused_candidates: int
    vector_latency_ms: float
    bm25_latency_ms: float
    fusion_latency_ms: float
    total_latency_ms: float
    warnings: list[str]
    embedding_profile: str


class RetrievalResponse(BaseModel):
    evidence: list[EvidenceResponse]
    answerability: Answerability
    answerability_reasons: list[str]
    trace: RetrievalTraceResponse


class AnswerResponse(RetrievalResponse):
    answer_text: str
    excerpts: list[CitedExcerpt]
    model: str | None
    prompt_version: str
    model_latency_ms: float


@router.post("/answer", response_model=AnswerResponse)
async def answer(request: RetrievalRequest, session: SessionDep) -> AnswerResponse:
    result = await answer_question(
        session,
        request.query,
        RetrievalFilters(
            product_id=request.product_id,
            product_model_id=request.product_model_id,
            product_version_id=request.product_version_id,
            language=request.language,
        ),
        limit=request.limit,
    )
    response = serialize_retrieval(result.retrieval)
    response.answerability = result.answerability
    response.answerability_reasons = result.reasons
    response.trace.warnings = result.warnings
    return AnswerResponse(
        **response.model_dump(),
        answer_text=result.answer_text,
        excerpts=result.excerpts,
        model=result.model,
        prompt_version=result.prompt_version,
        model_latency_ms=result.model_latency_ms,
    )


@router.post("/search", response_model=RetrievalResponse)
async def search(request: RetrievalRequest, session: SessionDep) -> RetrievalResponse:
    result = await hybrid_search(
        session,
        request.query,
        RetrievalFilters(
            product_id=request.product_id,
            product_model_id=request.product_model_id,
            product_version_id=request.product_version_id,
            language=request.language,
        ),
        limit=request.limit,
    )
    return serialize_retrieval(result)


def serialize_retrieval(result: RetrievalResult) -> RetrievalResponse:
    return RetrievalResponse(
        evidence=[
            EvidenceResponse(
                chunk_id=item.chunk_id,
                document_id=item.document_id,
                document_version_id=item.document_version_id,
                text=item.text,
                heading=item.heading,
                page_number=item.page_number,
                product_id=item.product_id,
                product_model_id=item.product_model_id,
                product_version_id=item.product_version_id,
                vector_rank=item.vector_rank,
                bm25_rank=item.bm25_rank,
                rrf_score=item.rrf_score,
                citation=item.citation,
                document_title=item.document_title,
                source_type=item.source_type,
            )
            for item in result.evidence
        ],
        answerability=result.answerability,
        answerability_reasons=result.answerability_reasons,
        trace=RetrievalTraceResponse(
            query=result.trace.query,
            vector_candidates=result.trace.vector_candidates,
            bm25_candidates=result.trace.bm25_candidates,
            fused_candidates=result.trace.fused_candidates,
            vector_latency_ms=result.trace.vector_latency_ms,
            bm25_latency_ms=result.trace.bm25_latency_ms,
            fusion_latency_ms=result.trace.fusion_latency_ms,
            total_latency_ms=result.trace.total_latency_ms,
            warnings=result.trace.warnings,
            embedding_profile=result.trace.embedding_profile,
        ),
    )
