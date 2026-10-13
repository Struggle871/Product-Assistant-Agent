"""Validate assessment labels against demo text, without faking database retrieval."""

from pathlib import Path

import pytest

from app.rag.chunking import chunk_document
from app.rag.evaluation import EvaluationDataset, LabeledCase
from app.rag.parsers import parse_document
from app.rag.retrieval import Evidence, RetrievalFilters, assess_answerability

ROOT = Path(__file__).resolve().parents[2]
DATASET = EvaluationDataset.model_validate_json(
    (ROOT / "evals/retrieval-smoke-v1.json").read_text(encoding="utf-8")
)
FILES = {
    "Archer AX55": "archer-ax55.md",
    "LaserJet M110w": "hp-m110w.md",
    "Tapo C200": "tapo-c200.md",
}


@pytest.mark.parametrize("case", DATASET.cases, ids=lambda case: case.case_id)
def test_smoke_assessment_labels(case: LabeledCase) -> None:
    evidence: list[Evidence] = []
    if case.product_name:
        path = ROOT / "data/demo" / FILES[case.product_name]
        parsed = parse_document(path.read_bytes(), path.name, "text/markdown")
        for chunk in chunk_document(parsed):
            evidence.append(
                Evidence(
                    f"chunk-{chunk.index}",
                    path.stem,
                    "version",
                    chunk.text,
                    chunk.heading,
                    chunk.page_number,
                    case.product_name,
                    None,
                    None,
                    document_title=path.stem,
                )
            )
    actual, _ = assess_answerability(
        case.query, evidence, RetrievalFilters(product_id=case.product_name)
    )
    assert actual == case.expected_answerability
