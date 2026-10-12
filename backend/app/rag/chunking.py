from dataclasses import dataclass

from app.rag.parsers import ParsedDocument


@dataclass(frozen=True)
class Chunk:
    index: int
    text: str
    heading: str | None
    page_number: int | None


def chunk_document(
    parsed: ParsedDocument, max_chars: int = 1200, overlap: int = 150
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for section in parsed.sections:
        text = section.text.strip()
        cursor = 0
        while cursor < len(text):
            end = min(cursor + max_chars, len(text))
            if end < len(text):
                boundary = max(text.rfind("\n", cursor, end), text.rfind("。", cursor, end))
                if boundary > cursor + max_chars // 2:
                    end = boundary + 1
            content = text[cursor:end].strip()
            if content:
                chunks.append(Chunk(len(chunks), content, section.heading, section.page_number))
            if end >= len(text):
                break
            cursor = max(end - overlap, cursor + 1)
    return chunks
