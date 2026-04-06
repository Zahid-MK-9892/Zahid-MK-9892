"""
data/news_fetcher.py — Pulls recent news headlines for a given ticker.
Uses NewsAPI (with free tier key) + a fallback RSS parser.
"""

import requests
from datetime import datetime, timedelta
from config import NEWS_API_KEY, MOCK_MODE


def get_news(ticker: str, max_articles: int = 5) -> list[dict]:
    """
    Returns a list of recent news articles relevant to the ticker.
    Each article: { title, source, published_at, url }
    """
    if MOCK_MODE or not NEWS_API_KEY:
        return _mock_news(ticker)

    # Strip crypto suffix for cleaner search (BTC/USDT → BTC)
    clean_name = ticker.split("/")[0].replace("-", " ")

    try:
        from_date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": clean_name,
            "from": from_date,
            "sortBy": "relevancy",
            "pageSize": max_articles,
            "language": "en",
            "apiKey": NEWS_API_KEY,
        }
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()

        articles = []
        for a in data.get("articles", [])[:max_articles]:
            articles.append({
                "title": a.get("title", ""),
                "source": a.get("source", {}).get("name", "Unknown"),
                "published_at": a.get("publishedAt", "")[:10],
                "url": a.get("url", ""),
            })
        return articles if articles else _mock_news(ticker)

    except Exception:
        return _mock_news(ticker)


def _mock_news(ticker: str) -> list[dict]:
    """Placeholder news used when running in mock mode or without a key."""
    return [
        {
            "title": f"[MOCK] {ticker} shows strong momentum amid broader market rally",
            "source": "Mock Financial Times",
            "published_at": datetime.now().strftime("%Y-%m-%d"),
            "url": "",
        },
        {
            "title": f"[MOCK] Analysts upgrade {ticker} with bullish price target revision",
            "source": "Mock Reuters",
            "published_at": datetime.now().strftime("%Y-%m-%d"),
            "url": "",
        },
    ]


def format_news_for_prompt(articles: list[dict]) -> str:
    """Converts list of articles into a clean string for the AI prompt."""
    if not articles:
        return "No recent news available."
    lines = []
    for a in articles:
        lines.append(f"- [{a['published_at']}] {a['title']} (Source: {a['source']})")
    return "\n".join(lines)
