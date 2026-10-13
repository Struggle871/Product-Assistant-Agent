import pytest

from app.rag.evaluation import LabeledCase, score_case, summarize
from app.rag.retrieval import Answerability, Evidence


def test_duplicate_sections_do_not_inflate_ndcg_or_recall() -> None:
    case = LabeledCase(
        case_id="case",
        query="如何重置？",
        product_name="product",
        expected_sections=["manual::reset", "manual::warning"],
        expected_answerability=Answerability.ANSWERABLE,
    )

    def item(chunk: str, heading: str) -> Evidence:
        return Evidence(
            chunk, "doc", "v", "text", heading, None, "product", None, None, document_title="manual"
        )

    result = score_case(case, [item("1", "reset"), item("2", "reset")], Answerability.ANSWERABLE)
    assert result.recall_at_10 == 0.5
    assert result.ndcg_at_10 == pytest.approx(1 / (1 + 1 / 1.584962500721156))


def test_negative_case_is_counted_as_unsafe_when_answered() -> None:
    case = LabeledCase(
        case_id="negative",
        query="最新价格",
        product_name="product",
        expected_sections=[],
        expected_answerability=Answerability.UNANSWERABLE,
    )
    result = score_case(case, [], Answerability.ANSWERABLE)
    report = summarize([result])
    assert report["unsafe_answer_count"] == 1
    assert report["retrieval_case_count"] == 0
    assert report["recall_at_10"] is None
    assert "CONFLICTED" in report["unsupported_classes"]
