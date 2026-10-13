from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, Field

from app.rag.retrieval import Answerability, Evidence


class QueryType(StrEnum):
    PROCEDURE = "procedure"
    TROUBLESHOOTING = "troubleshooting"
    COMPATIBILITY = "compatibility"
    SAFETY = "safety"


@dataclass(frozen=True)
class RetrievalEvalCase:
    case_id: str
    query: str
    product_id: str
    expected_document_ids: frozenset[str]
    query_type: QueryType


@dataclass(frozen=True)
class RetrievalEvalResult:
    case_id: str
    hit_at_k: bool
    reciprocal_rank: float
    answerable: bool


DEMO_EVAL_CASES: tuple[RetrievalEvalCase, ...] = (
    RetrievalEvalCase(
        "ax55-setup",
        "Archer AX55 如何首次连接？",
        "tp-link-archer-ax55",
        frozenset({"archer-ax55"}),
        QueryType.PROCEDURE,
    ),
    RetrievalEvalCase(
        "m110w-offline",
        "LaserJet M110w 无线打印无响应怎么办？",
        "hp-laserjet-m110w",
        frozenset({"hp-m110w"}),
        QueryType.TROUBLESHOOTING,
    ),
    RetrievalEvalCase(
        "c200-wifi",
        "Tapo C200 可以连接 5 GHz Wi-Fi 吗？",
        "tp-link-tapo-c200",
        frozenset({"tapo-c200"}),
        QueryType.COMPATIBILITY,
    ),
)


def evaluate_cases(
    cases: Iterable[RetrievalEvalCase],
    retrieve: Callable[[RetrievalEvalCase], tuple[list[Evidence], bool]],
) -> list[RetrievalEvalResult]:
    results: list[RetrievalEvalResult] = []
    for case in cases:
        evidence, answerable = retrieve(case)
        rank = next(
            (
                index
                for index, item in enumerate(evidence, start=1)
                if item.document_id in case.expected_document_ids
            ),
            None,
        )
        results.append(
            RetrievalEvalResult(
                case_id=case.case_id,
                hit_at_k=rank is not None,
                reciprocal_rank=1 / rank if rank else 0.0,
                answerable=answerable,
            )
        )
    return results


class LabeledCase(BaseModel):
    case_id: str
    query: str = Field(min_length=1)
    product_name: str | None
    expected_sections: list[str]
    expected_answerability: Answerability


class EvaluationDataset(BaseModel):
    version: str
    purpose: str
    cases: list[LabeledCase] = Field(min_length=1)


class CaseMetrics(BaseModel):
    case_id: str
    expected: Answerability
    predicted: Answerability
    recall_at_10: float | None
    ndcg_at_10: float | None
    reciprocal_rank: float | None
    latency_ms: float
    warnings: list[str]


def score_case(
    case: LabeledCase,
    evidence: list[Evidence],
    predicted: Answerability,
    *,
    latency_ms: float = 0,
    warnings: list[str] | None = None,
) -> CaseMetrics:
    expected = set(case.expected_sections)
    ranked = [f"{item.document_title}::{item.heading}" for item in evidence[:10]]
    # Multiple overlapping chunks from one section must not inflate relevance.
    seen: set[str] = set()
    gains: list[int] = []
    for key in ranked:
        gains.append(int(key in expected and key not in seen))
        seen.add(key)
    dcg = sum(gain / math.log2(index + 2) for index, gain in enumerate(gains))
    ideal = sum(1 / math.log2(index + 2) for index in range(min(len(expected), 10)))
    first = next((index + 1 for index, gain in enumerate(gains) if gain), None)
    return CaseMetrics(
        case_id=case.case_id,
        expected=case.expected_answerability,
        predicted=predicted,
        recall_at_10=len(set(ranked) & expected) / len(expected) if expected else None,
        ndcg_at_10=dcg / ideal if expected else None,
        reciprocal_rank=(1 / first if first else 0) if expected else None,
        latency_ms=latency_ms,
        warnings=warnings or [],
    )


def summarize(results: list[CaseMetrics]) -> dict[str, object]:
    retrieval = [item for item in results if item.recall_at_10 is not None]
    per_class: dict[str, dict[str, float | int]] = {}
    for label in Answerability:
        true_positive = sum(item.expected == label and item.predicted == label for item in results)
        predicted = sum(item.predicted == label for item in results)
        expected = sum(item.expected == label for item in results)
        precision = true_positive / predicted if predicted else 0.0
        recall = true_positive / expected if expected else 0.0
        per_class[label.value] = {
            "support": expected,
            "precision": precision,
            "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        }
    return {
        "case_count": len(results),
        "retrieval_case_count": len(retrieval),
        "recall_at_10": sum(item.recall_at_10 or 0 for item in retrieval) / len(retrieval)
        if retrieval
        else None,
        "ndcg_at_10": sum(item.ndcg_at_10 or 0 for item in retrieval) / len(retrieval)
        if retrieval
        else None,
        "mrr_at_10": sum(item.reciprocal_rank or 0 for item in retrieval) / len(retrieval)
        if retrieval
        else None,
        "macro_f1_all_five_classes": sum(float(item["f1"]) for item in per_class.values()) / 5,
        "unsupported_classes": [
            label for label, values in per_class.items() if not values["support"]
        ],
        "per_class": per_class,
        "unsafe_answer_count": sum(
            item.predicted == Answerability.ANSWERABLE and item.expected != Answerability.ANSWERABLE
            for item in results
        ),
        "degraded_case_count": sum(bool(item.warnings) for item in results),
    }
