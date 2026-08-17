"""Shared helper to build a representative excerpt of a long document.

Used by any feature that needs to hand a bounded slice of document text to an
LLM prompt (currently SummaryService and SuggestedQuestionService) without
duplicating the head/middle/tail sampling logic in each service.
"""

from __future__ import annotations

import re

DEFAULT_MAX_CHARS = 18_000


def representative_excerpt(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """Keep head/middle/tail context for long documents without overlap.

    Short documents (<= max_chars) are returned verbatim. Long documents are
    sampled from three non-overlapping regions - 45% beginning, 30% middle,
    25% end - so prompts stay bounded while still covering the whole
    document instead of only its first page.
    """
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= max_chars:
        return clean

    head_len = int(max_chars * 0.45)
    middle_len = int(max_chars * 0.30)
    tail_len = max_chars - head_len - middle_len

    head = clean[:head_len].rsplit(" ", 1)[0]
    middle_start = max(head_len, (len(clean) - middle_len) // 2)
    middle_end = min(len(clean) - tail_len, middle_start + middle_len)
    middle = clean[middle_start:middle_end].strip()
    if " " in middle:
        middle = middle.split(" ", 1)[-1].rsplit(" ", 1)[0]
    tail = clean[-tail_len:].split(" ", 1)[-1]

    return (
        f"{head}\n\n"
        "[... phần giữa tài liệu ...]\n\n"
        f"{middle}\n\n"
        "[... phần cuối tài liệu ...]\n\n"
        f"{tail}"
    )
