"""Generate suggested questions for an uploaded learning document.

Mirrors summary_service.py: prefers an external LLM (Gemini -> OpenAI) via
the shared gemini_provider, but always keeps a deterministic local fallback
so document processing still succeeds without an API key.
"""

from __future__ import annotations

import json
import random
import re

from app.services import gemini_provider
from app.utils.text_excerpt import representative_excerpt

DEFAULT_QUESTION_COUNT = 3
EXCERPT_MAX_CHARS = 12_000

_SYSTEM_INSTRUCTION = "Bạn là trợ lý giáo dục xuất câu hỏi gợi ý dạng JSON."

_FALLBACK_QUESTIONS = [
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


def build_suggested_questions_prompt(extracted_text: str) -> str:
    excerpt = representative_excerpt(extracted_text, max_chars=EXCERPT_MAX_CHARS)
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


def _fallback_questions(n: int) -> list[str]:
    """Local fallback: chuẩn hoá danh sách câu hỏi định hướng học tập."""
    return random.sample(_FALLBACK_QUESTIONS, min(n, len(_FALLBACK_QUESTIONS)))


def generate_suggested_questions(text: str, n: int = DEFAULT_QUESTION_COUNT) -> list[str]:
    """Generate the list stored in ``documents.suggested_questions``.

    Provider order is Gemini -> OpenAI -> local fallback list. External
    provider errors/malformed responses are swallowed deliberately so the
    document background job can still finish.
    """
    prompt = build_suggested_questions_prompt(text)

    raw = gemini_provider.generate_text(
        prompt,
        system_instruction=_SYSTEM_INSTRUCTION,
        response_json=True,
    )
    if raw:
        try:
            questions = _extract_json_array(raw)
        except (ValueError, TypeError, json.JSONDecodeError):
            questions = []
        if questions:
            return questions[:n]

    return _fallback_questions(n)
