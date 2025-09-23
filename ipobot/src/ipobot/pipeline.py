# src/ipobot/pipeline.py

from __future__ import annotations

from .config import load_config
from .data.news_scraper import fetch_news_items
from .data.financial_api import get_fundamentals
from .nlp.sentiment import sentiment_score
from .fundamentals.ratios import score_fundamentals
from .model.predict import load_or_train_model, predict_gain
from .engine.reasoning import build_reason

def _to_ui_fundamentals(f: dict) -> dict:
    """Return only the UI keys, mapping from internal keys when needed."""
    f = f or {}
    def pick(*keys):
        for k in keys:
            v = f.get(k)
            if v is not None:
                return v
        return None
    return {
        "P/E": pick("P/E", "pe"),
        "Peer P/E": pick("Peer P/E", "peer_pe"),
        "ROE (%)": pick("ROE (%)", "roe"),
        "D/E": pick("D/E", "debt_to_equity", "de"),
        "Revenue CAGR (%)": pick("Revenue CAGR (%)", "revenue_cagr", "rev_cagr"),
        "P/E discount vs peer (%)": pick("P/E discount vs peer (%)", "pe_discount_vs_peer"),
    }



def run_pipeline(
    symbol_or_name: str,
    query: str,
    *,
    override_thresholds: dict | None = None,
    symbol_is_final: bool = False,   # <-- NEW: if True, treat symbol_or_name as the final ticker
    **kwargs,
):
    """
    End-to-end analysis with graceful fallbacks.

    Parameters
    ----------
    symbol_or_name : str
        A ticker (e.g., 'TSLA', 'RELIANCE.NS') OR a company/IPO name (e.g., 'Tesla', 'Zomato').
    query : str
        News query string.
    override_thresholds : dict | None
        Optional {'buy_prob': float, 'hold_prob': float} to override config thresholds.
    symbol_is_final : bool
        If True, do NOT call resolve_symbol or auto-append any exchange suffix. Use as-is.

    Returns
    -------
    dict
        {
          symbol, query, sentiment, fundamentals, probability, expected_gain_pct,
          decision, reasoning, news_sample, meta, warnings, errors
        }
    """
    cfg = load_config() or {}
    warnings: list[str] = []
    errors: list[str] = []

    # ---------------- SYMBOL RESOLUTION (robust) ----------------
    raw = (symbol_or_name or "").strip()
    if symbol_is_final:
        sym = raw  # trust the UI / caller
    else:
        # Only resolve if it doesn't already look like a ticker
        looks_like_ticker = (
            ('.' in raw) or (':' in raw) or
            (raw.isupper() and raw.replace('-', '').isalnum() and 1 <= len(raw) <= 6)
        )
        if looks_like_ticker:
            sym = raw
        else:
            # Lazy import to avoid circulars
            from .data.lookup import resolve_symbol
            s, _learned = resolve_symbol(raw)
            sym = s or raw

    # Normalize trivial whitespace/case
    sym = (sym or "").strip()

    # ---------------- NEWS ----------------
    use_live_news = bool(cfg.get("use_live_news", False))
    news_provider = (cfg.get("news", {}) or {}).get("provider", "gnews")
    try:
        news_items = fetch_news_items(query, use_live=use_live_news)
    except Exception as e:
        news_items = []
        errors.append(f"news_fetch_failed: {type(e).__name__}: {e}")

    # ---------------- SENTIMENT ----------------
    # sentiment_score() already checks config.use_live_sentiment and falls back safely
    try:
        sent = sentiment_score(news_items)
    except Exception as e:
        sent = 0.0
        errors.append(f"sentiment_failed: {type(e).__name__}: {e}")

    # ---------------- FUNDAMENTALS ----------------
    use_live_fin = bool(cfg.get("use_live_financials", False))
    try:
        # financial_api.get_fundamentals decides provider(s) based on config; `use_live` toggles live vs cache if supported
        fins = get_fundamentals(sym, use_live=use_live_fin) or {}
    except Exception as e:
        fins = {}
        errors.append(f"fundamentals_failed: {type(e).__name__}: {e}")

    # Basic sanity fill (avoid None downstream)
    for k, v in {
        "pe": None,
        "peer_pe": None,
        "roe": None,
        "debt_to_equity": None,
        "revenue_cagr": None,
    }.items():
        fins.setdefault(k, v)

    # ---------------- FUNDAMENTAL SCORING ----------------
    try:
        fscore, fdetail = score_fundamentals(fins, cfg.get("valuation_weights", {}))
        # fdetail is a structured details dict from score_fundamentals
    except Exception as e:
        # If scoring fails, fall back to a neutral detail dict
        fdetail = {
            "pe": fins.get("pe"),
            "peer_pe": fins.get("peer_pe"),
            "roe": fins.get("roe"),
            "debt_to_equity": fins.get("debt_to_equity"),
            "revenue_cagr": fins.get("revenue_cagr"),
            "pe_discount_vs_peer": None,
            "roe_flag": False,
            "d2e_flag": False,
            "growth_flag": False,
        }
        fscore = 0.5
        errors.append(f"fundamental_scoring_failed: {type(e).__name__}: {e}")

    # ---------------- MODEL ----------------
    model_path = cfg.get("model_path", "models/demo_model.pkl")
    try:
        model = load_or_train_model(model_path)
    except Exception as e:
        errors.append(f"model_load_failed: {type(e).__name__}: {e}")
        model = load_or_train_model(model_path)

    try:
        prob, gain_est = predict_gain(model, sent, fdetail)
    except Exception as e:
        prob, gain_est = 0.5, 0.0
        errors.append(f"prediction_failed: {type(e).__name__}: {e}")

    # ---------------- DECISION ----------------
    thr = dict(cfg.get("thresholds", {}))
    if override_thresholds:
        thr.update(override_thresholds)  # let UI sliders override safely

    buy_thr = float(thr.get("buy_prob", 0.62))
    hold_thr = float(thr.get("hold_prob", 0.45))
    if prob >= buy_thr:
        decision = "BUY"
    elif prob >= hold_thr:
        decision = "HOLD"
    else:
        decision = "AVOID"

    # ---------------- REASONING ----------------
    try:
        why = build_reason(sym, sent, fdetail, prob, gain_est, decision)
    except Exception as e:
        why = f"{decision} for {sym} based on model output. (reasoning_failed: {type(e).__name__})"
        warnings.append("reasoning_fallback_used")

           # ---------------- RETURN ----------------
    ui_fins = _to_ui_fundamentals(fdetail.get("fundamentals", fins))
    return {
        "symbol": sym,
        "query": query,
        "sentiment": sent,
        "fundamentals": ui_fins,          # <- clean, UI-only fields
        "fundamental_details": fdetail,   # <- keep the full details for debugging
        "probability": prob,
        "expected_gain_pct": gain_est,
        "decision": decision,
        "reasoning": why,
        "news_sample": news_items[:5],
        "meta": {
            "use_live_news": use_live_news,
            "use_live_sentiment": bool(cfg.get("use_live_sentiment", False)),
            "use_live_financials": use_live_fin,
            "news_provider": news_provider,
            "model_path": model_path,
        },
        "warnings": warnings,
        "errors": errors,
    }
