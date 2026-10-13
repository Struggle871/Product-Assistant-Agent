"""Gold-source scoring for text answers, separate from a model's self-evaluation."""

import re

from pydantic import BaseModel, Field

from app.rag.answer import AnswerResult
from app.rag.evaluation import LabeledCase
from app.rag.retrieval import Answerability


class FixtureEvidence(BaseModel):
    chunk_id: str
    text: str
    heading: str = "测试说明"
    product_id: str = "synthetic"
    model_id: str | None = None
    version_id: str | None = None


class AnswerEvalCase(LabeledCase):
    expected_quotes: list[str] = Field(default_factory=list)
    allowed_quotes: list[str] = Field(default_factory=list)
    fixture_evidence: list[FixtureEvidence] | None = None
    selected_product_id: str | None = "synthetic"
    selected_model_id: str | None = None
    selected_version_id: str | None = None


class AnswerDataset(BaseModel):
    version: str
    purpose: str
    split: str
    annotation_status: str
    cases: list[AnswerEvalCase] = Field(min_length=1)


def score_answer(case: AnswerEvalCase, result: AnswerResult) -> dict[str, object]:
    expected = case.expected_quotes
    actual = [item.quote for item in result.excerpts]
    # Gold snippets define allowed technical claims. Exact source membership alone
    # does not establish question relevance, so it is not scored as precision.
    allowed = case.allowed_quotes or expected
    claims = [
        claim.strip()
        for quote in actual
        for claim in re.split(r"(?<=[。！？!?])|\n+", quote)
        if claim.strip()
    ]
    supported = sum(any(claim in gold for gold in allowed) for claim in claims)
    covered = sum(any(gold in quote for quote in actual) for gold in expected)
    precision = supported / len(claims) if claims else None
    recall = covered / len(expected) if expected else None
    correct_state = result.answerability == case.expected_answerability
    should_answer = case.expected_answerability in {Answerability.ANSWERABLE, Answerability.PARTIAL}
    content_ok = bool(actual) and recall == 1 and precision == 1 if should_answer else not actual
    return {
        "case_id": case.case_id,
        "expected": case.expected_answerability.value,
        "predicted": result.answerability.value,
        "citation_precision": precision,
        "citation_recall": recall,
        "end_to_end_correct": correct_state and content_ok and not result.warnings,
        "unsafe_answer": (bool(actual) and not should_answer)
        or (
            result.answerability == Answerability.ANSWERABLE
            and case.expected_answerability != Answerability.ANSWERABLE
        ),
        "model_used": result.model,
        "warnings": result.warnings,
        "answer_text": result.answer_text,
        "excerpts": [item.model_dump() for item in result.excerpts],
    }
