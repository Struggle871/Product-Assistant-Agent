from app.rag.answer import AnswerResult, CitedExcerpt
from app.rag.answer_evaluation import AnswerEvalCase, score_answer
from app.rag.retrieval import Answerability, RetrievalFilters, RetrievalResult, RetrievalTrace


def test_source_quote_with_irrelevant_extra_claim_is_not_perfect_precision() -> None:
    case = AnswerEvalCase(
        case_id="case",
        query="支持5GHz吗？",
        product_name=None,
        expected_sections=[],
        expected_answerability=Answerability.ANSWERABLE,
        expected_quotes=["不支持5GHz。"],
    )
    retrieval = RetrievalResult(
        [], RetrievalTrace("question", RetrievalFilters()), Answerability.ANSWERABLE, []
    )
    result = AnswerResult(
        retrieval,
        Answerability.ANSWERABLE,
        "answer",
        [],
        [CitedExcerpt(chunk_id="chunk", quote="不支持5GHz。售价100元。", citation="manual")],
    )
    score = score_answer(case, result)
    assert score["citation_precision"] == 0.5
    assert not score["end_to_end_correct"]
