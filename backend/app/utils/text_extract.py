"""
Utility helpers to extract text from uploaded files, split into chunks,
build a simple extractive summary, and produce a lightweight local
"embedding" vector so the AI Assistant works without any external API key.
"""
import hashlib
import json
import re

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    import google.generativeai as genai
except ImportError:
    genai = None

from docx import Document as DocxDocument
from pypdf import PdfReader

from app.core.config import settings

EMBEDDING_DIM = 384

STOP_STARTS = {
    "Để",
    "Khi",
    "Nếu",
    "Nơi",
    "Một",
    "Các",
    "Những",
    "Do",
    "Bởi",
    "Với",
    "Theo",
    "Trong",
    "Nguồn",
    "Tác giả",
    "Chương",
    "Bài",
    "Slide",
    "Trang",
    "Đại",
    "Học",
    "Trường",
    "Khoa",
    "Bộ",
    "Môn",
    "Viện",
    "Cộng",
    "Hòa",
    "Xã",
    "Hội",
    "Chủ",
    "Nghĩa",
    "Độc",
    "Lập",
    "Tự",
    "Do",
    "Hạnh",
    "Phúc",
}


def extract_text(file_path: str, file_type: str) -> str:
    file_type = file_type.lower()
    try:
        if file_type == "pdf":
            reader = PdfReader(file_path)
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        if file_type in ("docx", "doc"):
            doc = DocxDocument(file_path)
            return "\n".join(p.text for p in doc.paragraphs)

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


def _clean_academic_headers(text: str) -> str:
    """Loại bỏ tiêu ngữ hành chính, từ rác, và các dòng tên tác giả/giảng viên/học vị tổng quát (Việt & Anh)."""
    if not text:
        return ""
    clean = re.sub(
        r"(?:CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM|Độc lập\s*-\s*Tự do\s*-\s*Hạnh phúc|ĐẠI HỌC QUỐC GIA\s*[\w\s]*|TRƯỜNG ĐẠI HỌC\s*[\w\s]*|ĐỀ CƯƠNG CHI TIẾT\s*[\w\s]*|ĐỀ CƯƠNG MÔN HỌC)",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    clean = re.sub(
        r"\b(?:Tác giả|Giảng viên|Biên soạn|Phản biện|Nguồn|Author|Authors|Lecturer|By|Edited by|Written by|Email|Điện thoại|Phone|Fax)\s*:?\s*.*$",
        " ",
        clean,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    clean = re.sub(
        r"\b(?:GS\.|PGS\.|TS\.|ThS\.|BS\.|Dr\.|Prof\.|Ph\.D\.|PhD|MSc)\s+[A-ZÀÁẢẠÃĂẮẰẲẶẴÂẤẦẨẬẪĐÈÉẺẸẼÊẾỀỂỆỄÌÍỈỊĨÒÓỎỌÕÔỐỒỔỘỖƠỚỜỞỢỠÙÚỦỤŨƯỨỪỬỰỮỲÝỶỊỸa-z\s]+",
        " ",
        clean,
        flags=re.IGNORECASE,
    )
    clean = re.sub(r"[\-*=\:\._]{3,}", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def make_summary(text: str, max_sentences: int = 3) -> str:
    clean_text = _clean_academic_headers(text)
    if not clean_text:
        return "(Không thể trích xuất nội dung tài liệu để tóm tắt tự động.)"
    sentences = re.split(r"(?<=[.!?])\s+", clean_text)
    return " ".join(sentences[:max_sentences])[:1000]


def _take_first_words(text: str, max_words: int = 2000) -> str:
    clean_text = _clean_academic_headers(text)
    words = clean_text.split()
    if len(words) <= max_words:
        return clean_text
    return " ".join(words[:max_words]).strip()


def build_suggested_questions_prompt(extracted_text: str) -> str:
    excerpt = _take_first_words(extracted_text, 2000)
    return f"""
Bạn là một trợ lý giáo dục cao cấp. Hãy phân tích đoạn văn bản tài liệu dưới đây và tạo ra
đúng 3 câu hỏi gợi ý tự nhiên, thông minh bằng tiếng Việt mà người học/sinh viên sẽ muốn hỏi AI.

Nội dung tài liệu:
{excerpt}

Quy tắc bắt buộc (Strict Context Grounding):
1. Mỗi câu hỏi phải là một câu hỏi tự nhiên, hoàn chỉnh.
2. CHỈ ĐẶT CÂU HỎI CHO NHỮNG NỘI DUNG THỰC SỰ CÓ MẶT TRONG ĐOẠN VĂN BẢN TRÊN (Nếu tài liệu có ghi thông tin về cách chấm điểm/thi cử -> hỏi về điểm/thi; nếu có ghi giáo trình tham khảo -> hỏi về giáo trình; nếu chỉ có thuật ngữ môn học -> hỏi về thuật ngữ). Tuyệt đối không tự bịa ra thông tin không có trong văn bản.
3. Trả về đúng JSON object chuẩn dạng:
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
            clean_q = re.sub(r"\s+", " ", item).strip()
            if clean_q:
                questions.append(clean_q)
    return questions


def _extract_clean_terms(text: str) -> list[str]:
    """Trích xuất các thuật ngữ/tiêu đề viết hoa chuẩn (2-4 từ), loại bỏ hoàn toàn từ rác bằng pattern tổng quát."""
    clean = _clean_academic_headers(text)
    clean = re.sub(r"\S+@\S+", "", clean)
    clean = re.sub(r"https?://\S+", "", clean)

    terms: list[str] = []
    seen: set[str] = set()

    matches = re.finditer(
        r"\b([A-ZÀÁẢẠÃĂẮẰẲẶẴÂẤẦẨẬẪĐÈÉẺẸẼÊẾỀỂỆỄÌÍỈỊĨÒÓỎỌÕÔỐỒỔỘỖƠỚỜỞỢỠÙÚỦỤŨƯỨỪỬỰỮỲÝỶỊỸ][a-zàáảạãăắằẳặcẵâấtầnẩậnẫđèéẻẹẽêếềểệễìíỉịĩòóỏọõôốồổộỗơớờởợỡùúủụũưứừửựữỳýỷịỹ0-9]*+(?:\s+[A-ZÀÁẢẠÃĂẮẰẲẶẴÂẤẦẨẬẪĐÈÉẺẸẼÊẾỀỂỆỄÌÍỈỊĨÒÓỎỌÕÔỐỒỔỘỖƠỚỜỞỢỠÙÚỦỤŨƯỨỪỬỰỮỲÝỶỊỸa-zàáảạãăắằẳặcẵâấtầnẩậnẫđèéẻẹẽêếềểệễìíỉịĩòóỏọõôốồổộỗơớờởợỡùúủụũưứừửựữỳýỷịỹ0-9]+){1,3})\b",
        clean,
    )

    for match in matches:
        term = match.group(0).strip().rstrip(",;:-.")
        words = term.split()
        first_word = words[0]

        if first_word in STOP_STARTS:
            continue
        if len(term) >= 8 and len(term) <= 45 and term not in seen:
            seen.add(term)
            terms.append(term)

    return terms


def suggest_questions(text: str, n: int = 4) -> list[str]:
    """
    Hybrid Strategy 3 (Strict Grounding):
    1. Lọc bỏ tiêu ngữ hành chính và thông tin tác giả/học vị.
    2. Trích xuất thuật ngữ chuẩn (không dính từ rác hay câu cắt dở).
    3. Nếu có thuật ngữ chuẩn -> Tạo câu hỏi tự nhiên theo thuật ngữ đó.
    4. Nếu không tìm được -> Tự động fallback về danh sách câu hỏi định hướng học tập chuẩn 100%.
    """
    clean_text = _clean_academic_headers(text)
    terms = _extract_clean_terms(clean_text)

    templates = [
        'Khái niệm và nguyên lý của "{term}" được giải thích như thế nào?',
        'Tài liệu phân tích nội dung gì liên quan đến "{term}"?',
        'Ứng dụng và ý nghĩa của "{term}" được trình bày ra sao?',
    ]

    questions: list[str] = []
    for i, term in enumerate(terms[:n]):
        template = templates[i % len(templates)]
        questions.append(template.format(term=term))

    high_level_fallbacks = [
        "Tóm tắt các nội dung cốt lõi và kiến thức trọng tâm của tài liệu này?",
        "Những khái niệm hoặc định nghĩa quan trọng nhất được đề cập là gì?",
        "Các phương pháp hoặc thuật toán chính trong bài giảng được giải thích ra sao?",
        "Tài liệu này phù hợp để ôn tập phần kiến thức nào?",
    ]

    for q in high_level_fallbacks:
        if len(questions) >= n:
            break
        if q not in questions:
            questions.append(q)

    return questions[:n]


def generate_suggested_questions(text: str, n: int = 3) -> list[str]:
    fallback = suggest_questions(text, n=n)

    gemini_key = settings.GEMINI_API_KEY.strip()
    if gemini_key and genai is not None:
        gemini_models = ["gemini-2.5-flash", "gemini-flash-latest", "gemini-2.5-pro", "gemini-1.5-flash"]
        for m_name in gemini_models:
            try:
                genai.configure(api_key=gemini_key)
                model = genai.GenerativeModel(m_name)
                prompt = build_suggested_questions_prompt(text)
                response = model.generate_content(prompt)
                content = response.text or ""
                questions = _extract_json_array(content)
                if questions:
                    return questions[:n]
            except Exception as e:
                print(f"[Gemini API Error - {m_name}]: {e}")

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
        except Exception as e:
            print(f"[OpenAI API Error]: {e}")

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
