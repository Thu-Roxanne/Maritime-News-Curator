import streamlit as st
import feedparser
import yaml
import hashlib
import urllib.parse
from datetime import datetime, timezone, date
from bs4 import BeautifulSoup
import math
from dateutil import parser as dparser
from urllib.parse import urlparse

st.set_page_config(page_title="Maritime Latest News", layout="wide")

# ---------------- CSS (cards + small polish) ----------------
st.markdown("""
<style>
:root { --card-radius:14px; --card-shadow:0 4px 20px rgba(0,0,0,.06); }
.block-container { padding-top: 1.5rem; }
.stButton>button { border-radius: 999px !important; padding: .4rem .9rem; border: 1px solid rgba(0,0,0,.08); }

/* Cards */
.news-card { background:#fff; border-radius:var(--card-radius); box-shadow:var(--card-shadow);
  padding:16px 16px 12px 16px; border:1px solid rgba(0,0,0,.06); min-height:100%; }
.news-card:hover { transform: translateY(-1px); }
.news-title { font-size:1.15rem; font-weight:700; line-height:1.25; margin:6px 0 6px 0; }
.news-meta { color:#6b7280; font-size:0.9rem; margin-bottom:6px; }
.news-summary { color:#374151; font-size:.95rem; }
.news-thumb img { border-radius:10px; }
.badge { display:inline-block; padding:2px 8px; background:#f1f5f9; border-radius:999px;
  font-size:.8rem; color:#0f172a; border:1px solid #e2e8f0; }
hr.soft { border:0; border-top:1px solid rgba(0,0,0,.06); margin:18px 0; }
</style>
""", unsafe_allow_html=True)

# ---------------- YAML loaders ----------------
def load_yaml_safe(path: str, name: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        st.error(f"❌ YAML error in {name}: {e}"); st.stop()
    except FileNotFoundError:
        st.error(f"❌ File not found: {name}"); st.stop()

topic_config = load_yaml_safe("topics.yaml", "topics.yaml")
feed_config  = load_yaml_safe("feeds.yaml", "feeds.yaml")
ALL_TOPICS   = list(topic_config.get("topics", {}).keys())

# ---------------- Utilities ----------------
def clean(text):
    s = str(text or "")
    if "<" in s and ">" in s:
        return BeautifulSoup(s, "html.parser").get_text().strip()
    return s.strip()

def article_id(title, link):
    return hashlib.sha1(f"{title}{link}".encode()).hexdigest()

def parse_date_safe(s: str) -> datetime:
    if not s: return datetime.now(timezone.utc)
    try:
        dt = dparser.parse(s, fuzzy=True)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)

def extract_image(entry):
    media = entry.get("media_content", [])
    if isinstance(media, list) and media and media[0].get("url"): return media[0]["url"]
    thumbs = entry.get("media_thumbnail", [])
    if isinstance(thumbs, list) and thumbs and thumbs[0].get("url"): return thumbs[0]["url"]
    if entry.get("summary"):
        img = BeautifulSoup(entry["summary"], "html.parser").find("img")
        if img and img.get("src"): return img["src"]
    if entry.get("content"):
        html = entry["content"][0].get("value", "")
        img = BeautifulSoup(html, "html.parser").find("img")
        if img and img.get("src"): return img["src"]
    return ""

def get_domain(u: str) -> str:
    try:
        return urlparse(u).netloc.lower().replace("www.", "")
    except Exception:
        return ""

# ---------------- Fetch once, classify all ----------------
@st.cache_data(show_spinner=True, ttl=600)
def fetch_all_articles(max_age_days: int = 30):
    feeds   = feed_config.get("feeds", [])
    queries = feed_config.get("google_news_queries", [])
    google_feeds = [
        f"https://news.google.com/rss/search?q={urllib.parse.quote_plus(q)}&hl=en-US&gl=US&ceid=US:en"
        for q in queries
    ]
    urls = feeds + google_feeds

    items = []
    for url in urls:
        try:
            d = feedparser.parse(url)
        except Exception:
            continue
        if getattr(d, "bozo", 0) and not getattr(d, "entries", []):
            continue

        for entry in d.entries:
            title   = clean(entry.get("title", ""))
            summary = clean(entry.get("summary", ""))
            link    = (entry.get("link") or "").strip()
            pub_dt  = parse_date_safe(entry.get("published") or entry.get("updated") or "")
            # server-side age filter
            age_days = (datetime.now(timezone.utc) - pub_dt).total_seconds() / 86400.0
            if age_days > max_age_days:
                continue

            full_text = f"{title} {summary}"
            matched_topics = []
            for topic, data in topic_config.get("topics", {}).items():
                include_words = data.get("include", [])
                if any(w.lower() in full_text.lower() for w in include_words):
                    matched_topics.append(topic)

            if not matched_topics:
                continue  # only keep items that match at least one topic

            items.append({
                "id": article_id(title, link),
                "title": title,
                "summary": summary,
                "link": link,
                "date": pub_dt.isoformat(),
                "date_dt": pub_dt,
                "topics": matched_topics,
                "image": extract_image(entry) or "",
                "domain": get_domain(link),
            })
    return items

# ---------------- Sidebar filters ----------------
st.title("📰 Maritime Latest News")

with st.sidebar:
    st.markdown("### Filter Options")
    today = date.today()
    default_from = today.replace(day=max(1, today.day-7))
    date_range = st.date_input("Choose dates", value=(default_from, today))
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date, end_date = default_from, today

    choose_topics = st.multiselect(
        "Choose topics",
        options=ALL_TOPICS,
        default=ALL_TOPICS  # show everything initially
    )

    sort_by = st.selectbox("Sort by", ["Newest first", "Oldest first", "Title A→Z"])
    max_age_days = st.slider("Max article age (days)", 1, 60, 30)
    refresh_clicked = st.button("🔄 Refresh News")

# Fetch data (cached)
if refresh_clicked or "all_articles" not in st.session_state:
    st.session_state["all_articles"] = fetch_all_articles(max_age_days=max_age_days)
articles = st.session_state["all_articles"]

# ---------------- Filter + sort client-side ----------------
def date_in_window(dt: datetime, start_d: date, end_d: date) -> bool:
    d = dt.date()
    return (d >= start_d) and (d <= end_d)

def passes_filters(a: dict) -> bool:
    if choose_topics:
        if not any(t in choose_topics for t in a["topics"]):
            return False
    if start_date and end_date:
        if not date_in_window(a["date_dt"], start_date, end_date):
            return False
    return True

def apply_sort(items: list[dict]) -> list[dict]:
    if sort_by == "Newest first":
        return sorted(items, key=lambda x: x["date_dt"], reverse=True)
    if sort_by == "Oldest first":
        return sorted(items, key=lambda x: x["date_dt"])
    return sorted(items, key=lambda x: x["title"].lower())

filtered = apply_sort([a for a in articles if passes_filters(a)])

# ---------------- Render ----------------
st.markdown(f"## 📌 Results ({len(filtered)} articles)")

# Pagination controls
PAGE_SIZE = 18
total_pages = max(1, math.ceil(len(filtered) / PAGE_SIZE))
if "page" not in st.session_state:
    st.session_state["page"] = 1
# pager row
c1, c2, c3 = st.columns([1, 2, 1])
with c1:
    if st.button("⬅️ Previous", disabled=st.session_state["page"] <= 1):
        st.session_state["page"] -= 1
with c2:
    st.session_state["page"] = st.selectbox(
        "Page", options=list(range(1, total_pages + 1)),
        index=min(st.session_state["page"] - 1, total_pages - 1),
        label_visibility="collapsed"
    )
with c3:
    if st.button("Next ➡️", disabled=st.session_state["page"] >= total_pages):
        st.session_state["page"] += 1

start = (st.session_state["page"] - 1) * PAGE_SIZE
end = start + PAGE_SIZE
page_articles = filtered[start:end]

selected = []

def display_card(article, key_suffix):
    st.markdown('<div class="news-card">', unsafe_allow_html=True)
    if article.get("image"):
        st.image(article["image"], use_column_width=True)
    st.markdown(f'<div class="news-title">{article["title"]}</div>', unsafe_allow_html=True)
    date_str = article["date"][:10]
    dom = article.get("domain", "")
    st.markdown(f'<div class="news-meta">📅 {date_str} &nbsp;&nbsp;•&nbsp;&nbsp; 🔖 {dom}</div>', unsafe_allow_html=True)
    chips = " ".join([f'<span class="badge">{t}</span>' for t in article["topics"][:3]])
    if chips:
        st.markdown(chips, unsafe_allow_html=True)
        st.markdown('<hr class="soft">', unsafe_allow_html=True)
    st.markdown(f'<div class="news-summary">{article["summary"][:320]}...</div>', unsafe_allow_html=True)
    st.markdown(f"[🔗 Read more]({article['link']})")
    if st.checkbox("⭐ Add to Top 10", key=f"sel_{article['id']}_{key_suffix}"):
        selected.append(article)
    st.markdown("</div>", unsafe_allow_html=True)

for i in range(0, len(page_articles), 3):
    cols = st.columns(3)
    for j in range(3):
        if i + j < len(page_articles):
            with cols[j]:
                display_card(page_articles[i + j], key_suffix=f"{i}_{j}")

st.divider()

# Export Top 10
if selected:
    st.subheader("📦 Export Top 10 as Markdown")
    md = "# Maritime Top 10\n\n"
    for idx, a in enumerate(selected[:10], 1):
        md += f"## {idx}. {a['title']}\n"
        md += f"*Date:* {a['date']}\n\n"
        md += f"*Topics:* {', '.join(a['topics'])}\n\n"
        md += f"{a['summary'][:300]}...\n\n"
        md += f"[Read more]({a['link']})\n\n"
    st.download_button("📥 Download Markdown", md, file_name="top10.md", mime="text/markdown")
