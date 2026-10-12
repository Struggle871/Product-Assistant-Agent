# pyright: reportMissingTypeStubs=false, reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false

import re
from dataclasses import dataclass
from io import BytesIO

import pypdfium2 as pdfium  # pyright: ignore[reportMissingImports]
import pytesseract  # pyright: ignore[reportMissingImports]
from bs4 import BeautifulSoup
from PIL import Image
from pypdf import PdfReader


@dataclass(frozen=True)
class ParsedSection:
    text: str
    heading: str | None = None
    page_number: int | None = None


@dataclass(frozen=True)
class ParsedDocument:
    sections: list[ParsedSection]
    page_count: int


def _normalize(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text.replace("\x00", "")).strip()


def parse_markdown(content: bytes) -> ParsedDocument:
    text = content.decode("utf-8", errors="replace")
    sections: list[ParsedSection] = []
    heading: str | None = None
    buffer: list[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            if buffer:
                sections.append(ParsedSection(_normalize("\n".join(buffer)), heading))
            heading = line.lstrip("#").strip() or None
            buffer = []
        else:
            buffer.append(line)
    if buffer or heading:
        sections.append(ParsedSection(_normalize("\n".join(buffer)), heading))
    return ParsedDocument([section for section in sections if section.text], 1)


def parse_html(content: bytes) -> ParsedDocument:
    soup = BeautifulSoup(content.decode("utf-8", errors="replace"), "html.parser")
    for element in soup(["script", "style", "noscript"]):
        element.decompose()
    sections: list[ParsedSection] = []
    current_heading: str | None = None
    buffer: list[str] = []
    for element in soup.find_all(["h1", "h2", "h3", "p", "li", "pre", "table"]):
        text = str(element.get_text(" ", strip=True))
        if not text:
            continue
        if element.name in {"h1", "h2", "h3"}:
            if buffer:
                sections.append(ParsedSection(_normalize("\n".join(buffer)), current_heading))
                buffer = []
            current_heading = text
        else:
            buffer.append(text)
    if buffer:
        sections.append(ParsedSection(_normalize("\n".join(buffer)), current_heading))
    return ParsedDocument(sections, 1)


def _ocr_pdf_page(content: bytes, page_index: int) -> str:
    document = pdfium.PdfDocument(content)
    page = document[page_index]
    bitmap = page.render(scale=2)
    image: Image.Image = bitmap.to_pil()
    return str(pytesseract.image_to_string(image, lang="chi_sim+eng"))


def parse_pdf(content: bytes) -> ParsedDocument:
    reader = PdfReader(BytesIO(content))
    sections: list[ParsedSection] = []
    for index, page in enumerate(reader.pages):
        text = _normalize(page.extract_text() or "")
        if len(text) < 40:
            text = _normalize(_ocr_pdf_page(content, index))
        if text:
            sections.append(
                ParsedSection(text=text, heading=f"Page {index + 1}", page_number=index + 1)
            )
    return ParsedDocument(sections, len(reader.pages))


def parse_document(content: bytes, filename: str, content_type: str) -> ParsedDocument:
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if content_type == "application/pdf" or suffix == "pdf":
        return parse_pdf(content)
    if content_type in {"text/html", "application/xhtml+xml"} or suffix in {"html", "htm"}:
        return parse_html(content)
    if content_type in {"text/markdown", "text/plain"} or suffix in {"md", "markdown", "txt"}:
        return parse_markdown(content)
    raise ValueError(f"Unsupported document format: {content_type or suffix}")
