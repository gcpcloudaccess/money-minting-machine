"""News & sentiment data source: free RSS feeds, no API key required.

If NEWSAPI_KEY is set, results are supplemented with NewsAPI headlines, but
the system works fully without it.
"""

from __future__ import annotations

from urllib.parse import quote

import feedparser
import httpx

from app.config import get_settings

MARKET_FEEDS = [
    "https://www.moneycontrol.com/rss/marketreports.xml",
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
]

POLICY_KEYWORDS = ["RBI", "SEBI", "repo rate", "monetary policy", "budget", "tariff", "sanctions", "GST"]
GEOPOLITICAL_KEYWORDS = ["war", "conflict", "sanctions", "election", "trade deal", "crude oil", "OPEC", "border"]


def _tag(text: str) -> list[str]:
    tags = []
    low = text.lower()
    if any(k.lower() in low for k in POLICY_KEYWORDS):
        tags.append("policy")
    if any(k.lower() in low for k in GEOPOLITICAL_KEYWORDS):
        tags.append("geopolitical")
    return tags


def fetch_symbol_news(company_query: str, max_items: int = 10) -> list[dict]:
    """Google News RSS search scoped to a company/stock name."""
    url = f"https://news.google.com/rss/search?q={quote(company_query)}+stock&hl=en-IN&gl=IN&ceid=IN:en"
    feed = feedparser.parse(url)
    items = []
    for entry in feed.entries[:max_items]:
        title = entry.get("title", "")
        summary = entry.get("summary", "")
        items.append(
            {
                "title": title,
                "summary": summary,
                "published": entry.get("published", ""),
                "link": entry.get("link", ""),
                "tags": _tag(f"{title} {summary}"),
            }
        )
    settings = get_settings()
    if settings.newsapi_key:
        items.extend(_fetch_newsapi(company_query, settings.newsapi_key, max_items=5))
    return items


def fetch_market_news(max_items: int = 15) -> list[dict]:
    """Broad market/macro/policy news, not tied to one symbol."""
    items: list[dict] = []
    for url in MARKET_FEEDS:
        try:
            feed = feedparser.parse(url)
        except Exception:
            continue
        for entry in feed.entries[: max_items // len(MARKET_FEEDS) + 1]:
            title = entry.get("title", "")
            summary = entry.get("summary", "")
            items.append(
                {
                    "title": title,
                    "summary": summary,
                    "published": entry.get("published", ""),
                    "link": entry.get("link", ""),
                    "tags": _tag(f"{title} {summary}"),
                }
            )
    return items[:max_items]


def _fetch_newsapi(query: str, api_key: str, max_items: int = 5) -> list[dict]:
    try:
        resp = httpx.get(
            "https://newsapi.org/v2/everything",
            params={"q": query, "language": "en", "sortBy": "publishedAt", "pageSize": max_items},
            headers={"X-Api-Key": api_key},
            timeout=8.0,
        )
        resp.raise_for_status()
        articles = resp.json().get("articles", [])
    except Exception:
        return []
    return [
        {
            "title": a.get("title", ""),
            "summary": a.get("description", "") or "",
            "published": a.get("publishedAt", ""),
            "link": a.get("url", ""),
            "tags": _tag(f"{a.get('title', '')} {a.get('description', '')}"),
        }
        for a in articles
    ]
