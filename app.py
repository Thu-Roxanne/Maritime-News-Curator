import streamlit as st
import feedparser
import yaml
import hashlib
import urllib.parse
from urllib.parse import urlparse
from datetime import datetime, timezone, date
from bs4 import BeautifulSoup
import math
from dateutil import parser as dparser

st.set_page_config(page_title="Maritime Latest News", layout="wide")

# =========================
# CSS – modern card layout
# =========================
CARD_CSS = """
<style>
/* Global tweaks */
:root { --card-radius:14px; --card-shadow:0 4px 20px rgba(0,0,0,.06); }
.block-container { padding-top: 1.5rem; }

/* Topic buttons */
.stButton>button {
  border-radius: 999px !important;
  padding: .4rem .9rem;
  border: 1px solid rgba(0,0,0,.08);
}

/* Article cards */
.news-card {
  background: #fff;
  border-radius: var(--card-radius);
  box-shadow: var(--card-shadow);
  padding: 16px 16px 12px 16px;
  transition: transform .05s ease-in-out;
  border: 1px solid rgba(0,0,0,.05);
  min-height: 100%;
}
.news-card:hover { transform: translateY(-1px); }
.news-title {
  font-size: 1.15rem;
  font-weight: 700;
  line-height: 1.25;
  margin: 6px 0 6px 0;
}
.news-meta {
  color: #6b7280;
  font-size: 0.9rem;
  margin-bottom: 6px;
}
.news-summary {
  color: #374151;
  font-size: .95rem;
}
.news-thumb img {
  border-radius: 10px;
}
.news-actions {
  display: flex; align-items: center; gap: 10px; margin-top: 8px;
}
.badge {
  display:inline-block;
  padding: 2px 8px;
  background: #f1f5f9;
  border-radius: 999px;
  font-size: .8rem;
  color: #0f172a;
  border: 1px solid #e2e8f0;
}
hr.soft { border:0; border-top:1px solid rgba(0,0,0,.06); margin: 18px 0; }
</style>
"""
st.markdown(CARD_CSS, unsafe_allow_html=True)

# =========================
# YAML loaders (safe)
# =========================
def load_yaml_safe(path: str, name: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        st.error(f"❌ YAML error in {name}: {e}")
        st.stop()
    except FileNotFoundError:
        st.error(f"❌ File not found: {name}")
        st.stop()

topic_config = load_yaml_safe("topics.yaml", "topics.yaml")
feed_config  = load_yaml_safe("feeds.yaml", "feeds.yaml")
all_topics   = list(topic_config.get("topics", {}).keys())

# =========================
# Utilities
# =========================
def clean(text):
    s = str(text or "")
    if "<" in s and ">" in s:
        return BeautifulSoup(s, "html.parser").get_text().strip()
    return s.strip()

def article_id(title, link):
    return hashlib.sha1(f"{title}{link}".encode()).hexdigest()

def parse_date_safe(s: str) -> datetime:
    if not s:
        return datetime.now(timezone.utc)
    try:
        dt = dparser.parse(s, fuzzy=True)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)

def extract_image(entry):
    media = entry.get("media_content", [])
    if isinstance(media, list) and media and media[0].get("url"):
        return media[0]["url"]
    thumbs = entry.get("media_thumbnail", [])
    if isinstance(thumbs, list) and thumbs and thumbs[0].get("url"):
        return thumbs[0]["url"]
    if entry.get("summary"):
        soup = BeautifulSoup(entry["summary"], "html.parser")
        img = soup.find("img")
        if img and img.get("src"):
            return img["src"]
    if entry.get("content"):
        html = entry["content"][0].get("value", "")
        soup = BeautifulSoup(html, "html.parser")
        img = soup.find("img")
        if img and img.get("src"):
            return img["src"]
    return ""

def get_domain(u: str) -> str:
    try:
        return urlparse(u).netloc.lower().replace("www.", "")
    except Exception:
        return ""

# =========================
# Fetching Core
# =========================
def fetch_articles_for_topic(selected_topic, max_age_days: int = 30):
    all_articles = []
    feeds   = feed_config.get("feeds", [])
    queries = feed_config.get("google_news_queries", [])
    google_feeds = [
        f"https://news.google.com/rss/search?q={urllib.parse.quote_plus(q)}&hl=en-US&gl=US&ceid=US:en"
        for q in queries
    ]

    for url in feeds + google_feeds:
        try:
            d = feedparser.parse(url)
        except Exception as e:
            st.warning(f"Skipping feed due to URL/error: {url} — {e}")
            continue
        if getattr(d, "bozo", 0) and not getattr(d, "entries", []):
            continue

        for entry in d.entries:
            title   = clean(entry.get("title", ""))
            summary = clean(entry.get("summary", ""))
            link    = entry.get("link", "").strip()
            pub_dt  = parse_date_safe(entry.get("published") or entry.get("updated") or "")

            # Age filter up-front (server-side)
            age_days = (datetime.now(timezone.utc) - pub_dt).total_seconds() / 86400.0
            if age_days > max_age_days:
                continue

            full_text = f"{title} {summary}"
            matched_topics = []
            for topic, data in topic_config.get("topics", {}).items():
                include_words = data.get("include", [])
                if any(word.lower() in full_text.lower() for word in include_words):
                    matched_topics.append(topic)

            if selected_topic in matched_topics:
                image = extract_image(entry)
                all_articles.append({
                    "id": article_id(title, link),
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "date": pub_dt.isoformat(),
                    "date_dt": pub_dt,
                    "topics": matched_topics,
                    "image": image or "",
                    "domain": get_domain(link)
                })

    return all_articles

# =========================
# UI – Header & Sidebar
# =========================
st.title("📰 Maritime Latest News")

# Sidebar Filters
with st.sidebar:
    st.markdown("### Filter Options")
    st.caption("Adjust filters and click **Refresh News** after changing Topics on the main view.")

    # Date range
    today = date.today()
    default_from = today.replace(day=max(1, today.day-7))  # last ~week
    date_range = st.date_input(
        "Choose dates",
        value=(default_from, today),
        help="Articles are filtered by published/updated date."
    )
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date, end_date = default_from, today

    # Sources (domains)
    # We fill these after we load/refresh articles; placeholder now:
    st.session_state.setdefault("source_options", [])
    chosen_sources = st.multiselect(
        "Choose sources",
        options=st.session_state["source_options"],
        default=st.session_state["source_options"],
        help="Filter by article domain."
    )

    # Keyword search
    keyword = st.text_input("Keyword contains", value="", placeholder="e.g. ammonia, Red Sea, EEXI")

    # Sort
    sort_by = st.selectbox("Sort by", ["Newest first", "Oldest first", "Title A→Z"])

    # Age ceiling (server-side fetch limiter)
    max_age_days = st.slider("Max article age (days)", 1, 60, 30)

    refresh_clicked = st.button("🔄 Refresh News")

# =========================
# Topic selector (pills)
# =========================
st.markdown("### 📂 Choose a topic")
topic_cols = st.columns(3)
for i, topic in enumerate(all_topics):
    with topic_cols[i % 3]:
        if st.button(topic, key=f"topic_btn_{topic}"):
            st.session_state["selected_topic"] = topic
            st.session_state["articles"] = fetch_articles_for_topic(topic, max_age_days=max_age_days)

# Initial state
articles = st.session_state.get("articles", [])
selected_topic = st.session_state.get("selected_topic", None)

# When user presses Refresh after changing filters or age limit
if refresh_clicked and selected_topic:
    st.session_state["articles"] = fetch_articles_for_topic(selected_topic, max_age_days=max_age_days)
    articles = st.session_state["articles"]

# Build dynamic source list for the sidebar
if articles:
    domains = sorted({a.get("domain","") for a in articles if a.get("domain")})
    st.session_state["source_options"] = domains
    # If none selected yet (first load), select all
    if not st.session_state.get("sources_initialized"):
        st.session_state["sources_initialized"] = True
        chosen_sources = domains

# =========================
# Client-side filtering + sort
# =========================
def within_date_window(dt: datetime, start_d: date, end_d: date) -> bool:
    d = dt.date()
    return (d >= start_d) and (d <= end_d)

def passes_filters(a: dict) -> bool:
    ok_date = True
    if start_date and end_date:
        ok_date = within_date_window(a["date_dt"], start_date, end_date)
    ok_source = (not chosen_sources) or (a.get("domain","") in chosen_sources)
    ok_kw = True
    if keyword.strip():
        blob = f"{a['title']} {a['summary']}".lower()
        ok_kw = all(k.strip().lower() in blob for k in keyword.split())
    return ok_date and ok_source and ok_kw

def apply_sort(items: list[dict]) -> list[dict]:
    if sort_by == "Newest first":
        return sorted(items, key=lambda x: x["date_dt"], reverse=True)
    if sort_by == "Oldest first":
        return sorted(items, key=lambda x: x["date_dt"])
    if sort_by == "Title A→Z":
        return sorted(items, key=lambda x: x["title"].lower())
    return items

# =========================
# Render
# =========================
selected = []

if articles:
    filtered = [a for a in articles if passes_filters(a)]
    filtered = apply_sort(filtered)

    st.markdown(f"## 📌 {selected_topic} ({len(filtered)} articles)")

    # Pagination
    PAGE_SIZE = 18
    total_pages = max(1, math.ceil(len(filtered) / PAGE_SIZE))
    current_page_key = f"page_{selected_topic}"
    if current_page_key not in st.session_state:
        st.session_state[current_page_key] = 1

    # Header pager
    c1, c2, c3 = st.columns([1, 2, 1])
    with c1:
        if st.button("⬅️ Previous", disabled=st.session_state[current_page_key] <= 1):
            st.session_state[current_page_key] -= 1
    with c2:
        st.session_state[current_page_key] = st.selectbox(
            "Page",
            options=list(range(1, total_pages + 1)),
            index=min(st.session_state[current_page_key]-1, total_pages-1),
            label_visibility="collapsed",
        )
    with c3:
        if st.button("Next ➡️", disabled=st.session_state[current_page_key] >= total_pages):
            st.session_state[current_page_key] += 1

    # Slice
    page = st.session_state[current_page_key]
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    page_articles = filtered[start:end]

    # Card renderer
    def display_article_card(article, key_suffix):
        with st.container():
            st.markdown('<div class="news-card">', unsafe_allow_html=True)
            # Thumb
            if article.get("image"):
                st.markdown('<div class="news-thumb">', unsafe_allow_html=True)
                st.image(article["image"], use_column_width=True)
                st.markdown("</div>", unsafe_allow_html=True)

            # Title
            st.markdown(f'<div class="news-title">{article["title"]}</div>', unsafe_allow_html=True)

            # Meta
            date_str = article['date'][:10]
            domain = article.get("domain", "")
            topics_str = ", ".join(article["topics"])
            st.markdown(
                f'<div class="news-meta">📅 {date_str} &nbsp;&nbsp;•&nbsp;&nbsp; 🔖 {domain}</div>',
                unsafe_allow_html=True
            )

            # Topics chips
            chips = " ".join([f'<span class="badge">{t}</span>' for t in article["topics"][:3]])
            if chips:
                st.markdown(chips, unsafe_allow_html=True)
                st.markdown('<hr class="soft">', unsafe_allow_html=True)

            # Summary
            st.markdown(f'<div class="news-summary">{article["summary"][:320]}...</div>', unsafe_allow_html=True)

            # Actions
            link = article["link"]
            st.markdown('<div class="news-actions">', unsafe_allow_html=True)
            st.markdown(f"[🔗 Read more]({link})")
            if st.checkbox("⭐ Add to Top 10", key=f"sel_{article['id']}_{key_suffix}"):
                selected.append(article)
            st.markdown("</div></div>", unsafe_allow_html=True)

    # Grid – 3 columns per row
    for i in range(0, len(page_articles), 3):
        cols = st.columns(3)
        for j in range(3):
            if i + j < len(page_articles):
                with cols[j]:
                    display_article_card(page_articles[i + j], key_suffix=f"{selected_topic}_{i}_{j}")

    st.divider()

# Markdown Export
if selected:
    st.subheader("📦 Export Top 10 as Markdown")
    markdown = f"# Maritime Top 10 – {st.session_state.get('selected_topic','')}\n\n"
    for i, a in enumerate(selected[:10], 1):
        markdown += f"## {i}. {a['title']}\n"
        markdown += f"*Date:* {a['date']}\n\n"
        markdown += f"*Topics:* {', '.join(a['topics'])}\n\n"
        markdown += f"{a['summary'][:300]}...\n\n"
        markdown += f"[Read more]({a['link']})\n\n"
    st.download_button("📥 Download Markdown", markdown, file_name=f"top10-{st.session_state.get('selected_topic','')}.md", mime="text/markdown")
