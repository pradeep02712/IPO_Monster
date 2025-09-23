# src/ipobot/data/news_scraper.py
from typing import List, Dict
import os, requests, html, urllib.parse
import feedparser  # optional but used for RSS fallback

# ================= sentiment heuristic (swap for FinBERT later) =================
def _rule_sentiment(title: str) -> str:
    t = (title or "").lower()
    pos = any(k in t for k in [
        "strong", "robust", "beats", "record", "growth", "surge",
        "gmp up", "oversubscribed", "solid", "subscription", "upgraded",
        "profit", "order book", "margin expansion", "bumper", "subscribe"
    ])
    neg = any(k in t for k in [
        "probe", "flag", "warning", "decline", "fall", "downgrade", "delay",
        "sebi", "fraud", "scam", "controversy", "penalty", "loss", "issue",
        "allegation", "penalised", "adverse"
    ])
    if pos and not neg: return "positive"
    if neg and not pos: return "negative"
    return "neutral"

# ================= config loader ===============================================
def _from_config():
    try:
        from ipobot.config import load_config
        cfg = load_config() or {}
        news_cfg = (cfg.get("news") or {})
        return {
            "provider": (news_cfg.get("provider") or "gnews").lower(),
            "api_key": news_cfg.get("api_key") or os.getenv("GNEWS_API_KEY") or os.getenv("NEWSAPI_KEY"),
            "language": news_cfg.get("language", "en"),
            "page_size": int(news_cfg.get("page_size", 8)),
        }
    except Exception:
        # Safe defaults
        return {"provider": "gnews", "api_key": os.getenv("GNEWS_API_KEY"), "language": "en", "page_size": 8}

# ================= providers ====================================================
def _newsapi_fetch(query: str, api_key: str, lang: str, n: int) -> List[Dict]:
    url = "https://newsapi.org/v2/everything"
    params = {"q": query, "language": lang, "pageSize": n, "sortBy": "publishedAt", "apiKey": api_key}
    r = requests.get(url, params=params, timeout=12)
    try:
        r.raise_for_status()
    except requests.HTTPError:
        err_text = (r.text or "")[:150].replace("\n", " ")
        msg = f"NewsAPI HTTP {r.status_code}: {err_text}"
        return [{"title": f"{query}: live fetch failed ({msg})", "sent": "neutral"}]
    data = r.json()
    items: List[Dict] = []
    for a in (data.get("articles") or []):
        title = html.unescape(a.get("title") or "").strip()
        if title:
            items.append({"title": title, "sent": _rule_sentiment(title)})
    return items

def _gnews_fetch(query: str, api_key: str, lang: str, n: int) -> List[Dict]:
    # Docs: https://gnews.io/docs/v4#search
    url = "https://gnews.io/api/v4/search"
    params = {"q": query, "lang": lang, "max": n, "token": api_key, "sortby": "publishedAt"}
    r = requests.get(url, params=params, timeout=12)
    try:
        r.raise_for_status()
    except requests.HTTPError:
        err_text = (r.text or "")[:150].replace("\n", " ")
        msg = f"GNews HTTP {r.status_code}: {err_text}"
        return [{"title": f"{query}: live fetch failed ({msg})", "sent": "neutral"}]
    data = r.json()
    items: List[Dict] = []
    for a in (data.get("articles") or []):
        title = html.unescape((a.get("title") or "")).strip()
        if title:
            items.append({"title": title, "sent": _rule_sentiment(title)})
    return items

def _google_rss_fetch(query: str, lang: str, n: int) -> List[Dict]:
    # No key needed; Google News RSS
    q = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={q}&hl={lang}"
    feed = feedparser.parse(url)
    items: List[Dict] = []
    for e in (feed.entries or [])[:n]:
        title = html.unescape(getattr(e, "title", "")).strip()
        if title:
            items.append({"title": title, "sent": _rule_sentiment(title)})
    return items or [{"title": f"{query}: no recent articles (RSS)", "sent": "neutral"}]

# ================= main entry ===================================================
def fetch_news_items(query: str, use_live: bool = False) -> List[Dict]:
    """
    Return a list of dicts: {title, sent}. If use_live=False -> simulated sample.
    """
    if not use_live:
        return [
            {"title": f"{query}: solid subscription numbers reported", "sent": "positive"},
            {"title": f"{query}: robust order book; margin guidance intact", "sent": "positive"},
            {"title": f"{query}: SEBI query on related-party disclosure", "sent": "negative"},
            {"title": f"{query}: grey market premium steady", "sent": "positive"},
            {"title": f"{query}: analyst flags valuation stretch", "sent": "negative"},
        ]

    cfg = _from_config()
    provider, api_key, lang, n = cfg["provider"], cfg["api_key"], cfg["language"], cfg["page_size"]

    items: List[Dict] = []

    if provider == "gnews":
        if not api_key:
            items = [{"title": f"{query}: GNews key missing", "sent": "neutral"}]
        else:
            items = _gnews_fetch(query, api_key, lang, n)

    elif provider == "newsapi":
        if not api_key:
            items = [{"title": f"{query}: NewsAPI key missing", "sent": "neutral"}]
        else:
            items = _newsapi_fetch(query, api_key, lang, n)

    elif provider == "google_rss":
        items = _google_rss_fetch(query, lang, n)

    else:
        items = [{"title": f"{query}: unknown provider '{provider}'", "sent": "neutral"}]

    # Fallback: if API returned error headline or empty, append RSS results
    need_fallback = (not items) or any("live fetch failed" in (it.get("title") or "") for it in items)
    if need_fallback and provider != "google_rss":
        items = [it for it in items if "live fetch failed" not in (it.get("title") or "")]
        items.extend(_google_rss_fetch(query, lang, n))

    return items
