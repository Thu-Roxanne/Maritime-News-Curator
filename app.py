import streamlit as st
import feedparser
import yaml
import hashlib
import urllib.parse
from datetime import datetime, timezone
from bs4 import BeautifulSoup
import math
from dateutil import parser as dparser

st.set_page_config(page_title="Maritime Latest News", layout="wide")

# ---------- Helpers ----------
def load_yaml_safe(path: str, name: str):
    """Load YAML and show a friendly error if malformed."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        st.error(f"❌ YAML error in {name}: {e}")
        st.stop()
    except FileNotFoundError:
        st.error(f"❌ File not found: {name}")
        st.stop()

def clean(text):
    """Robust text cleaner: only parse as HTML if it looks like HTML."""
    s = str(text or "")
    if "<" in s and ">" in s:
        return BeautifulSoup(s, "html.parser").get_text().strip()
    return s.strip()

def article_id(title, link):
    return hashlib.sha1(f"{title}{link}".encode()).hexdigest()

def parse_date_safe(s: str) -> datetime:
    """Parse date safely; return timezone-aware UTC now if missing/invalid."""
    if not s:
        return datetime.now(timezone.utc)
    try:
        dt = dparser.parse(s, fuzzy=True)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)

# 🔍 Improved image extraction (kept simple & robust)
def extract_image(entry):
    # 1) media_content
    media = entry.get("media_content", [])
    if isinstance(media, list) and media and media[0].get("url"):
        return media[0]["url"]
    # 2) media_thumbnail
    thumbs = entry.get("media_thumbnail", [])
    if isinstance(thumbs, list) and thumbs and thumbs[0].get("url"):
        return thumbs[0]["url"]
    # 3) summary HTML
    if entry.get("summary"):
        soup = BeautifulSoup(entry["summary"], "html.parser")
        img = soup.find("img")
        if img and img.get("src"):
            return img["src"]
    # 4) content HTML
    if entry.get("content"):
        html = entry["content"][0].get("value", "")
        soup = BeautifulSoup(html, "html.parser")
        img = soup.find("img")
        if img and img.get("src"):
            return img["src"]
    return ""

# ---------- Load topics and feeds ----------
topic_config = load_yaml_safe("topics.yaml", "topics.yaml")
feed_config = load_yaml_safe("feeds.yaml", "feeds.yaml")

all_topics = list(topic_config.get("topics", {}).keys())

# ---------- Core fetching ----------
def fetch_articles_for_topic(selected_topic, max_age_days: int = 30):
    all_articles = []
    feeds = feed_config.get("feeds", [])
    queries = feed_config.get("google_news_queries", [])

    # URL-encoded Google News queries + set language/region for consistency
    google_feeds = [
        f"https://news.google.com/rss/search?q={urllib.parse.quote_plus(q)}&hl=en-US&gl=US&ceid=US:en"
        for q in queries
    ]

    for url in feeds + google_feeds:
        # Make sure a malformed URL or network hiccup doesn't crash the app
        try:
            d = feedparser.parse(url)
        except Exception as e:
            st.warning(f"Skipping feed due to URL/error: {url} — {e}")
            continue

        # If feedparser itself couldn't open it, continue gracefully
        if getattr(d, "bozo", 0) and not getattr(d, "entries", []):
            # d.bozo_exception might contain details, but we avoid noisy logs in UI
            continue

        for entry in d.entries:
            title = clean(entry.get("title", ""))
            summary = clean(entry.get("summary", ""))
            link = entry.get("link", "").strip()
            pub_raw = entry.get("published") or entry.get("updated") or ""
            pub_dt = parse_date_safe(pub_raw)

            # Age filter (optional but useful)
            age_days = (datetime.now(timezone.utc) - pub_dt).total_seconds() / 86400.0
            if age_days > max_age_days:
                continue

            full_text = f"{title} {summary}"

            matched_topics = []
            for topic, data in topic_config.get("topics", {}).items():
                include_words = data.get("include", [])
                # Simple substring match (case-insensitive), as in your original
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
                    "topics": matched_topics,
                    "image": image or ""
                })

    return all_articles

# ---------- UI ----------
st.title("📰 Maritime Latest News")
selected = []

with st.sidebar:
    st.markdown("### Filters")
    max_age_days = st.slider("Max article age (days)", 1, 60, 30, help="Skip items older than this.")

# Topic tiles (clickable)
st.markdown("### 📂 Choose a topic")
topic_cols = st.columns(3)

for i, topic in enumerate(all_topics):
    with topic_cols[i % 3]:
        if st.button(topic, key=f"topic_btn_{topic}"):
            st.session_state["selected_topic"] = topic
            st.session_state["articles"] = fetch_articles_for_topic(topic, max_age_days=max_age_days)

# Article display
articles = st.session_state.get("articles", [])
selected_topic = st.session_state.get("selected_topic", None)

if articles:
    st.markdown(f"## 📌 {selected_topic} ({len(articles)} articles)")
    PAGE_SIZE = 20
    total_pages = max(1, math.ceil(len(articles) / PAGE_SIZE))
    page = st.number_input("Page", 1, total_pages, 1, key=f"page_{selected_topic}")
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    page_articles = articles[start:end]

    # Card
    def display_article_card(article, key_suffix):
        with st.container():
            if article.get("image"):
                st.image(article["image"], use_column_width=True)
            st.markdown(f"### {article['title']}")
            # date is isoformat — just show YYYY-MM-DD
            st.markdown(f"*📅 {article['date'][:10]}*")
            st.markdown(f"**Topics:** {', '.join(article['topics'])}")
            st.markdown(f"{article['summary'][:300]}...")
            st.markdown(f"[🔗 Read more]({article['link']})")
            if st.checkbox("⭐ Add to Top 10", key=f"sel_{article['id']}_{key_suffix}"):
                selected.append(article)

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
    markdown = f"# Maritime Top 10 – {selected_topic}\n\n"
    for i, a in enumerate(selected[:10], 1):
        markdown += f"## {i}. {a['title']}\n"
        markdown += f"*Date:* {a['date']}\n\n"
        markdown += f"*Topics:* {', '.join(a['topics'])}\n\n"
        markdown += f"{a['summary'][:300]}...\n\n"
        markdown += f"[Read more]({a['link']})\n\n"
    st.download_button("📥 Download Markdown", markdown, file_name=f"top10-{selected_topic}.md", mime="text/markdown")
