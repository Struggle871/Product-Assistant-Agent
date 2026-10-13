"""Evaluate the real pgvector/BM25 pipeline against versioned smoke labels."""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.db import engine, session_factory
from app.domain.models import Document, DocumentStatus, Product
from app.infrastructure.embeddings import embedding_profile
from app.rag.evaluation import CaseMetrics, EvaluationDataset, score_case, summarize
from app.rag.retrieval import RetrievalFilters, hybrid_search

ROOT = Path(__file__).resolve().parents[2]


async def evaluate(dataset: EvaluationDataset, output: Path) -> None:
    results: list[CaseMetrics] = []
    async with session_factory() as session:
        products = {
            product.name: product.id for product in (await session.scalars(select(Product))).all()
        }
        documents = set(
            (
                await session.scalars(
                    select(Document.title).where(Document.status == DocumentStatus.READY)
                )
            ).all()
        )
        for case in dataset.cases:
            if case.product_name and case.product_name not in products:
                raise ValueError(f"Missing product {case.product_name}; run import_demo first")
            for section in case.expected_sections:
                if section.split("::", 1)[0] not in documents:
                    raise ValueError(f"Missing READY document for {section}; run import_demo first")
            filters = RetrievalFilters(
                product_id=products[case.product_name] if case.product_name else None
            )
            result = await hybrid_search(session, case.query, filters, limit=10)
            results.append(
                score_case(
                    case,
                    result.evidence,
                    result.answerability,
                    latency_ms=result.trace.total_latency_ms,
                    warnings=result.trace.warnings,
                )
            )
    await engine.dispose()
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "dataset_version": dataset.version,
        "purpose": dataset.purpose,
        "created_at": datetime.now(UTC).isoformat(),
        "embedding_profile": embedding_profile(),
        "embedding_provider": get_settings().embedding_provider,
        "embedding_model": get_settings().embedding_model,
        "assessment": "deterministic-conservative-v1",
        "summary": summarize(results),
        "cases": [item.model_dump(mode="json") for item in results],
        "acceptance_note": "Smoke evaluation only; not the full locked interview acceptance set",
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Evaluated {len(results)} cases. Report: {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "evals/retrieval-smoke-v1.json")
    parser.add_argument("--output", type=Path, default=ROOT / "evals/reports/retrieval-latest.json")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    dataset = EvaluationDataset.model_validate_json(args.dataset.read_text(encoding="utf-8"))
    ids = [case.case_id for case in dataset.cases]
    if len(set(ids)) != len(ids):
        raise ValueError("Evaluation case IDs must be unique")
    if args.validate_only:
        print(f"Valid dataset {dataset.version}: {len(ids)} cases (no retrieval executed)")
    else:
        asyncio.run(evaluate(dataset, args.output))


if __name__ == "__main__":
    main()
