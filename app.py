import streamlit as st
import feedparser
import yaml
import hashlib
import json
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup

# Load topics
with open("topics.yaml", "r") as f:
    topic_config = yaml.safe_load(f)

# Load feeds
with open("feeds.yaml", "r") as f:
    feed_config = yaml.safe_load(f)

def clean(text):
    return BeautifulSoup(text, "html.parser").get_text().strip()

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
            date = entry.get("published", datetime.utcnow().isoformat())

            # Generate ID
            id = hashlib.sha1(f"{title}{link}".encode()).hexdigest()
            full_text = f"{title} {summary}"

            matched_topics = []
            for topic, data in topic_config["topics"].items():
                if any(word.lower() in full_text.lower() for word in data.get("include", [])):
                    matched_topics.append(topic)

            articles.append({
                "id": id,
                "title": title,
                "link": link,
                "summary": summary,
                "date": date,
                "topics": matched_topics
            })
    return articles

# Streamlit UI
st.title("📰 Maritime News Curator")

if st.button("Fetch News"):
    articles = fetch_articles()
    st.session_state["articles"] = articles
    st.success(f"Fetched {len(articles)} articles!")

# View + curate
articles = st.session_state.get("articles", [])

selected = []

from collections import defaultdict

# Group articles by topic
topic_buckets = defaultdict(list)
for article in articles:
    topics = article.get("topics", [])
    if not topics:
        topic_buckets["📂 Uncategorized / Other"].append(article)

    else:
        for topic in topics:
            topic_buckets[topic].append(article)

# Sort topics alphabetically
sorted_topics = sorted(topic_buckets.items())

st.subheader("🧠 Curated Topics")

# Page size
PAGE_SIZE = 20

for topic, group_articles in sorted_topics:
    st.markdown(f"### 📌 {topic} ({len(group_articles)} articles)")

    # Add pagination
    total_pages = (len(group_articles) - 1) // PAGE_SIZE + 1
    page = st.number_input(
        f"Page (Topic: {topic})", min_value=1, max_value=total_pages, value=1, key=f"page_{topic}"
    )
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    page_articles = group_articles[start:end]

    for i, a in enumerate(page_articles):
        with st.expander(f"{a['title']}"):
            st.write(f"🗓 {a['date']}")
            st.write(a['summary'])
            st.markdown(f"[Read more]({a['link']})")
            if st.checkbox("⭐ Add to Top 10", key=f"sel_{a['id']}"):
                selected.append(a)

# Export
if selected:
    st.subheader("📦 Export Top 10 as Markdown")
    markdown = "# Maritime Top 10 News of the Week\n\n"
    for i, a in enumerate(selected, 1):
        markdown += f"### {i}. {a['title']}\n"
        markdown += f"*Date:* {a['date']}  \n"
        markdown += f"*Topics:* {', '.join(a['topics'])}\n\n"
        markdown += f"{a['summary']}\n\n"
        markdown += f"[Read more]({a['link']})\n\n"

    st.download_button("Download Markdown", markdown, file_name="top10.md", mime="text/markdown")
