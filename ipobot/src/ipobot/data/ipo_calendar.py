# src/ipobot/data/ipo_calendar.py
from __future__ import annotations
from typing import List, Dict
import requests, datetime as dt
from bs4 import BeautifulSoup

Headers = {"User-Agent": "Mozilla/5.0 (compatible; IPOBot/1.0)"}

def _clean(text: str) -> str:
    return " ".join((text or "").split()).strip()

def _parse_dates(d: str) -> str | None:
    # tries to keep an ISO-ish string
    try:
        return str(dt.datetime.strptime(d.strip(), "%d %b %Y").date())
    except Exception:
        try:
            return str(dt.datetime.strptime(d.strip(), "%d %B %Y").date())
        except Exception:
            return None

def fetch_chittorgarh() -> List[Dict]:
    """Scrape upcoming/mainboard+SME IPOs from Chittorgarh (public, fast)."""
    url = "https://www.chittorgarh.com/report/upcoming-ipo-calendar-in-india/83/"
    r = requests.get(url, headers=Headers, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    tbls = soup.select("table.table")
    items: List[Dict] = []
    for tbl in tbls:
        for tr in tbl.select("tbody tr"):
            tds = [ _clean(td.get_text(" ", strip=True)) for td in tr.select("td") ]
            if len(tds) < 6: 
                continue
            name = tds[0]
            # Usually columns: Company, Issue Size, Open, Close, Price Band, Min Lot ...
            open_dt = _parse_dates(tds[2]) if tds[2] else None
            close_dt = _parse_dates(tds[3]) if tds[3] else None
            price_band = tds[4] or None
            lot = tds[5] or None
            items.append({
                "name": name,
                "symbol": None,              # not always available here
                "open_date": open_dt,
                "close_date": close_dt,
                "price_band": price_band,
                "lot_size": lot,
                "source": "chittorgarh",
                "exchange": None,
                "status": "upcoming",
            })
    return items

def fetch_ipowatch() -> List[Dict]:
    """Scrape IPOWatch upcoming IPOs."""
    url = "https://ipowatch.in/upcoming-ipo-calendar/"; 
    r = requests.get(url, headers=Headers, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    rows = soup.select("table tr")
    items: List[Dict] = []
    for tr in rows:
        tds = [ _clean(td.get_text(" ", strip=True)) for td in tr.select("td") ]
        if len(tds) < 5: 
            continue
        name = tds[0]
        open_dt = _parse_dates(tds[1]) if tds[1] else None
        close_dt = _parse_dates(tds[2]) if tds[2] else None
        price_band = tds[3] or None
        lot = tds[4] or None
        items.append({
            "name": name,
            "symbol": None,
            "open_date": open_dt,
            "close_date": close_dt,
            "price_band": price_band,
            "lot_size": lot,
            "source": "ipowatch",
            "exchange": None,
            "status": "upcoming",
        })
    return items

def merge_and_dedupe(lists: List[List[Dict]]) -> List[Dict]:
    """Merge lists and de-duplicate by normalized name."""
    out: Dict[str, Dict] = {}
    for L in lists:
        for it in L:
            key = _clean((it.get("name") or "").lower())
            if not key:
                continue
            if key not in out:
                out[key] = it
            else:
                # prefer earliest open date, fill missing fields
                cur = out[key]
                for k, v in it.items():
                    if not cur.get(k) and v:
                        cur[k] = v
    return list(out.values())

def fetch_upcoming_ipos() -> List[Dict]:
    """Public, no-key calendar aggregator with graceful fallbacks."""
    items: List[Dict] = []
    try:
        items.extend(fetch_chittorgarh())
    except Exception:
        pass
    try:
        items.extend(fetch_ipowatch())
    except Exception:
        pass
    if not items:
        return []
    merged = merge_and_dedupe([items])
    # optional: filter only where open/close present or open in next 60d
    return merged
