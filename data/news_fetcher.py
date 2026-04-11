"""
data/news_fetcher.py — Pulls recent news headlines for a given ticker.
Falls back to mock news gracefully if API key is missing or fails.
"""

import requests
from datetime import datetime, timedelta
from config import NEWS_API_KEY, MOCK_MODE


def get_news(ticker: str, max_articles: int = 5) -> list:
    if MOCK_MODE or not NEWS_API_KEY or NEWS_API_KEY == "your_newsapi_key_here":
        return _mock_news(ticker)
    try:
        clean = ticker.split("/")[0].replace("-USD", "").replace("-", " ")
        from_date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
        resp = requests.get(
            "https://newsapi.org/v2/everything",
            params={"q": clean, "from": from_date, "sortBy": "relevancy",
                    "pageSize": max_articles, "language": "en", "apiKey": NEWS_API_KEY},
            timeout=10,
        )
        articles = resp.json().get("articles", [])
        if not articles:
            return _mock_news(ticker)
        return [{"title": a.get("title",""), "source": a.get("source",{}).get("name","Unknown"),
                 "published_at": a.get("publishedAt","")[:10], "url": a.get("url","")}
                for a in articles[:max_articles]]
    except Exception:
        return _mock_news(ticker)


def _mock_news(ticker: str) -> list:
    base = ticker.split("/")[0]
    return [
        {"title": f"{base} shows resilience amid broader market moves",
         "source": "Market Watch", "published_at": datetime.now().strftime("%Y-%m-%d"), "url": ""},
        {"title": f"Analysts watch {base} closely as volatility continues",
         "source": "Reuters", "published_at": datetime.now().strftime("%Y-%m-%d"), "url": ""},
    ]


def format_news_for_prompt(articles: list) -> str:
    if not articles:
        return "No recent news available."
    return "\n".join(
        f"- [{a['published_at']}] {a['title']} (Source: {a['source']})"
        for a in articles
    )
