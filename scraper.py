from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class Product:

    url: str
    title: Optional[str] = None
    image: Optional[str] = None
    rating: Optional[str] = None
    rating_count: Optional[str] = None
    price: Optional[str] = None
    reviews: list[str] = field(default_factory=list)

    @property
    def review_count(self) -> int:
        return len(self.reviews)


class ScraperError(Exception):


def is_valid_amazon_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    if "amazon." not in (parsed.netloc or "").lower():
        return False
    return True


def _fetch_html(url: str) -> str:

    logger.info("Fetching URL via requests: %s", url)
    response = requests.get(
        url,
        headers=settings.default_headers,
        timeout=settings.request_timeout,
    )
    response.raise_for_status()
    return response.text


def _fetch_html_playwright(url: str) -> Optional[str]:

    if not settings.use_playwright_fallback:
        return None
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("Playwright not installed; skipping JS fallback.")
        return None

    logger.info("Falling back to Playwright for: %s", url)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=settings.user_agent)
            page = context.new_page()
            page.goto(url, timeout=settings.request_timeout * 1000)
            page.wait_for_load_state("domcontentloaded")
            html = page.content()
            browser.close()
            return html
    except Exception as exc:
        logger.warning("Playwright fallback failed: %s", exc)
        return None

def _clean(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    return re.sub(r"\s+", " ", text).strip() or None


def _parse_title(soup: BeautifulSoup) -> Optional[str]:
    for selector in ("#productTitle", "#title", "span#productTitle"):
        node = soup.select_one(selector)
        if node:
            return _clean(node.get_text())
    return None


def _parse_image(soup: BeautifulSoup) -> Optional[str]:
    node = soup.select_one("#landingImage") or soup.select_one("#imgBlkFront")
    if node and node.get("src"):
        return node["src"]

    node = soup.select_one("#imgTagWrapperId img")
    if node and node.get("src"):
        return node["src"]
    return None


def _parse_rating(soup: BeautifulSoup) -> Optional[str]:
    node = soup.select_one("span[data-hook='rating-out-of-text']")
    if node:
        return _clean(node.get_text())
    node = soup.select_one("i.a-icon-star span.a-icon-alt")
    if node:
        return _clean(node.get_text())
    return None


def _parse_rating_count(soup: BeautifulSoup) -> Optional[str]:
    node = soup.select_one("#acrCustomerReviewText")
    if node:
        return _clean(node.get_text())
    return None


def _parse_price(soup: BeautifulSoup) -> Optional[str]:
    selectors = [
        "span.a-price span.a-offscreen",
        "#priceblock_ourprice",
        "#priceblock_dealprice",
        "#priceblock_saleprice",
        "span#price",
    ]
    for sel in selectors:
        node = soup.select_one(sel)
        if node:
            text = _clean(node.get_text())
            if text:
                return text
    return None


def _parse_reviews(soup: BeautifulSoup) -> list[str]:

    reviews: list[str] = []
    selectors = [
        "div[data-hook='reviewRichContentContainer'] p span",
        "div[data-hook='reviewRichContentContainer'] span",
        "span[data-hook='review-body'] span",
        "div[data-hook='review-collapsed'] span",
        "span.review-text-content span",
    ]
    for sel in selectors:
        for node in soup.select(sel):
            txt = _clean(node.get_text())
            if txt:
                reviews.append(txt)
        if reviews:
            break
    return reviews


def scrape_product(url: str) -> Product:

    if not is_valid_amazon_url(url):
        raise ScraperError("Invalid Amazon URL. Expected a link on amazon.*.")

    html: Optional[str] = None
    try:
        html = _fetch_html(url)
    except requests.RequestException as exc:
        logger.warning("Static fetch failed: %s", exc)

    product = _parse_from_html(url, html) if html else Product(url=url)

    if _needs_fallback(product):
        js_html = _fetch_html_playwright(url)
        if js_html:
            product = _parse_from_html(url, js_html)

    if not product.title and not product.reviews:
        raise ScraperError(
            "Could not extract product data. Amazon may be blocking the "
            "request or the page layout is unsupported."
        )

    logger.info(
        "Scraped %s | reviews=%d | title=%s",
        url,
        product.review_count,
        (product.title or "N/A")[:60],
    )
    return product


def _parse_from_html(url: str, html: str) -> Product:
    soup = BeautifulSoup(html, "html.parser")
    return Product(
        url=url,
        title=_parse_title(soup),
        image=_parse_image(soup),
        rating=_parse_rating(soup),
        rating_count=_parse_rating_count(soup),
        price=_parse_price(soup),
        reviews=_parse_reviews(soup),
    )


def _needs_fallback(product: Product) -> bool:

    if product.title is None:
        return True
    if product.review_count < 3:
        return True
    return False
