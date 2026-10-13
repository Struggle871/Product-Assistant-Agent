"""Check structured chat with a bounded synthetic source; never print credentials."""

import asyncio

from app.config import get_settings
from app.rag.answer import answer_from_retrieval
from app.rag.retrieval import (
    Answerability,
    Evidence,
    RetrievalFilters,
    RetrievalResult,
    RetrievalTrace,
)


async def main() -> None:
    filters = RetrievalFilters(product_id="synthetic")
    text = "该型号只支持2.4GHz无线网络，不支持5GHz。"
    evidence = Evidence("chunk", "doc", "version", text, "兼容性", 1, "synthetic", None, None)
    retrieval = RetrievalResult(
        [evidence], RetrievalTrace("支持5GHz吗？", filters), Answerability.PARTIAL, []
    )
    result = await answer_from_retrieval("支持5GHz无线网络吗？", filters, retrieval)
    if result.answerability != Answerability.ANSWERABLE or result.warnings or not result.excerpts:
        print(f"Chat status: {result.answerability}; warnings: {result.warnings}")
        raise RuntimeError("Structured chat or citation check failed")
    print(f"Chat ready: {get_settings().chat_model}; exact source citation validated.")


if __name__ == "__main__":
    asyncio.run(main())
