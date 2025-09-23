# src/ipobot/data/lookup.py
from __future__ import annotations
from typing import Optional, Dict, Tuple, Any
import os, requests, json
from pathlib import Path
from ipobot.config import load_config   # keep this import

# ---- default seed mappings (you can keep editing these) ----
NAME_TO_SYMBOL: Dict[str, str] = {
    "oyo": "OYO.NS",
    "lic": "LICI.NS",
    "zomato": "ZOMATO.NS",
    "jsw steel": "JSWSTEEL.NS",
    "jswsteel": "JSWSTEEL.NS",
}

# Persistent store lives next to this file
PERSIST_PATH = Path(__file__).resolve().parent / "mappings.json"


def _load_persistent_mappings() -> Dict[str, str]:
    """Load mappings.json if present and merge into NAME_TO_SYMBOL (lowercased keys)."""
    try:
        if PERSIST_PATH.exists():
            data = json.loads(PERSIST_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(k, str) and isinstance(v, str):
                        NAME_TO_SYMBOL.setdefault(k.strip().lower(), v.strip())
    except Exception:
        # non-fatal
        pass
    return NAME_TO_SYMBOL


def _save_persistent_mappings() -> None:
    """Save the current NAME_TO_SYMBOL (lowercased keys only for user-added items) to mappings.json."""
    try:
        clean = {
            k.strip().lower(): v
            for k, v in NAME_TO_SYMBOL.items()
            if isinstance(k, str) and isinstance(v, str)
        }
        PERSIST_PATH.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        # non-fatal
        pass


# Load any saved mappings at import time
_load_persistent_mappings()


def _normalize_symbol(sym: Optional[str]) -> Optional[str]:
    """
    Normalize symbols conservatively.
    - 'NSE:ZOMATO' -> 'ZOMATO.NS'
    - 'ZOMATO.NS'  -> 'ZOMATO.NS'
    - 'TSLA'       -> 'TSLA'        (do NOT force .NS)
    - 'NASDAQ:TSLA' or 'AAPL' with any suffix -> returned as-is
    """
    if not isinstance(sym, str):
        return None
    s = sym.strip().upper()
    if not s:
        return None
    if s.startswith("NSE:"):
        return s.split(":", 1)[1] + ".NS"
    # already qualified (has a suffix like .NS/.NS/.NYQ etc. or an exchange prefix) -> leave as-is
    if "." in s or ":" in s:
        return s
    # default: leave plain tickers unchanged
    return s


def _pick_best_finnhub_symbol(results: list[dict[str, Any]]) -> Optional[str]:
    """
    Prefer explicit NSE results if present, else the first valid symbol.
    Finnhub result fields: 'symbol', 'displaySymbol', 'description', etc.
    """
    if not results:
        return None

    # First pass: explicit NSE markers
    for item in results:
        sym = (item.get("symbol") or item.get("displaySymbol") or "").upper()
        if sym.startswith("NSE:") or sym.endswith(".NS"):
            return sym

    # Second pass: look for India context in description (best-effort)
    for item in results:
        desc = (item.get("description") or "").lower()
        if "india" in desc or "nse" in desc:
            sym = (item.get("symbol") or item.get("displaySymbol") or "")
            return sym

    # Fallback: take the first symbol
    sym = results[0].get("symbol") or results[0].get("displaySymbol")
    return sym if isinstance(sym, str) else None


def _load_lookup_cfg() -> tuple[str, Optional[str]]:
    """
    Returns (provider, api_key) from config or env.
    Supports:
      - config['symbol_lookup']
      - config['news']['symbol_lookup']  (backward compatibility)
      - env: FINNHUB_API_KEY / FINNHUB_TOKEN
    """
    cfg = load_config() or {}
    lut = (cfg.get("symbol_lookup")
           or cfg.get("news", {}).get("symbol_lookup")
           or {}) or {}
    provider = (lut.get("provider") or "finnhub").lower()
    api_key = lut.get("api_key") or os.getenv("FINNHUB_API_KEY") or os.getenv("FINNHUB_TOKEN")
    return provider, api_key


def resolve_symbol(ipo_name: str) -> tuple[Optional[str], bool]:
    """
    Returns (symbol, learned)
    learned=True when we discovered it via API and saved to mappings.json
    """
    if not ipo_name:
        return None, False
    name_key = ipo_name.strip().lower()

    # 1) local/persisted
    if name_key in NAME_TO_SYMBOL:
        return _normalize_symbol(NAME_TO_SYMBOL[name_key]), False

    # 2) live lookup
    symbol = fetch_symbol_from_api(ipo_name)
    if symbol:
        symbol = _normalize_symbol(symbol)  # ensure normalized before saving/returning
        if symbol:
            NAME_TO_SYMBOL[name_key] = symbol
            _save_persistent_mappings()
            return symbol, True

    return None, False


def fetch_symbol_from_api(ipo_name: str) -> Optional[str]:
    """
    Uses config symbol_lookup to pick provider. Default: finnhub.
    Supported provider(s):
      - finnhub  (requires api_key)
    """
    provider, api_key = _load_lookup_cfg()
    if not api_key:
        return None

    if provider == "finnhub":
        url = "https://finnhub.io/api/v1/search"
        params = {"q": ipo_name, "token": api_key}
        try:
            r = requests.get(url, params=params, timeout=6)
            r.raise_for_status()
            data = r.json() or {}
            results = data.get("result") or []
            if not results:
                return None
            best = _pick_best_finnhub_symbol(results)
            return _normalize_symbol(best) if best else None
        except Exception:
            return None

    # Add other providers here later (Alpha Vantage SYMBOL_SEARCH, Yahoo, etc.)
    return None


def suggest_symbol(ipo_name: str) -> str:
    """Last-resort fallback if nothing resolves (UI-safe placeholder)."""
    return ipo_name.strip().upper().replace(" ", "_")
