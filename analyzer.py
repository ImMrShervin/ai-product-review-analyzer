from __future__ import annotations

import logging
import re
from typing import Iterable

logger = logging.getLogger(__name__)

_MIN_REVIEW_LENGTH = 15

_MAX_COMBINED_CHARS = 18_000


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def clean_reviews(reviews: Iterable[str]) -> list[str]:

    seen: set[str] = set()
    cleaned: list[str] = []

    for raw in reviews:
        if not raw:
            continue
        text = _normalize_whitespace(raw)
        if len(text) < _MIN_REVIEW_LENGTH:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)

    logger.info("Cleaned reviews: %d -> %d", len(list(reviews)) if isinstance(reviews, list) else -1, len(cleaned))
    return cleaned


def build_reviews_prompt(reviews: list[str]) -> str:

    if not reviews:
        return ""

    lines: list[str] = []
    total = 0
    for i, review in enumerate(reviews, start=1):
        line = f"{i}. {review}"
        if total + len(line) > _MAX_COMBINED_CHARS:
            logger.warning(
                "Truncating reviews at #%d to stay within %d chars.",
                i,
                _MAX_COMBINED_CHARS,
            )
            break
        lines.append(line)
        total += len(line)

    return "\n".join(lines)
