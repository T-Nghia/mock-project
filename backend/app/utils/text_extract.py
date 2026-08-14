"""
Utility helpers to extract text from uploaded files, split into chunks,
build a simple extractive summary, and produce a lightweight local
"embedding" vector so the AI Assistant works without any external API key.
"""
import hashlib
import json
import logging
import re
import random

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    import google.generativeai as genai
except ImportError:
    genai = None

from docx import Document as DocxDocument
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader

from app.core.config import settings

EMBEDDING_DIM = 384
logger = logging.getLogger(__name__)

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
        return extractor(file_path)
    except Exception:
        logger.exception(
            "Text extraction failed: type=%s path=%s",
            normalized_type,
            file_path,
        )
        return ""


def _hard_split(text: str, max_chars: int) -> list[str]:
    return [text[index : index + max_chars] for index in range(0, len(text), max_chars)]


def _split_words(text: str, max_chars: int) -> list[str]:
    units = []
    current = []
    current_length = 0

    for word in text.split():
        if len(word) > max_chars:
            if current:
                units.append(" ".join(current))
                current = []
                current_length = 0
            units.extend(_hard_split(word, max_chars))
            continue

        candidate_length = current_length + (1 if current else 0) + len(word)
        if current and candidate_length > max_chars:
            units.append(" ".join(current))
            current = [word]
            current_length = len(word)
        else:
            current.append(word)
            current_length = candidate_length

    if current:
        units.append(" ".join(current))
    return units


_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?。！？])\s+")
_TABLE_MARKER_RE = re.compile(r"^\[TABLE \d+\]$")


def _pack_parts(parts: list[str], max_chars: int, separator: str) -> list[str]:
    packed = []
    current = ""
    for part in parts:
        if not part:
            continue
        candidate = f"{current}{separator}{part}" if current else part
        if current and len(candidate) > max_chars:
            packed.append(current)
            current = part
        else:
            current = candidate
    if current:
        packed.append(current)
    return packed


def _split_ordinary_block(block: str, max_chars: int) -> list[str]:
    normalized = re.sub(r"\s+", " ", block).strip()
    if not normalized:
        return []
    if len(normalized) <= max_chars:
        return [normalized]

    sentences = [part.strip() for part in _SENTENCE_BOUNDARY_RE.split(normalized) if part.strip()]
    bounded = []
    for sentence in sentences:
        if len(sentence) <= max_chars:
            bounded.append(sentence)
        else:
            bounded.extend(_split_words(sentence, max_chars))
    return _pack_parts(bounded, max_chars, " ")


def _split_blocks(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    return [block.strip() for block in re.split(r"\n\s*\n+", normalized) if block.strip()]


def _is_table_block(block: str) -> bool:
    first_line = block.splitlines()[0].strip() if block.splitlines() else ""
    return bool(_TABLE_MARKER_RE.fullmatch(first_line))


def _split_table_block(block: str, max_chars: int) -> list[str]:
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    if len(lines) < 2:
        return _split_ordinary_block(block, max_chars)

    marker = lines[0]
    content_budget = max_chars - len(marker) - 1
    if content_budget <= 0:
        return _split_ordinary_block(block, max_chars)

    row_fragments = []
    for row in lines[1:]:
        if len(row) <= content_budget:
            row_fragments.append(row)
        else:
            row_fragments.extend(_split_ordinary_block(row, content_budget))

    row_groups = _pack_parts(row_fragments, content_budget, "\n")
    return [f"{marker}\n{group}" for group in row_groups if group]


def _build_units(text: str, max_chars: int) -> list[str]:
    units = []
    for block in _split_blocks(text):
        if _is_table_block(block):
            units.extend(_split_table_block(block, max_chars))
        else:
            units.extend(_split_ordinary_block(block, max_chars))
    return units


def _join_units(units: list[str]) -> str:
    return "\n\n".join(units)


def _select_overlap_units(units: list[str], overlap_chars: int) -> list[str]:
    if overlap_chars == 0:
        return []

    selected = []
    for unit in reversed(units):
        candidate = [unit, *selected]
        if len(_join_units(candidate)) > overlap_chars:
            break
        selected = candidate
    return selected


def _pack_units(units: list[str], max_chars: int, overlap_chars: int) -> list[str]:
    chunks = []
    current = []

    for unit in units:
        candidate = _join_units([*current, unit])
        if not current or len(candidate) <= max_chars:
            current.append(unit)
            continue

        chunks.append(_join_units(current))
        overlap = _select_overlap_units(current, overlap_chars)
        while overlap and len(_join_units([*overlap, unit])) > max_chars:
            overlap.pop(0)
        current = [*overlap, unit]

    if current:
        chunks.append(_join_units(current))
    return chunks


def chunk_text(
    text: str,
    max_chars: int = 1200,
    overlap_chars: int = 200,
) -> list[str]:
    if max_chars <= 0:
        raise ValueError("max_chars must be greater than zero")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be between zero and max_chars - 1")

    if not text or not text.strip():
        return []
    units = _build_units(text, max_chars)
    return _pack_units(units, max_chars, overlap_chars)


def _clean_academic_headers(text: str) -> str:
    """Loại bỏ tiêu ngữ hành chính, từ rác, và các dòng tên tác giả/giảng viên/học vị tổng quát (Việt & Anh)."""
    if not text:
        return ""
    # 1. Xoá tiêu ngữ hành chính Việt Nam & Tên trường/khoa
    clean = re.sub(
        r"(?:CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM|Độc lập\s*-\s*Tự do\s*-\s*Hạnh phúc|ĐẠI HỌC QUỐC GIA\s*[\w\s]*|TRƯỜNG ĐẠI HỌC\s*[\w\s]*|ĐỀ CƯƠNG CHI TIẾT\s*[\w\s]*|ĐỀ CƯƠNG MÔN HỌC)",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    # 2. Xoá dòng tên tác giả / giảng viên / học vị (Hỗ trợ quốc tế & Việt Nam)
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


def _sample_representative_text(text: str, target_words: int = 2000) -> str:
    """
    Trích mẫu đại diện 3 phân vùng (Head + Middle + Tail) cho tài liệu dài:
    - File ngắn (<= 2000 từ ~ 1-5 trang A4): Trả về 100% nguyên văn (KHÔNG CẮT GHÉP, KHÔNG LẶP).
    - File dài (> 2000 từ ~ 6-50+ trang): Trích mẫu 3 vùng đảm bảo chỉ số tuyệt đối không chồng lấp.
    """
    clean_text = _clean_academic_headers(text)
    words = clean_text.split()
    total_words = len(words)

    # 1. Nếu file ngắn (<= 2000 từ): Trả về 100% nguyên văn, không bị lặp hay cắt chữ
    if total_words <= target_words:
        return clean_text

    # 2. Nếu file dài (> 2000 từ): Trích mẫu 3 phần với chỉ số không bao giờ chồng lấp
    head_count = 700
    tail_count = 400
    mid_count = 700

    head_part = " ".join(words[:head_count])

    # Đảm bảo phần Giữa nằm lọt lòng giữa phần Đầu và phần Cuối
    mid_start = max(head_count, (total_words - mid_count) // 2)
    mid_end = min(total_words - tail_count, mid_start + mid_count)

    mid_part = " ".join(words[mid_start:mid_end])
    tail_part = " ".join(words[-tail_count:])

    return f"{head_part}\n\n[...Nội dung phần giữa tài liệu...]\n\n{mid_part}\n\n[...Nội dung phần cuối tài liệu...]\n\n{tail_part}"


def build_suggested_questions_prompt(extracted_text: str) -> str:
    excerpt = _sample_representative_text(extracted_text, 2000)
    return f"""
Bạn là một trợ lý giáo dục cao cấp. Hãy phân tích đoạn văn bản đại diện (gồm Phần đầu, Phần giữa và Phần cuối tài liệu) dưới đây và tạo ra
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


def suggest_questions(text: str, n: int = 4) -> list[str]:
    """
    Local Fallback: Trả về danh sách các câu hỏi định hướng học tập chuẩn mực 100%,
    đảm bảo câu cú tự nhiên, không bị rác hay lỗi bóc tách thuật ngữ.
    """
    high_level_fallbacks = [
        # --- Nhóm tóm tắt & Ý chính ---
        "Tóm tắt các nội dung cốt lõi và kiến thức trọng tâm của tài liệu này?",
        "Ý nghĩa hoặc thông điệp chính mà tài liệu muốn truyền tải là gì?",
        "Những kết luận quan trọng nhất được rút ra ở cuối tài liệu là gì?",
        
        # --- Nhóm khái niệm & Thuật ngữ ---
        "Những khái niệm hoặc định nghĩa quan trọng nhất được đề cập là gì?",
        "Các thuật ngữ chuyên ngành nào xuất hiện thường xuyên và ý nghĩa của chúng?",
        
        # --- Nhóm phương pháp & Cấu trúc ---
        "Các phương pháp, mô hình hoặc thuật toán chính được giải thích ra sao?",
        "Quy trình hoặc các bước thực hiện trọng tâm được trình bày trong tài liệu là gì?",
        
        # --- Nhóm ứng dụng & Ví dụ ---
        "Kiến thức trong tài liệu này có thể ứng dụng vào thực tế hoặc bài tập như thế nào?",
        "Có những ví dụ minh họa hoặc tình huống thực tế (case study) nổi bật nào trong bài?",
        
        # --- Nhóm phân tích & Đánh giá ---
        "Tài liệu có chỉ ra những ưu điểm và hạn chế của vấn đề đang bàn luận không?",
        "Có những luận điểm hoặc bằng chứng nào nổi bật được sử dụng trong tài liệu?",
        
        # --- Nhóm định hướng học tập ---
        "Tài liệu này phù hợp để ôn tập hoặc nghiên cứu sâu về mảng kiến thức nào?",
        "Phạm vi nghiên cứu hoặc đối tượng người học mà tài liệu hướng tới là ai?",
    ]
    return random.sample(high_level_fallbacks, min(n, len(high_level_fallbacks)))


def generate_suggested_questions(text: str, n: int = 3) -> list[str]:
    fallback = suggest_questions(text, n=n)

    # 1. Try Google Gemini API if GEMINI_API_KEY is provided
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
