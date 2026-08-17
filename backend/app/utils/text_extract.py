"""
Utility helpers to extract text from uploaded files and produce a
lightweight local "embedding" vector so the AI Assistant works without any
external API key.

Chunking lives in ``text_chunking.py`` and LLM-backed features (summary,
suggested questions) live in their respective services under
``app/services``.
"""
import hashlib
import re

from docx import Document as DocxDocument
from pypdf import PdfReader

EMBEDDING_DIM = 384


# def extract_text(file_path: str, file_type: str) -> str:
#     file_type = file_type.lower()
#     try:
#         if file_type == "pdf":
#             reader = PdfReader(file_path)
#             return "\n".join(page.extract_text() or "" for page in reader.pages)
#         if file_type in ("docx", "doc"):
#             doc = DocxDocument(file_path)
#             return "\n".join(p.text for p in doc.paragraphs)
#         # Fallback: treat as plain text
#         with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
#             return f.read()
#     except Exception:
#         return ""
def extract_text(file_path: str, file_type: str) -> str:
    file_type = file_type.lower()

    try:
        if file_type == "pdf":
            reader = PdfReader(file_path)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)

        elif file_type in ("docx", "doc"):
            doc = DocxDocument(file_path)
            text = "\n".join(p.text for p in doc.paragraphs)

        else:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()

        # PostgreSQL không chấp nhận NUL character
        return text.replace("\x00", "")

    except Exception:
        return ""


def embed_text(text: str) -> list[float]:
    """
    Deterministic pseudo-embedding based on token hashing (bag-of-hashed-words).
    Not semantically rich, but stable and dependency-free — good enough to
    demonstrate the pgvector pipeline end-to-end. Replace with a real
    embedding model for production-quality RAG.
    """
    vector = [0.0] * EMBEDDING_DIM
    words = re.findall(r"\w+", text.lower())
    for word in words:
        h = int(hashlib.md5(word.encode()).hexdigest(), 16)
        idx = h % EMBEDDING_DIM
        vector[idx] += 1.0
    norm = sum(v * v for v in vector) ** 0.5
    if norm > 0:
        vector = [v / norm for v in vector]
    return vector
