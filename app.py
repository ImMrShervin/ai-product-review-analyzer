from __future__ import annotations

import logging
from typing import Any

import streamlit as st

from analyzer import build_reviews_prompt, clean_reviews
from config import configure_logging, settings
from groq_client import GroqClientError, analyze_reviews
from scraper import Product, ScraperError, is_valid_amazon_url, scrape_product

configure_logging()
logger = logging.getLogger("app")


st.set_page_config(
    page_title="AI Product Review Analyzer",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        .main-title {
            font-size: 2.4rem;
            font-weight: 700;
            background: linear-gradient(90deg, #6366f1, #ec4899);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.2rem;
        }
        .subtitle {
            color: #6b7280;
            font-size: 1rem;
            margin-bottom: 1.6rem;
        }
        .metric-card {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 12px;
            padding: 1rem 1.2rem;
            box-shadow: 0 1px 2px rgba(0,0,0,0.04);
        }
        .pill {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 999px;
            font-weight: 600;
            font-size: 0.85rem;
        }
        .pill-positive { background:#dcfce7; color:#15803d; }
        .pill-negative { background:#fee2e2; color:#b91c1c; }
        .pill-neutral  { background:#e0e7ff; color:#3730a3; }
        .list-item { padding: 4px 0; }
    </style>
    """,
    unsafe_allow_html=True,
)


with st.sidebar:
    st.header("⚙️ Settings")
    st.markdown(
        f"**Model:** `{settings.groq_model}`  \n"
        f"**Min reviews:** `{settings.min_reviews}`  \n"
        f"**Playwright fallback:** "
        f"`{'on' if settings.use_playwright_fallback else 'off'}`"
    )
    if not settings.groq_api_key:
        st.error("`GROQ_API_KEY` not set. Add it to `.env`.")
    st.divider()
    st.caption(
        "Paste an Amazon product URL to extract reviews and get an "
        "AI-powered summary."
    )


st.markdown(
    '<div class="main-title">🛍️ AI Product Review Analyzer</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="subtitle">Extract Amazon reviews and get pros, cons, and '
    "a buying recommendation — powered by Groq.</div>",
    unsafe_allow_html=True,
)


with st.form("url_form", clear_on_submit=False):
    url = st.text_input(
        "Amazon Product URL",
        placeholder="https://www.amazon.com/dp/XXXXXXXXXX",
    )
    submitted = st.form_submit_button("🔍 Analyze reviews", type="primary")


def _sentiment_pill(sentiment: str) -> str:
    s = sentiment.lower()
    if any(w in s for w in ("positive", "excellent", "good")):
        emoji, cls = "😊", "pill-positive"
    elif any(w in s for w in ("negative", "poor", "bad")):
        emoji, cls = "😞", "pill-negative"
    else:
        emoji, cls = "😐", "pill-neutral"
    return f'<span class="pill {cls}">{sentiment} {emoji}</span>'


def _render_product_header(product: Product) -> None:
    col_img, col_info = st.columns([1, 2])
    with col_img:
        if product.image:
            st.image(product.image, use_container_width=True)
        else:
            st.info("No product image available.")

    with col_info:
        st.subheader(product.title or "Unknown product")
        m1, m2, m3 = st.columns(3)
        m1.metric("⭐ Rating", product.rating or "N/A")
        m2.metric("🗣️ Ratings", product.rating_count or "N/A")
        m3.metric("💵 Price", product.price or "N/A")
        st.caption(f"Reviews collected: **{product.review_count}**")
        st.markdown(f"[Open on Amazon]({product.url})")


def _render_analysis(analysis: dict[str, Any]) -> None:
    st.markdown("### 📊 Overall Sentiment")
    st.markdown(
        _sentiment_pill(analysis.get("overall_sentiment", "Neutral")),
        unsafe_allow_html=True,
    )

    col_pros, col_cons = st.columns(2)
    with col_pros:
        st.markdown("### ✅ Pros")
        pros = analysis.get("pros") or []
        if pros:
            for p in pros:
                st.markdown(f"<div class='list-item'>✔ {p}</div>", unsafe_allow_html=True)
        else:
            st.caption("No pros extracted.")

    with col_cons:
        st.markdown("### ❌ Cons")
        cons = analysis.get("cons") or []
        if cons:
            for c in cons:
                st.markdown(f"<div class='list-item'>✘ {c}</div>", unsafe_allow_html=True)
        else:
            st.caption("No cons extracted.")

    st.markdown("### ⚠️ Common Issues")
    issues = analysis.get("common_issues") or []
    if issues:
        for issue in issues:
            st.markdown(f"- {issue}")
    else:
        st.caption("No recurring issues detected.")

    st.markdown("### 🧠 AI Summary")
    st.info(analysis.get("summary") or "No summary produced.")

    st.markdown("### 🛒 Buying Recommendation")
    st.success(analysis.get("recommendation") or "No recommendation produced.")


def _run_pipeline(product_url: str) -> None:
    if not is_valid_amazon_url(product_url):
        st.error("❌ Please enter a valid Amazon product URL.")
        return

    if not settings.groq_api_key:
        st.error("❌ `GROQ_API_KEY` is missing. Add it to your `.env` file.")
        return

    with st.status("🔎 Scraping product page...", expanded=False) as status:
        try:
            product = scrape_product(product_url)
        except ScraperError as exc:
            status.update(label="Scraping failed", state="error")
            st.error(f"❌ {exc}")
            return
        except Exception as exc:
            status.update(label="Unexpected error", state="error")
            logger.exception("Unhandled scraping error")
            st.error(f"❌ Unexpected scraping error: {exc}")
            return
        status.update(label="✅ Product scraped", state="complete")

    _render_product_header(product)
    st.divider()

    cleaned = clean_reviews(product.reviews)
    if not cleaned:
        st.warning(
            "⚠️ No usable reviews were found on this page. Amazon may have "
            "blocked the request or the product has no written reviews."
        )
        return
    if len(cleaned) < 5:
        st.warning(
            f"⚠️ Only {len(cleaned)} reviews were extracted — the AI summary "
            "may be less reliable."
        )

    #Analyze
    with st.status("🤖 Analyzing reviews with Groq...", expanded=False) as status:
        try:
            reviews_text = build_reviews_prompt(cleaned)
            analysis = analyze_reviews(reviews_text)
        except GroqClientError as exc:
            status.update(label="AI analysis failed", state="error")
            st.error(f"❌ {exc}")
            return
        except Exception as exc:
            status.update(label="Unexpected AI error", state="error")
            logger.exception("Unhandled Groq error")
            st.error(f"❌ Unexpected AI error: {exc}")
            return
        status.update(label="✅ Analysis complete", state="complete")

    _render_analysis(analysis)

    with st.expander("📝 View raw reviews"):
        for i, review in enumerate(cleaned, start=1):
            st.markdown(f"**{i}.** {review}")


if submitted and url:
    _run_pipeline(url.strip())
elif submitted:
    st.warning("Please paste an Amazon product URL first.")
