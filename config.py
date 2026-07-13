from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def configure_logging(level: int = logging.INFO) -> None:

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


@dataclass(frozen=True)
class Settings:

    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    groq_temperature: float = float(os.getenv("GROQ_TEMPERATURE", "0.2"))
    groq_max_tokens: int = int(os.getenv("GROQ_MAX_TOKENS", "1500"))

    min_reviews: int = int(os.getenv("MIN_REVIEWS", "20"))
    request_timeout: int = int(os.getenv("REQUEST_TIMEOUT", "20"))
    use_playwright_fallback: bool = (
        os.getenv("USE_PLAYWRIGHT_FALLBACK", "true").lower() == "true"
    )

    user_agent: str = os.getenv(
        "USER_AGENT",
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
    )

    @property
    def default_headers(self) -> dict[str, str]:

        return {
            "User-Agent": self.user_agent,
            "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }


settings = Settings()
