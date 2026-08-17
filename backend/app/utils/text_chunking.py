"""Split extracted document text into bounded character or token chunks."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.utils.text_extract import ExtractedBlock


@dataclass(frozen=True)
class ChunkData:
    content: str
    heading_path: list[str]


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
_LOCAL_TOKEN_RE = re.compile(r"\w+|[^\w\s]", flags=re.UNICODE)


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


def chunk_text(text: str, max_chars: int = 1200, overlap_chars: int = 200) -> list[str]:
    if max_chars <= 0:
        raise ValueError("max_chars must be greater than zero")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be between zero and max_chars - 1")
    if not text or not text.strip():
        return []
    return _pack_units(_build_units(text, max_chars), max_chars, overlap_chars)


def _local_tokens(text: str) -> list[str]:
    return _LOCAL_TOKEN_RE.findall(text)


def count_local_tokens(text: str) -> int:
    return len(_local_tokens(text))


def chunk_text_by_tokens(
    text: str,
    max_tokens: int = 500,
    overlap_tokens: int = 80,
) -> list[str]:
    if max_tokens <= 0:
        raise ValueError("max_tokens must be greater than zero")
    if overlap_tokens < 0 or overlap_tokens >= max_tokens:
        raise ValueError("overlap_tokens must be between zero and max_tokens - 1")
    tokens = _local_tokens(text)
    if not tokens:
        return []
    step = max_tokens - overlap_tokens
    return [
        " ".join(tokens[start : start + max_tokens])
        for start in range(0, len(tokens), step)
    ]


def _split_sentences(text: str) -> list[str]:
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?。！？])\s+|\n+", text.strip())
        if sentence.strip()
    ]


def _split_block_units(block: ExtractedBlock, max_tokens: int) -> list[str]:
    if block.kind == "table":
        lines = [line.strip() for line in block.text.splitlines() if line.strip()]
        if not lines:
            return []
        marker = lines[0]
        rows = lines[1:] or lines
        units = []
        current = [marker]
        for row in rows:
            candidate = "\n".join([*current, row])
            if len(_local_tokens(candidate)) <= max_tokens:
                current.append(row)
            else:
                if len(current) > 1:
                    units.append("\n".join(current))
                    current = [marker, row]
                else:
                    units.extend(
                        f"{marker}\n{part}"
                        for part in chunk_text_by_tokens(row, max_tokens=max_tokens, overlap_tokens=0)
                    )
                    current = [marker]
        if len(current) > 1:
            units.append("\n".join(current))
        return units

    if count_local_tokens(block.text) <= max_tokens:
        return [block.text.strip()] if block.text.strip() else []
    units = []
    for sentence in _split_sentences(block.text):
        units.extend(
            [sentence]
            if count_local_tokens(sentence) <= max_tokens
            else chunk_text_by_tokens(sentence, max_tokens=max_tokens, overlap_tokens=0)
        )
    return units


def _trim_heading_context(headings: list[str], max_tokens: int) -> str:
    text = "\n".join(headings).strip()
    if count_local_tokens(text) <= max_tokens:
        return text
    tokens = _local_tokens(text)
    return " ".join(tokens[-max_tokens:]) if tokens else ""


def _previous_sentence(text: str, max_tokens: int) -> str:
    sentences = _split_sentences(text)
    if not sentences:
        return ""
    tokens = _local_tokens(sentences[-1])
    return " ".join(tokens[-max_tokens:])


def chunk_blocks(
    blocks: list[ExtractedBlock],
    target_tokens: int = 320,
    max_tokens: int = 450,
    overlap_tokens: int = 60,
) -> list[str]:
    if target_tokens <= 0 or target_tokens > max_tokens:
        raise ValueError("target_tokens must be between 1 and max_tokens")
    if overlap_tokens < 0 or overlap_tokens >= max_tokens:
        raise ValueError("overlap_tokens must be between zero and max_tokens - 1")

    chunks: list[ChunkData] = []
    headings: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if not current:
            return
        heading = _trim_heading_context(headings, max_tokens)
        content = "\n\n".join(current)
        available = max_tokens - count_local_tokens(heading)
        body = " ".join(_local_tokens(content)[-available:]) if available <= 0 else content
        chunks.append(
            ChunkData(
                content="\n\n".join(part for part in (heading, body) if part),
                heading_path=list(headings),
            )
        )
        current.clear()

    for block in blocks:
        if not block.text.strip():
            continue
        if block.kind == "heading":
            flush()
            level = block.heading_level or 1
            headings[:] = [*headings[: level - 1], block.text.strip()]
            continue

        for unit in _split_block_units(block, max_tokens):
            heading_tokens = count_local_tokens("\n".join(headings))
            current_tokens = count_local_tokens("\n\n".join(current))
            unit_tokens = count_local_tokens(unit)
            if current and current_tokens + unit_tokens + heading_tokens > target_tokens:
                previous = _previous_sentence("\n\n".join(current), overlap_tokens)
                flush()
                if previous and block.kind != "table":
                    current.append(previous)
            current.append(unit)
            if count_local_tokens("\n\n".join(current)) + heading_tokens >= max_tokens:
                flush()

    flush()
    return chunks
