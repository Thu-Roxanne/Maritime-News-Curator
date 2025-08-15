import streamlit as st
import feedparser
import yaml
import hashlib
from datetime import datetime
from bs4 import BeautifulSoup
from collections import defaultdict
import math

st.set_page_config(page_title="Maritime Latest News", layout="wide")

# --- Load topics and feeds ---
with open("topics.yaml", "r") as f:
    topic_config = yaml.safe_load(f)
all_topics = list(topic_config["topics"].keys())

with open("feeds.yaml", "r") as f:
    feed_config = yaml.safe_load(f)

# --- Utility functions ---
def clean(text):
    return BeautifulSoup(text or "", "html.parser").get_text().strip()

def article_id(title, link):
    return hashlib.sha1(f"{title}{link}".encode()).hexdigest()

# 🔍 Improved image extraction
def extract_image(entry):
    # 1. media_content
    media = entry.get("media_content", [])
    if media and isinstance(media, list) and media[0].get("url"):
        return media[0]["url"]

    # 2. media_thumbnail
    if entry.get("media_thumbnail"):
        return entry["media_thumbnail"][0].get("url", "")

    # 3. from summary
    if "summary" in entry:
        soup = BeautifulSoup(entry["summary"], "html.parser")
        img_tag = soup.find("img")
        if img_tag and img_tag.get("src"):
            return img_tag["src"]

    # 4. from content block
    if entry.get("content"):
        html = entry["content"][0].get("value", "")
        soup = BeautifulSoup(html, "html.parser")
        img_tag = soup.find("img")
        if img_tag and img_tag.get("src"):
            return img_tag["src"]

    return ""

# 📰 Fetch and filter articles by topic
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
                image = extract_image(entry)
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

# 🧱 Display article card
def display_article_card(article, key_suffix):
    with st.container():
        if article.get("image"):
            st.image(article["image"], use_column_width=True)
        st.markdown(f"### {article['title']}")
        st.markdown(f"*📅 {article['date'][:10]}*")
        st.markdown(f"**Topics:** {', '.join(article['topics'])}")
        st.markdown(f"{article['summary'][:300]}...")
        st.markdown(f"[🔗 Read more]({article['link']})")
        if st.checkbox("⭐ Add to Top 10", key=f"sel_{article['id']}_{key_suffix}"):
            selected.append(article)

# --- UI ---
st.title("📰 Maritime Latest News")
selected = []

# 🔘 Topic tiles (clickable)
st.markdown("### 📂 Choose a topic")
topic_cols = st.columns(3)

for i, topic in enumerate(all_topics):
    with topic_cols[i % 3]:
        if st.button(topic, key=f"topic_btn_{topic}"):
            st.session_state["selected_topic"] = topic
            st.session_state["articles"] = fetch_articles_for_topic(topic)

# 🧾 Article display
articles = st.session_state.get("articles", [])
selected_topic = st.session_state.get("selected_topic", None)

if articles:
    st.markdown(f"## 📌 {selected_topic} ({len(articles)} articles)")
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

# 💾 Markdown Export
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
