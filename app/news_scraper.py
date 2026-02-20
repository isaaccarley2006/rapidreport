import json
from datetime import datetime, date, timedelta, timezone

import anthropic
import feedparser

import config
from app.models import NewsDigest, get_session

RSS_SOURCES = [
    {"name": "Letting Agent Today", "url": "https://www.lettingagenttoday.co.uk/rss"},
    {"name": "Property Industry Eye", "url": "https://propertyindustryeye.com/feed/"},
    {"name": "Estate Agent Today", "url": "https://www.estateagenttoday.co.uk/rss"},
    {"name": "GOV.UK Housing", "url": "https://www.gov.uk/search/news-and-communications.atom?topics%5B%5D=housing"},
    {"name": "Propertymark", "url": "https://www.propertymark.co.uk/news/rss"},
    {"name": "Goodlord Blog", "url": "https://blog.goodlord.co/rss.xml"},
]

FETCH_TIMEOUT = 30


def _fetch_single_feed(source):
    """Parse one RSS feed and return normalized articles."""
    try:
        feed = feedparser.parse(source["url"])
        articles = []
        for entry in feed.entries[:15]:
            published = ""
            if hasattr(entry, "published"):
                published = entry.published
            elif hasattr(entry, "updated"):
                published = entry.updated

            summary = ""
            if hasattr(entry, "summary"):
                summary = entry.summary[:500]
            elif hasattr(entry, "description"):
                summary = entry.description[:500]

            articles.append({
                "title": getattr(entry, "title", "Untitled"),
                "url": getattr(entry, "link", ""),
                "source": source["name"],
                "published_date": published,
                "summary": summary,
            })
        return articles
    except Exception as e:
        print(f"  [news] Error fetching {source['name']}: {e}")
        return []


def fetch_all_news():
    """Fetch from all RSS sources, combine, dedupe by URL, sort by date."""
    all_articles = []
    seen_urls = set()

    for source in RSS_SOURCES:
        articles = _fetch_single_feed(source)
        for article in articles:
            url = article["url"]
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_articles.append(article)

    all_articles.sort(key=lambda a: a.get("published_date", ""), reverse=True)
    return all_articles


def summarise_news(articles):
    """Use Claude to summarise articles into key themes, stats, and post angles."""
    if not articles:
        return {"summary": "No articles found today.", "key_stats": [], "post_angles": []}

    articles_text = ""
    for i, a in enumerate(articles[:30], 1):
        articles_text += f"\n{i}. [{a['source']}] {a['title']}\n   URL: {a['url']}\n   {a['summary']}\n"

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=2000,
        system=(
            "You are a UK property market research analyst. Analyse these RSS articles and produce a JSON summary.\n\n"
            "RULES:\n"
            "- Extract ONLY explicit statistics mentioned in the articles. NEVER fabricate stats.\n"
            "- For each stat, cite the exact source article.\n"
            "- Post angles should be relevant to a PropTech company (RapidRent) that does tenant referencing.\n"
            "- Focus on UK private rental sector, landlords, letting agents, tenant referencing, and regulation.\n\n"
            "OUTPUT FORMAT (valid JSON only):\n"
            '{"summary": "2-3 paragraph overview of key themes", '
            '"key_stats": [{"stat": "the statistic", "source": "article source name", "url": "article url"}], '
            '"post_angles": ["angle 1", "angle 2", "angle 3"]}'
        ),
        messages=[{"role": "user", "content": f"Analyse these property industry articles from today:\n{articles_text}"}],
    )

    try:
        result = json.loads(message.content[0].text)
        return result
    except json.JSONDecodeError:
        import re
        match = re.search(r'\{.*\}', message.content[0].text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return {"summary": message.content[0].text, "key_stats": [], "post_angles": []}


def run_daily_digest():
    """Orchestrator: fetch articles, summarise, save to NewsDigest."""
    db = get_session()
    today = date.today()

    existing = db.query(NewsDigest).filter_by(date=today).first()
    if existing:
        db.close()
        print(f"  [news] Digest for {today} already exists, skipping.")
        return existing

    print(f"  [news] Fetching RSS feeds for {today}...")
    articles = fetch_all_news()
    print(f"  [news] Found {len(articles)} articles, summarising...")

    result = summarise_news(articles)

    digest = NewsDigest(
        date=today,
        raw_articles_json=json.dumps(articles),
        summary=result.get("summary", ""),
        key_stats_json=json.dumps(result.get("key_stats", [])),
        post_angles_json=json.dumps(result.get("post_angles", [])),
        article_count=len(articles),
    )
    db.add(digest)
    db.commit()
    db.refresh(digest)
    db.close()
    print(f"  [news] Saved digest for {today} with {len(articles)} articles.")
    return digest


def get_recent_digests(days=7):
    """Get recent NewsDigest entries."""
    db = get_session()
    cutoff = date.today() - timedelta(days=days)
    digests = (
        db.query(NewsDigest)
        .filter(NewsDigest.date >= cutoff)
        .order_by(NewsDigest.date.desc())
        .all()
    )
    db.close()
    return digests
