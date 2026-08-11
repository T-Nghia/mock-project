"""
Utility helpers to extract text from uploaded files, split into chunks,
build a simple extractive summary, and produce a lightweight local
"embedding" vector so the AI Assistant works without any external API key.
Swap the embed_text() implementation for a real embedding model/provider
(OpenAI, sentence-transformers, etc.) when you're ready to go beyond the MVP.
"""
import json
import hashlib
import re

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    import google.generativeai as genai
except ImportError:
    genai = None

from pypdf import PdfReader
from docx import Document as DocxDocument

from app.core.config import settings

EMBEDDING_DIM = 384


def extract_text(file_path: str, file_type: str) -> str:
    file_type = file_type.lower()
    try:
        if file_type == "pdf":
            reader = PdfReader(file_path)
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        if file_type in ("docx", "doc"):
            doc = DocxDocument(file_path)
            return "\n".join(p.text for p in doc.paragraphs)
        # Fallback: treat as plain text
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


def make_summary(text: str, max_sentences: int = 3) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return "(Không thể trích xuất nội dung tài liệu để tóm tắt tự động.)"
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(sentences[:max_sentences])[:1000]


def _take_first_words(text: str, max_words: int = 2000) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text.strip()
    return " ".join(words[:max_words]).strip()


def build_suggested_questions_prompt(extracted_text: str) -> str:
    excerpt = _take_first_words(extracted_text, 2000)
    return f"""
Bạn là một trợ lý giáo dục thông minh. Hãy đọc đoạn văn bản tài liệu dưới đây và tạo ra
đúng 3 câu hỏi gợi ý ngắn gọn, tự nhiên bằng tiếng Việt mà người học sẽ muốn hỏi AI về tài
liệu này.

Nội dung tài liệu:
{excerpt}

Yêu cầu: Trả về đúng JSON object chuẩn, không thêm giải thích, không bọc markdown,
không dùng văn bản ngoài JSON. Schema bắt buộc:
{{"questions": ["Câu hỏi 1?", "Câu hỏi 2?", "Câu hỏi 3?"]}}
""".strip()


def _extract_json_array(raw_text: str) -> list[str]:
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE | re.DOTALL)

    data = json.loads(cleaned)
    if isinstance(data, dict):
        data = data.get("questions", [])
    if not isinstance(data, list):
        raise ValueError("LLM response is not a JSON array")

    questions: list[str] = []
    for item in data:
        if isinstance(item, str):
            question = item.strip()
            if question:
                questions.append(question)
    return questions


def generate_suggested_questions(text: str, n: int = 3) -> list[str]:
    fallback = suggest_questions(text, n=n)

    # 1. Try Google Gemini API if GEMINI_API_KEY is provided
    gemini_key = settings.GEMINI_API_KEY.strip()
    if gemini_key and genai is not None:
        try:
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            prompt = build_suggested_questions_prompt(text)
            response = model.generate_content(prompt)
            content = response.text or ""
            questions = _extract_json_array(content)
            if questions:
                return questions[:n]
        except Exception:
            pass

    # 2. Try OpenAI API if OPENAI_API_KEY is provided
    openai_key = settings.OPENAI_API_KEY.strip()
    if openai_key and OpenAI is not None:
        try:
            prompt = build_suggested_questions_prompt(text)
            client = OpenAI(api_key=openai_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that outputs JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )
            content = response.choices[0].message.content or ""
            questions = _extract_json_array(content)
            if questions:
                return questions[:n]
        except Exception:
            pass

    # 3. Fallback to local extraction
    return fallback[:n]


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


def suggest_questions(text: str, n: int = 4) -> list[str]:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 20]
    questions = []
    for s in sentences[: n * 3]:
        if len(questions) >= n:
            break
        snippet = s[:80]
        questions.append(f"Tài liệu này nói gì về: \"{snippet}...\"?")
    if not questions:
        questions = [
            "Tài liệu này nói về chủ đề gì?",
            "Hãy tóm tắt nội dung chính của tài liệu.",
        ]
    return questions[:n]
