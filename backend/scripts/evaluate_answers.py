"""Evaluate Qwen text routing/citations against versioned demo or synthetic gold."""

import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.db import engine, session_factory
from app.domain.models import Product
from app.rag.answer import PROMPT_VERSION, SYSTEM, answer_from_retrieval
from app.rag.answer_evaluation import AnswerDataset, score_answer
from app.rag.evaluation import CaseMetrics, score_case, summarize
from app.rag.retrieval import (
    Answerability,
    Evidence,
    RetrievalFilters,
    RetrievalResult,
    RetrievalTrace,
    hybrid_search,
)

ROOT = Path(__file__).resolve().parents[2]


async def evaluate(dataset: AnswerDataset, dataset_hash: str, output: Path) -> None:
    metrics: list[CaseMetrics] = []
    answers: list[dict[str, object]] = []
    async with session_factory() as session:
        products: dict[str, str] = {}
        if any(case.fixture_evidence is None for case in dataset.cases):
            products = {p.name: p.id for p in (await session.scalars(select(Product))).all()}
        for case in dataset.cases:
            if case.fixture_evidence is not None:
                filters = RetrievalFilters(
                    product_id=case.selected_product_id,
                    product_model_id=case.selected_model_id,
                    product_version_id=case.selected_version_id,
                )
                evidence = [
                    Evidence(
                        item.chunk_id,
                        "fixture",
                        "fixture",
                        item.text,
                        item.heading,
                        1,
                        item.product_id,
                        item.model_id,
                        item.version_id,
                        document_title="合成评测说明",
                    )
                    for item in case.fixture_evidence
                ]
                retrieval = RetrievalResult(
                    evidence, RetrievalTrace(case.query, filters), Answerability.UNANSWERABLE, []
                )
            else:
                if case.product_name and case.product_name not in products:
                    raise ValueError("Required demo product is missing; run import_demo first")
                filters = RetrievalFilters(product_id=products.get(case.product_name or ""))
                retrieval = await hybrid_search(session, case.query, filters, limit=10)
            result = await answer_from_retrieval(case.query, filters, retrieval)
            metrics.append(
                score_case(
                    case,
                    retrieval.evidence,
                    result.answerability,
                    latency_ms=retrieval.trace.total_latency_ms,
                    warnings=result.warnings,
                )
            )
            answers.append(score_answer(case, result))
            print(f"{case.case_id}: {result.answerability.value}", flush=True)
    await engine.dispose()
    summary = summarize(metrics)
    precision = [
        float(a["citation_precision"]) for a in answers if a["citation_precision"] is not None
    ]
    recall = [float(a["citation_recall"]) for a in answers if a["citation_recall"] is not None]
    summary.update(
        {
            "citation_precision": sum(precision) / len(precision) if precision else None,
            "citation_recall": sum(recall) / len(recall) if recall else None,
            "end_to_end_accuracy": sum(bool(a["end_to_end_correct"]) for a in answers)
            / len(answers),
            "unsafe_answer_rate": sum(bool(a["unsafe_answer"]) for a in answers)
            / max(
                1,
                sum(
                    case.expected_answerability != Answerability.ANSWERABLE
                    for case in dataset.cases
                ),
            ),
        }
    )
    quality_passed = (
        not summary["unsupported_classes"]
        and float(summary["macro_f1_all_five_classes"]) >= 0.85
        and summary["unsafe_answer_rate"] <= 0.02
        and (summary["citation_precision"] or 0) >= 0.95
        and (summary["citation_recall"] or 0) >= 0.9
        and summary["end_to_end_accuracy"] >= 0.85
        and not summary["degraded_case_count"]
    )
    report = {
        "dataset_version": dataset.version,
        "dataset_sha256": dataset_hash,
        "split": dataset.split,
        "evaluation_role": (
            "held-out candidate; labels still require independent human review"
            if dataset.split == "held-out-candidate"
            else "regression; not an independent blind acceptance set"
        ),
        "annotation_status": dataset.annotation_status,
        "created_at": datetime.now(UTC).isoformat(),
        "model": get_settings().chat_model,
        "prompt_version": PROMPT_VERSION,
        "system_prompt_sha256": hashlib.sha256(SYSTEM.encode()).hexdigest(),
        "thinking_enabled": get_settings().chat_enable_thinking,
        "thinking_budget": get_settings().chat_thinking_budget,
        "structured_output": get_settings().chat_structured_output,
        "summary": summary,
        "automated_text_thresholds_passed": quality_passed,
        "stage3_accepted": False,
        "acceptance_note": "Agent-authored synthetic labels require independent human review; "
        "synthetic routing tests do not replace database retrieval acceptance.",
        "cases": answers,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report: {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "evals/answer-synthetic-v1.json")
    parser.add_argument("--output", type=Path, default=ROOT / "evals/reports/answers-latest.json")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    raw = args.dataset.read_bytes()
    dataset = AnswerDataset.model_validate_json(raw)
    if len({case.case_id for case in dataset.cases}) != len(dataset.cases):
        raise ValueError("Case IDs must be unique")
    if args.validate_only:
        print(
            f"Valid dataset: {dataset.version}; {len(dataset.cases)} cases; "
            f"sha256={hashlib.sha256(raw).hexdigest()}"
        )
    else:
        asyncio.run(evaluate(dataset, hashlib.sha256(raw).hexdigest(), args.output))


if __name__ == "__main__":
    main()
