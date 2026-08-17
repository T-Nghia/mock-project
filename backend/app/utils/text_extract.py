"""Extract document text and provide the legacy local embedding fallback."""

import hashlib
import logging
import re

from docx import Document as DocxDocument
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader


EMBEDDING_DIM = 384
logger = logging.getLogger(__name__)


def _extract_pdf(file_path: str) -> str:
    reader = PdfReader(file_path)
    pages = []
    for page in reader.pages:
        text = (page.extract_text() or "").strip()
        if text:
            pages.append(text)
    return "\n\n".join(pages)


def _extract_txt(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as file:
        return file.read().strip()


def _iter_docx_blocks(document):
    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield Table(child, document)


def _normalize_docx_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _format_docx_table(table: Table, table_number: int) -> str:
    if len(table.rows) < 2:
        return ""

    headers = [
        _normalize_docx_text(cell.text) or f"Cột {index}"
        for index, cell in enumerate(table.rows[0].cells, start=1)
    ]
    lines = []
    for row in table.rows[1:]:
        pairs = []
        for index, cell in enumerate(row.cells, start=1):
            value = _normalize_docx_text(cell.text)
            if not value:
                continue
            header = headers[index - 1] if index <= len(headers) else f"Cột {index}"
            pairs.append(f"{header}: {value}")
        if pairs:
            lines.append("; ".join(pairs))

    if not lines:
        return ""
    return f"[TABLE {table_number}]\n" + "\n".join(lines)


def _extract_docx(file_path: str) -> str:
    document = DocxDocument(file_path)
    blocks = []
    table_number = 0

    for block in _iter_docx_blocks(document):
        if isinstance(block, Paragraph):
            text = _normalize_docx_text(block.text)
            if text:
                blocks.append(text)
            continue

        table_number += 1
        table_text = _format_docx_table(block, table_number)
        if table_text:
            blocks.append(table_text)

    return "\n\n".join(blocks)


def extract_text(file_path: str, file_type: str) -> str:
    normalized_type = file_type.lower()
    extractors = {
        "pdf": _extract_pdf,
        "docx": _extract_docx,
        "txt": _extract_txt,
    }
    extractor = extractors.get(normalized_type)
    if extractor is None:
        logger.warning(
            "Unsupported extraction format: type=%s path=%s",
            normalized_type,
            file_path,
        )
        return ""

    try:
        return extractor(file_path).replace("\x00", "")
    except Exception:
        logger.exception(
            "Text extraction failed: type=%s path=%s",
            normalized_type,
            file_path,
        )
        return ""


def embed_text(text: str) -> list[float]:
    """Return the deterministic 384-dimensional legacy local embedding."""
    vector = [0.0] * EMBEDDING_DIM
    words = re.findall(r"\w+", text.lower())
    for word in words:
        hash_value = int(hashlib.md5(word.encode()).hexdigest(), 16)
        vector[hash_value % EMBEDDING_DIM] += 1.0
    norm = sum(value * value for value in vector) ** 0.5
    if norm > 0:
        vector = [value / norm for value in vector]
    return vector
