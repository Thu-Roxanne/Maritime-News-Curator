import streamlit as st
import feedparser
import yaml
import hashlib
import json
from datetime import datetime
from bs4 import BeautifulSoup
from collections import defaultdict
import math

st.set_page_config(page_title="Maritime News Curator", layout="wide")

# Load topics
with open("topics.yaml", "r") as f:
    topic_config = yaml.safe_load(f)
all_topics = list(topic_config["topics"].keys())

# Load feeds
with open("feeds.yaml", "r") as f:
    feed_config = yaml.safe_load(f)

# Clean HTML
def clean(text):
    return BeautifulSoup(text or "", "html.parser").get_text().strip()

# Generate unique ID
def article_id(title, link):
    return hashlib.sha1(f"{title}{link}".encode()).hexdigest()

# Fetch and filter articles
def fetch_articles_for_topic(selected_topic):
    all_articles = []
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

            matched_topics = []
            for topic, data in topic_config["topics"].items():
                if any(word.lower() in full_text.lower() for word in data.get("include", [])):
                    matched_topics.append(topic)

            if selected_topic in matched_topics:
                image = ""
                media = entry.get("media_content", [])
                if media and isinstance(media, list):
                    image = media[0].get("url", "")

                all_articles.append({
                    "id": article_id(title, link),
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "date": pub_date,
                    "topics": matched_topics,
                    "image": image or ""
                })
    return all_articles

# Display article card
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

# UI
st.title("🗂 Maritime News Curator by Topic")
selected = []

# 1. Select topic
selected_topic = st.selectbox("Choose a topic to fetch news for:", all_topics)

# 2. Fetch when topic is selected
if selected_topic and st.button("🔍 Fetch News for Topic"):
    articles = fetch_articles_for_topic(selected_topic)
    st.session_state["articles"] = articles
    st.session_state["selected_topic"] = selected_topic
    st.success(f"Fetched {len(articles)} articles for **{selected_topic}**.")

# 3. Display results
articles = st.session_state.get("articles", [])
selected_topic = st.session_state.get("selected_topic", None)

if articles:
    st.markdown(f"## 🔖 {selected_topic} ({len(articles)} articles)")
    PAGE_SIZE = 20
    total_pages = math.ceil(len(articles) / PAGE_SIZE)
    page = st.number_input("Page", 1, total_pages, 1, key=f"page_{selected_topic}")
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    page_articles = articles[start:end]

    for i in range(0, len(page_articles), 3):
        cols = st.columns(3)
        for j in range(3):
            if i + j < len(page_articles):
                with cols[j]:
                    display_article_card(page_articles[i + j], key_suffix=f"{selected_topic}_{i}_{j}")

    st.divider()

# 4. Export Top 10
if selected:
    st.subheader("📦 Export Top 10 as Markdown")
    markdown = f"# Maritime Top 10 – {selected_topic}\n\n"
    for i, a in enumerate(selected[:10], 1):
        markdown += f"## {i}. {a['title']}\n"
        markdown += f"*Date:* {a['date']}  \n"
        markdown += f"*Topics:* {', '.join(a['topics'])}\n\n"
        markdown += f"{a['summary'][:300]}...\n\n"
        markdown += f"[Read more]({a['link']})\n\n"
    st.download_button("📥 Download Markdown", markdown, file_name=f"top10-{selected_topic}.md", mime="text/markdown")
