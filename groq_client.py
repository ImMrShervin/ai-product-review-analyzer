from __future__ import annotations

import json
import logging
import re
from typing import Any

from groq import Groq

from config import settings

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are an expert product review analyst.

Analyze the provided customer reviews.

Return ONLY valid JSON.

Required format:

{
  "overall_sentiment":"",
  "pros":[],
  "cons":[],
  "common_issues":[],
  "summary":"",
  "recommendation":""
}

Rules:

- Do not invent information.
- Use only evidence found in the reviews.
- Merge similar opinions together.
- Keep the summary concise.
- Recommendation must be short.
- Return only JSON."""


_REQUIRED_KEYS = {
    "overall_sentiment",
    "pros",
    "cons",
    "common_issues",
    "summary",
    "recommendation",
}


class GroqClientError(Exception):


def _build_client() -> Groq:
    if not settings.groq_api_key:
        raise GroqClientError(
            "GROQ_API_KEY is missing. Add it to your .env file."
        )
    return Groq(api_key=settings.groq_api_key)


def _extract_json(raw: str) -> dict[str, Any]:

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.S)
    candidate = fenced.group(1) if fenced else None

    if candidate is None:

        match = re.search(r"\{.*\}", raw, flags=re.S)
        if not match:
            raise GroqClientError("Model did not return any JSON object.")
        candidate = match.group(0)

    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise GroqClientError(f"Model returned invalid JSON: {exc}") from exc


def _validate_shape(data: dict[str, Any]) -> dict[str, Any]:

    missing = _REQUIRED_KEYS - data.keys()
    if missing:
        raise GroqClientError(f"Missing keys in AI response: {sorted(missing)}")

    for list_key in ("pros", "cons", "common_issues"):
        if not isinstance(data[list_key], list):
            data[list_key] = [str(data[list_key])]
        data[list_key] = [str(x).strip() for x in data[list_key] if str(x).strip()]

    for str_key in ("overall_sentiment", "summary", "recommendation"):
        data[str_key] = str(data[str_key]).strip()

    return data


def analyze_reviews(reviews_text: str) -> dict[str, Any]:

    if not reviews_text.strip():
        raise GroqClientError("No reviews provided to analyze.")

    client = _build_client()

    user_prompt = (
        "Analyze the following customer reviews and return the JSON "
        "described in the system prompt.\n\n"
        "REVIEWS:\n"
        f"{reviews_text}"
    )

    logger.info(
        "Calling Groq model=%s temp=%.2f chars=%d",
        settings.groq_model,
        settings.groq_temperature,
        len(reviews_text),
    )

    try:
        completion = client.chat.completions.create(
            model=settings.groq_model,
            temperature=settings.groq_temperature,
            max_tokens=settings.groq_max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
    except Exception as exc:
        raise GroqClientError(f"Groq API request failed: {exc}") from exc

    try:
        raw = completion.choices[0].message.content or ""
    except (AttributeError, IndexError) as exc:
        raise GroqClientError("Unexpected Groq response structure.") from exc

    data = _extract_json(raw)
    return _validate_shape(data)
