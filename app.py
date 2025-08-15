import streamlit as st
import feedparser
import yaml
import hashlib
import json
from datetime import datetime
from bs4 import BeautifulSoup
from collections import defaultdict
import math

st.set_page_config(page_title="Maritime News", layout="wide")

# Load topic keywords
with open("topics.yaml", "r") as f:
    topic_config = yaml.safe_load(f)

# Load feeds
with open("feeds.yaml", "r") as f:
    feed_config = yaml.safe_load(f)

# Clean HTML content
def clean(text):
    return BeautifulSoup(text or "", "html.parser").get_text().strip()

# Generate unique ID from title + link
def article_id(title, link):
    return hashlib.sha1(f"{title}{link}".encode()).hexdigest()

# Fetch articles from RSS
def fetch_articles():
    articles = []
    feeds = feed_config["feeds"]
    queries = feed_config["google_news_queries"]
    google_feeds = [f"https://news.google.com/rss/search?q={q}" for q in queries]

    for url in feeds + google_feeds:
        d = feedparser.parse(url)
        for entry in d.entries:
            title = clean(entry.get("title", ""))
            summary = clean(entry.get("summary", ""))
            link = entry.get("link", "")
            pub_date = entry.get("published", datetime.utcnow().isoformat())
            full_text = f"{title} {summary}"

            # Detect topic(s)
            matched_topics = []
            for topic, data in topic_config["topics"].items():
                if any(word.lower() in full_text.lower() for word in data.get("include", [])):
                    matched_topics.append(topic)

            # Optional: try media content
            image = ""
            media = entry.get("media_content", [])
            if media and isinstance(media, list):
                image = media[0].get("url", "")

            articles.append({
                "id": article_id(title, link),
                "title": title,
                "summary": summary,
                "link": link,
                "date": pub_date,
                "topics": matched_topics or ["📂 Uncategorized"],
                "image": image or ""
            })
    return articles

# Display one article in Inoreader-style card
def display_article_card(article, key_suffix):
    with st.container():
        if article.get("image"):
            st.image(article["image"], use_column_width=True)
        st.markdown(f"### {article['title']}")
        st.markdown(f"*🗓 {article['date'][:10]}*")
        st.markdown(f"**Topics:** {', '.join(article['topics'])}  ")
        st.markdown(f"{article['summary'][:200]}...")
        st.markdown(f"[🔗 Read more]({article['link']})")
        if st.checkbox("⭐ Add to Top 10", key=f"sel_{article['id']}_{key_suffix}"):
            selected.append(article)

# --- UI Starts Here ---
st.title("📰 Maritime News Curator")
selected = []

# Button to fetch news
if st.button("📥 Fetch Latest News"):
    st.session_state["articles"] = fetch_articles()
    st.success(f"Fetched {len(st.session_state['articles'])} articles.")

# Get articles from session or default to empty
articles = st.session_state.get("articles", [])

# Group by topic
topic_buckets = defaultdict(list)
for article in articles:
    for topic in article["topics"]:
        topic_buckets[topic].append(article)

# Sort topics alphabetically
sorted_topics = sorted(topic_buckets.items())

# Config
PAGE_SIZE = 20

# Display per topic
for topic, group_articles in sorted_topics:
    st.markdown(f"## 📌 {topic} ({len(group_articles)} articles)")

    total_pages = math.ceil(len(group_articles) / PAGE_SIZE)
    page = st.number_input(
        f"Page (Topic: {topic})", min_value=1, max_value=total_pages, value=1, key=f"page_{topic}"
    )
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    page_articles = group_articles[start:end]

    # 3-column layout
    for i in range(0, len(page_articles), 3):
        cols = st.columns(3)
        for j in range(3):
            if i + j < len(page_articles):
                with cols[j]:
                    display_article_card(page_articles[i + j], key_suffix=f"{topic}_{i}_{j}")

# --- Export Top 10 ---
st.divider()
if selected:
    st.subheader("📦 Export Top 10 as Markdown")
    markdown = "# Maritime Top 10 News of the Week\n\n"
    for i, a in enumerate(selected[:10], 1):
        markdown += f"## {i}. {a['title']}\n"
        markdown += f"*Date:* {a['date']}  \n"
        markdown += f"*Topics:* {', '.join(a['topics'])}\n\n"
        markdown += f"{a['summary'][:300]}...\n\n"
        markdown += f"[Read more]({a['link']})\n\n"
    st.download_button("📥 Download Markdown", markdown, file_name="top10.md", mime="text/markdown")
