from app.rag.chunking import chunk_document
from app.rag.parsers import ParsedDocument, ParsedSection


def test_chunking_keeps_metadata_and_overlap() -> None:
    parsed = ParsedDocument(
        sections=[ParsedSection("A" * 80, heading="Reset", page_number=3)],
        page_count=3,
    )

    chunks = chunk_document(parsed, max_chars=50, overlap=10)

    assert len(chunks) == 2
    assert chunks[0].text[-10:] == chunks[1].text[:10]
    assert all(chunk.heading == "Reset" for chunk in chunks)
    assert all(chunk.page_number == 3 for chunk in chunks)
