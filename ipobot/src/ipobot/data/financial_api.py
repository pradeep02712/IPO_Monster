# src/ipobot/data/financial_api.py
from __future__ import annotations

from typing import Dict, List
from ipobot.fundamentals.ratios import get_fundamentals as _ratios_get

# NOTE:
# We deliberately do NOT append .NS/.BO anymore. The symbol passed in is treated as final.
# If you want NSE/BO, resolve it BEFORE calling this (lookup.py / UI already does that).

def _try_tickers(symbol: str) -> List[str]:
    s = (symbol or "").strip()
    return [s] if s else []

def get_fundamentals(symbol: str, use_live: bool = False) -> Dict:
    """
    Thin wrapper that delegates to fundamentals.ratios.get_fundamentals().
    `use_live` is reserved for future caching/toggling—ignored here.
    Returns a dict of fundamentals (UI-style keys inside the ratios module).
    """
    # You can pass peer_pe here if you have peer logic in config; keeping None by default.
    return _ratios_get(symbol, peer_pe=None) or {}
