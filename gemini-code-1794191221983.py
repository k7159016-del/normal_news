import streamlit as st
import requests
import xml.etree.ElementTree as ET
import re
import html
from datetime import datetime
from email.utils import parsedate_to_datetime

# ============================================================
# FEEDS
# ============================================================

NATION_FEEDS = {
    "The Hindu": "https://www.thehindu.com/news/national/feeder/default.rss",
    "Times of India": "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms",
    "Hindustan Times": "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml",
}

PUNJAB_FEEDS = {
    "TOI Chandigarh/Punjab": "https://timesofindia.indiatimes.com/rssfeeds/3908285.cms",
    "Indian Express (North)": "https://indianexpress.com/section/cities/chandigarh/feed/",
    "News18 Punjab": "https://punjabi.news18.com/rss/punjab.xml",
}

ECONOMY_FEEDS = {
    "Economic Times": "https://economictimes.indiatimes.com/rssfeeds/1373380680.cms",
    "LiveMint": "https://www.livemint.com/rss/economy",
    "Hindu BusinessLine": "https://www.thehindubusinessline.com/economy/feeder/default.rss",
}

SPORTS_FEEDS = {
    "Times of India": "https://timesofindia.indiatimes.com/rssfeeds/4719148.cms",
    "The Hindu": "https://www.thehindu.com/sport/feeder/default.rss",
    "Hindustan Times": "https://www.hindustantimes.com/feeds/rss/sports/rssfeed.xml",
}


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Daily News Dashboard",
    page_icon="📰",
    layout="wide"
)

# ============================================================
# CSS
# ============================================================

st.markdown("""
<style>
.block-container {
    max-width: 1250px;
    padding-top: 1.5rem;
}
.main-title {
    font-size: 34px;
    font-weight: 800;
    margin-bottom: 2px;
}
.subtitle {
    color: #777;
    font-size: 14px;
    margin-bottom: 25px;
}
.section-title {
    font-size: 27px;
    font-weight: 800;
    margin-top: 10px;
    margin-bottom: 5px;
}
.section-line {
    border-bottom: 3px solid #d71920;
    margin-bottom: 25px;
}
.article-title {
    font-size: 21px;
    font-weight: 700;
    line-height: 1.35;
    margin-bottom: 7px;
}
.article-source {
    font-size: 12px;
    font-weight: 700;
    margin-bottom: 3px;
}
.article-date {
    color: #777;
    font-size: 13px;
    margin-bottom: 10px;
}
.article-description {
    color: #555;
    font-size: 14px;
    line-height: 1.5;
    margin-bottom: 12px;
}
.article-divider {
    border-bottom: 1px solid #e5e5e5;
    margin: 25px 0;
}
div[data-testid="stImage"] img {
    border-radius: 8px;
}
button[data-baseweb="tab"] {
    font-size: 16px;
    font-weight: 600;
}
</style>
""", unsafe_allow_html=True)


# ============================================================
# DATE PARSER
# ============================================================

def parse_date(value):
    if not value:
        return datetime.min
    value = str(value).strip()
    if not value:
        return datetime.min

    try:
        return datetime.strptime(value, "%Y-%m-%d %I:%M:%S %p")
    except Exception:
        pass

    try:
        return datetime.strptime(value, "%Y-%m-%d %I:%M %p")
    except Exception:
        pass

    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt
    except Exception:
        pass

    try:
        iso_value = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso_value)
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt
    except Exception:
        pass

    formats = [
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S%z", "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
        "%d %b %Y %H:%M:%S", "%d %b %Y %H:%M", "%d %B %Y %H:%M:%S",
        "%d %B %Y %H:%M", "%a, %d %b %Y %H:%M:%S", "%a, %d %b %Y %H:%M",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except Exception:
            continue

    return datetime.min

def format_date(dt):
    if dt == datetime.min:
        return "Date unavailable"
    return dt.strftime("%d %b %Y • %I:%M %p")


# ============================================================
# CONTENT EXTRACTION & CLEANING
# ============================================================

def clean_html(text):
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def get_text(element, tag):
    child = element.find(tag)
    if child is None or child.text is None:
        return ""
    return child.text.strip()

def find_article_date(item):
    fields = ["pubDate", "published", "updated", "date", "created"]
    for field in fields:
        value = get_text(item, field)
        if value:
            parsed = parse_date(value)
            if parsed != datetime.min:
                return parsed

    for child in item:
        tag = child.tag.lower()
        if any(keyword in tag for keyword in ["date", "published", "updated", "created", "pubdate"]):
            if child.text:
                parsed = parse_date(child.text.strip())
                if parsed != datetime.min:
                    return parsed
    return datetime.min

def find_image(item):
    image_element = item.find("image")
    if image_element is not None and image_element.text:
        url = image_element.text.strip()
        if url: return url

    for child in item:
        tag = child.tag.lower()
        if "content" in tag or "thumbnail" in tag or "image" in tag:
            url = child.attrib.get("url", "")
            if url: return url

    enclosure = item.find("enclosure")
    if enclosure is not None:
        url = enclosure.attrib.get("url", "")
        if url: return url

    return ""


# ============================================================
# FETCH & PARSE LOGIC
# ============================================================

def parse_rss(xml_data, source):
    root = ET.fromstring(xml_data)
    articles = []
    items = root.findall(".//item")

    for item in items:
        title = get_text(item, "title")
        if not title:
            continue

        article = {
            "source": source,
            "title": clean_html(title),
            "link": get_text(item, "link"),
            "description": clean_html(get_text(item, "description")),
            "image": find_image(item),
            "datetime": find_article_date(item),
        }
        articles.append(article)
    return articles

@st.cache_data(ttl=300)
def fetch_feed(url, source):
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0 Safari/537.36",
        "Accept": "application/rss+xml,application/xml,text/xml,*/*",
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return parse_rss(response.content, source)

def fetch_sources(feeds):
    articles = []
    errors = []
    for source, url in feeds.items():
        try:
            articles.extend(fetch_feed(url, source))
        except Exception as e:
            errors.append(f"{source}: {str(e)}")
    return deduplicate(sort_articles(articles)), errors


def deduplicate(articles):
    seen = set()
    result = []
    for article in articles:
        unique_key = article.get("link", "").strip().lower() or article.get("title", "").strip().lower()
        if not unique_key or unique_key in seen:
            continue
        seen.add(unique_key)
        result.append(article)
    return result

def sort_articles(articles):
    return sorted(articles, key=lambda x: x.get("datetime", datetime.min), reverse=True)

def apply_search(articles, search_term):
    if not search_term:
        return articles
    search_term = search_term.lower().strip()
    return [
        a for a in articles 
        if search_term in a.get("title", "").lower() or search_term in a.get("description", "").lower()
    ]


# ============================================================
# RENDER COMPONENTS
# ============================================================

def display_article(article):
    title = article.get("title", "Untitled")
    link = article.get("link", "")
    description = article.get("description", "")
    image = article.get("image", "")
    source = article.get("source", "")
    article_datetime = article.get("datetime", datetime.min)

    if len(description) > 400:
        description = description[:400] + "..."

    image_col, content_col = st.columns([1.2, 3], gap="large")

    with image_col:
        if image:
            try:
                st.image(image, use_container_width=True)
            except Exception:
                st.write("📰")
        else:
            st.write("📰")

    with content_col:
        st.markdown(f'<div class="article-source">{source}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="article-title">{title}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="article-date">🕒 {format_date(article_datetime)}</div>', unsafe_allow_html=True)
        
        if description:
            st.markdown(f'<div class="article-description">{description}</div>', unsafe_allow_html=True)
        if link:
            st.link_button("Read Full Story →", link)
            
    st.markdown('<div class="article-divider"></div>', unsafe_allow_html=True)


def render_tab(tab_name, icon, raw_articles, errors, selected_sources, search_query):
    st.markdown(
        f'<div class="section-title">{icon} {tab_name} News</div>',
        unsafe_allow_html=True
    )
    st.markdown('<div class="section-line"></div>', unsafe_allow_html=True)

    # Apply filters specific to this tab
    filtered = [a for a in raw_articles if a.get("source") in selected_sources]
    filtered = apply_search(filtered, search_query)
    
    if filtered:
        source_counts = {}
        for a in filtered:
            src = a.get("source", "Unknown")
            source_counts[src] = source_counts.get(src, 0) + 1

        cols = st.columns(len(source_counts))
        for col, (src, count) in zip(cols, source_counts.items()):
            col.metric(src, count)
            
        st.divider()

        for article in filtered:
            display_article(article)
    else:
        st.info(f"No {tab_name.lower()} news found matching your criteria.")

    if errors:
        with st.expander("⚠️ Feed status"):
            for error in errors:
                st.warning(error)


# ============================================================
# APP EXECUTION
# ============================================================

# Fetch All Data
nation_articles, nation_err = fetch_sources(NATION_FEEDS)
punjab_articles, punjab_err = fetch_sources(PUNJAB_FEEDS)
economy_articles, economy_err = fetch_sources(ECONOMY_FEEDS)
sports_articles, sports_err = fetch_sources(SPORTS_FEEDS)

# Header
st.markdown('<div class="main-title">📰 Daily News Dashboard</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="subtitle">Top Stories • Punjab Local • Economy & Business • Sports</div>',
    unsafe_allow_html=True
)

# Sidebar Options
with st.sidebar:
    st.header("🔎 Filters")
    search = st.text_input("Search news", placeholder="e.g. RBI, Election, Cricket...")
    st.divider()

    st.subheader("📡 Filter Sources")
    with st.expander("Nation Sources", expanded=False):
        sel_nation = st.multiselect("Show", list(NATION_FEEDS.keys()), list(NATION_FEEDS.keys()))
    with st.expander("Punjab Sources", expanded=False):
        sel_punjab = st.multiselect("Show", list(PUNJAB_FEEDS.keys()), list(PUNJAB_FEEDS.keys()))
    with st.expander("Economy Sources", expanded=False):
        sel_economy = st.multiselect("Show", list(ECONOMY_FEEDS.keys()), list(ECONOMY_FEEDS.keys()))
    with st.expander("Sports Sources", expanded=False):
        sel_sports = st.multiselect("Show", list(SPORTS_FEEDS.keys()), list(SPORTS_FEEDS.keys()))
        
    st.divider()
    
    if st.button("🔄 Refresh News", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption("Feeds automatically refresh every 5 minutes.")

# Tabs Setup
t_nation, t_punjab, t_economy, t_sports = st.tabs([
    f"🇮🇳 Nation ({len(apply_search([a for a in nation_articles if a.get('source') in sel_nation], search))})",
    f"🌾 Punjab ({len(apply_search([a for a in punjab_articles if a.get('source') in sel_punjab], search))})",
    f"📈 Economy ({len(apply_search([a for a in economy_articles if a.get('source') in sel_economy], search))})",
    f"🏏 Sports ({len(apply_search([a for a in sports_articles if a.get('source') in sel_sports], search))})"
])

# Render Each Tab
with t_nation:
    render_tab("Nation", "🇮🇳", nation_articles, nation_err, sel_nation, search)

with t_punjab:
    render_tab("Punjab", "🌾", punjab_articles, punjab_err, sel_punjab, search)

with t_economy:
    render_tab("Economy", "📈", economy_articles, economy_err, sel_economy, search)

with t_sports:
    render_tab("Sports", "🏏", sports_articles, sports_err, sel_sports, search)

st.divider()
st.caption("Aggregated from public RSS feeds of major Indian publications.")