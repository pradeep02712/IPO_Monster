# fundamentals/ratios.py
# Hybrid fundamentals: NSE(.NS P/E) -> Finnhub -> FMP -> AlphaVantage -> yfinance-computed
# Works without yfinance.info and is resilient to Yahoo 404s

from dotenv import load_dotenv
load_dotenv()  # reads .env from project root

import os, time, requests
import pandas as pd
import yfinance as yf
from ipobot.config import load_config  # for score_fundamentals

# ---------- config ----------
REQ_TIMEOUT = 12  # seconds
YF_HISTORY_PERIODS = ["1mo", "3mo", "6mo"]
NSE_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

# ---------- small utils ----------
def _to_float(x):
    if x is None: return None
    if isinstance(x, (int, float)): return float(x)
    try:
        return float(str(x).replace(",", ""))
    except Exception:
        return None

def _safe_div(a, b):
    try:
        if a is None or b in (None, 0): return None
        return a / b
    except Exception:
        return None

def _pct(x): return None if x is None else x * 100.0

def _revenue_cagr(series, min_years=3, max_years=5):
    vals = [v for v in series if v is not None]
    if len(vals) < min_years: return None
    n = min(max(len(vals), min_years), max_years)
    start, end = vals[n-1], vals[0]
    if start and start > 0:
        return (end / start) ** (1/(n-1)) - 1
    return None

def _round(x): return None if x is None else round(float(x), 2)

def _session():
    s = requests.Session()
    adapter = requests.adapters.HTTPAdapter(max_retries=2)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s

# ---------- NSE (unofficial) just for P/E on .NS ----------
def _nse_pe(nse_ticker_wo_suffix):
    url = "https://www.nseindia.com/api/quote-equity"
    s = _session()
    try:
        # prime cookies
        s.get("https://www.nseindia.com", headers=NSE_HEADERS, timeout=REQ_TIMEOUT)
        time.sleep(0.25)
        hdrs = dict(NSE_HEADERS)
        hdrs["Referer"] = f"https://www.nseindia.com/get-quotes/equity?symbol={nse_ticker_wo_suffix}"
        r = s.get(url, headers=hdrs, params={"symbol": nse_ticker_wo_suffix}, timeout=REQ_TIMEOUT)
        if r.ok:
            js = r.json()
            return _to_float(js.get("priceInfo", {}).get("pE"))
    except Exception:
        return None
    return None

# ---------- Finnhub ----------
def _from_finnhub(symbol):
    key = os.getenv("FINNHUB_API_KEY") or os.getenv("FINNHUB_TOKEN")
    if not key:
        return None
    s = _session()
    out = None

    # Try NSE-qualified first for .NS tickers, else raw
    candidates = [f"NSE:{symbol[:-3]}", symbol] if symbol.endswith(".NS") else [symbol]
    for sym in candidates:
        try:
            r = s.get(
                "https://finnhub.io/api/v1/stock/metric",
                params={"symbol": sym, "metric": "all", "token": key},
                timeout=REQ_TIMEOUT,
            )
            if not r.ok:
                continue
            m = (r.json() or {}).get("metric") or {}
            tmp = {}

            # --- P/E ---
            pe = _to_float(m.get("peTTM") or m.get("peExclExtraTTM"))
            if pe is None:
                ey = _to_float(m.get("earningsYieldTTM"))  # 0.0304 -> P/E ~ 32.9
                if ey not in (None, 0):
                    pe = _safe_div(1.0, ey)
            tmp["pe"] = pe

            # --- ROE ---
            roe = _to_float(m.get("roeTTM") or m.get("returnOnEquityTTM"))
            if roe is not None and roe > 2:  # looks like %, convert to fraction
                roe = roe / 100.0
            tmp["roe"] = _pct(roe) if roe is not None else None  # store as %

            # --- D/E ---
            de = _to_float(
                m.get("debtToEquityAnnual")
                or m.get("debtToEquityTTM")
                or m.get("totalDebt/totalEquityAnnual")
            )
            tmp["de"] = de

            # --- Revenue CAGR ---
            rc = _to_float(
                m.get("revenueCagr3Y")
                or m.get("revenueCagr5Y")
                or m.get("salesCAGR5Y")
            )
            if rc is not None and rc > 2:  # looks like %, convert to fraction
                rc = rc / 100.0
            tmp["rev_cagr"] = _pct(rc) if rc is not None else None  # %

            if any(v is not None for v in tmp.values()):
                out = tmp
                break
        except Exception:
            pass

    return out

# ---------- FMP ----------
def _from_fmp(symbol):
    key = os.getenv("FMP_API_KEY")
    if not key: return None
    base = "https://financialmodelingprep.com/api/v3"
    out, sess = {}, _session()

    try:
        r = sess.get(f"{base}/profile/{symbol}", params={"apikey": key}, timeout=REQ_TIMEOUT)
        if r.ok:
            prof = r.json()
            if isinstance(prof, list) and prof:
                out["pe"] = _to_float(prof[0].get("pe"))
    except Exception:
        pass

    inc = bal = None
    try:
        r = sess.get(f"{base}/income-statement/{symbol}",
                     params={"period":"annual","limit":5,"apikey":key}, timeout=REQ_TIMEOUT)
        if r.ok: inc = r.json()
    except Exception: pass

    try:
        r = sess.get(f"{base}/balance-sheet-statement/{symbol}",
                     params={"period":"annual","limit":5,"apikey":key}, timeout=REQ_TIMEOUT)
        if r.ok: bal = r.json()
    except Exception: pass

    if not inc or not isinstance(inc, list): return out or None

    try:
        net_income = _to_float(inc[0].get("netIncome"))
        if bal and isinstance(bal, list) and bal:
            equity = _to_float(bal[0].get("totalStockholdersEquity"))
            total_debt = _to_float(bal[0].get("totalDebt"))
            out["roe"] = _pct(_safe_div(net_income, equity))
            out["de"]  = _safe_div(total_debt, equity)
        revs = [_to_float(row.get("revenue")) for row in inc[:5]]
        out["rev_cagr"] = _pct(_revenue_cagr(revs))
    except Exception:
        pass

    return out or None

# ---------- Alpha Vantage ----------
def _from_av(symbol):
    key = os.getenv("ALPHAVANTAGE_API_KEY")
    if not key: return None
    out, sess = {}, _session()

    try:
        r = sess.get("https://www.alphavantage.co/query",
                     params={"function":"OVERVIEW","symbol":symbol,"apikey":key},
                     timeout=REQ_TIMEOUT)
        if r.ok:
            ov = r.json()
            if isinstance(ov, dict) and "Note" not in ov:
                out["pe"] = _to_float(ov.get("PERatio"))
                net_income = _to_float(ov.get("NetIncomeTTM"))
                book_value_ps = _to_float(ov.get("BookValue"))
                shares = _to_float(ov.get("SharesOutstanding"))
                equity_total = book_value_ps * shares if (book_value_ps and shares) else None
                out["roe"] = _pct(_safe_div(net_income, equity_total)) if equity_total else None
    except Exception: pass

    try:
        r = sess.get("https://www.alphavantage.co/query",
                     params={"function":"INCOME_STATEMENT","symbol":symbol,"apikey":key},
                     timeout=REQ_TIMEOUT)
        if r.ok:
            js = r.json()
            ann = js.get("annualReports", []) if isinstance(js, dict) else []
            revs = [_to_float(x.get("totalRevenue")) for x in ann[:5]]
            if revs:
                out["rev_cagr"] = _pct(_revenue_cagr(revs))
    except Exception: pass

    return out or None

# ---------- yfinance (no .info) ----------
def _from_yf(symbol):
    out = {}
    try:
        t = yf.Ticker(symbol)

        # Last price: try multiple periods, then fast_info
        price = None
        for per in YF_HISTORY_PERIODS:
            try:
                h = t.history(period=per)
                if len(h):
                    price = float(h["Close"].iloc[-1])
                    break
            except Exception:
                pass
        if price is None:
            try:
                fi = getattr(t, "fast_info", None)
                if fi:
                    price = float(fi.get("last_price") or fi.get("last_close") or fi.get("previous_close"))
            except Exception:
                pass

        # Financial statements
        inc = getattr(t, "income_stmt", None) or getattr(t, "financials", None)
        bal = getattr(t, "balance_sheet", None)

        def _find_row(df, names):
            if df is None or df.empty: return None
            idx = {str(i).lower(): i for i in df.index}
            for nm in names:
                key = nm.lower()
                if key in idx: return df.loc[idx[key]]
            for i in df.index:
                s = str(i).lower()
                if any(n.lower() in s for n in names): return df.loc[i]
            return None

        def _latest(series):
            if series is None: return None
            try: return _to_float(series.dropna().iloc[0])
            except Exception: return None

        # Net income & revenues
        ni_row = _find_row(inc, ["Net Income", "NetIncome"])
        net_income = _latest(ni_row)

        rev_row = _find_row(inc, ["Total Revenue", "Revenue"])
        if isinstance(rev_row, pd.Series):
            revs = [_to_float(v) for v in rev_row.values[:5]]
            out["rev_cagr"] = _pct(_revenue_cagr(revs))

        # Equity & Debt
        eq_row = _find_row(bal, ["Total Stockholder Equity", "Total Shareholder Equity", "Total Equity"])
        debt_row = _find_row(bal, ["Total Debt", "Long Term Debt"])
        equity = _latest(eq_row)
        debt = _latest(debt_row)
        out["de"] = _safe_div(debt, equity) if (debt is not None and equity not in (None, 0)) else None
        out["roe"] = _pct(_safe_div(net_income, equity))

        # P/E via EPS ≈ NetIncome / SharesOutstanding
        shares = None
        try:
            sh = t.get_shares_full()
            if sh is not None and not sh.empty:
                shares = float(sh["Shares (Basic)"].dropna().iloc[-1]) if "Shares (Basic)" in sh else float(sh.iloc[-1, 0])
        except Exception:
            pass
        eps = _safe_div(net_income, shares) if (net_income is not None and shares) else None
        out["pe"] = _safe_div(price, eps) if (price is not None and eps not in (None, 0)) else None

        return out
    except Exception:
        return None

# ---------- public ----------
def get_fundamentals(symbol: str, peer_pe: float | None = None) -> dict:
    res = {
        "P/E": None,
        "Peer P/E": peer_pe,
        "ROE (%)": None,
        "D/E": None,
        "Revenue CAGR (%)": None,
        "P/E discount vs peer (%)": None,
    }

    # 1) NSE P/E for .NS tickers (fast win)
    if symbol.endswith(".NS"):
        pe = _nse_pe(symbol[:-3])
        if pe is not None:
            res["P/E"] = pe

    # 1.5) Finnhub fill (great coverage incl. NSE)
    fh = _from_finnhub(symbol)
    if fh:
        for src, dst in [("pe","P/E"), ("roe","ROE (%)"), ("de","D/E"), ("rev_cagr","Revenue CAGR (%)")]:
            if res[dst] is None and fh.get(src) is not None:
                res[dst] = fh[src]

    # 2) FMP
    f = _from_fmp(symbol)
    if f:
        res["P/E"] = res["P/E"] if res["P/E"] is not None else f.get("pe")
        res["ROE (%)"] = f.get("roe", res["ROE (%)"])
        res["D/E"] = f.get("de", res["D/E"])
        res["Revenue CAGR (%)"] = f.get("rev_cagr", res["Revenue CAGR (%)"])

    # 3) Alpha Vantage
    a = _from_av(symbol)
    if a:
        if res["P/E"] is None and a.get("pe") is not None: res["P/E"] = a["pe"]
        if res["ROE (%)"] is None and a.get("roe") is not None: res["ROE (%)"] = a["roe"]
        if res["Revenue CAGR (%)"] is None and a.get("rev_cagr") is not None: res["Revenue CAGR (%)"] = a["rev_cagr"]

    # 4) yfinance fallback
    if any(res[k] is None for k in ["P/E", "ROE (%)", "D/E", "Revenue CAGR (%)"]):
        y = _from_yf(symbol)
        if y:
            for k_src, k_dst in [("pe","P/E"), ("roe","ROE (%)"), ("de","D/E"), ("rev_cagr","Revenue CAGR (%)")]:
                if res[k_dst] is None and y.get(k_src) is not None:
                    res[k_dst] = y[k_src]

    # 5) P/E discount vs peer
    if res["P/E"] is not None and res["Peer P/E"] not in (None, 0):
        res["P/E discount vs peer (%)"] = _pct(1 - (res["P/E"] / res["Peer P/E"]))

    # Round for UI
    for k in res:
        if k.endswith("(%)") or k in ("P/E", "D/E", "Peer P/E"):
            res[k] = _round(res[k])

    return res

# ---------- scoring ----------
def score_fundamentals(arg, weights=None, peer_pe=None, return_details=False):
    """
    Flexible scorer.
    - If `arg` is a dict (output of get_fundamentals), it is scored directly.
    - If `arg` is a symbol string, we call get_fundamentals(arg, peer_pe) first.
    Always returns (score, details_dict).
    """
    # 1) load weights
    if weights is None:
        cfg = load_config() or {}
        weights = (cfg.get("valuation_weights") or {})
    w_pe  = float(weights.get("pe_under_peer_bonus", 0.15))
    w_roe = float(weights.get("roe_bonus", 0.10))

    # 2) resolve fundamentals
    if isinstance(arg, str):
        fund = get_fundamentals(arg, peer_pe=peer_pe)
    elif isinstance(arg, dict):
        fund = arg
    else:
        fund = {}

    # helpers
    def _to_frac(pct):
        try:
            return float(pct) / 100.0
        except Exception:
            return None

    # 3) components
    score = 0.0
    components = {}

    # P/E discount vs peer → [-w_pe, +w_pe]
    pe_disc_frac = _to_frac(fund.get("P/E discount vs peer (%)"))
    if pe_disc_frac is not None:
        pe_component = max(-1.0, min(1.0, pe_disc_frac)) * w_pe
        score += pe_component
        components["pe_under_peer"] = round(pe_component, 4)
    else:
        components["pe_under_peer"] = 0.0

    # ROE bonus: bucketed scaling
    roe_frac = _to_frac(fund.get("ROE (%)"))
    roe_scale = 0.0
    if roe_frac is not None:
        roe_pct = roe_frac * 100.0
        if roe_pct >= 20: roe_scale = 1.0
        elif roe_pct >= 15: roe_scale = 0.75
        elif roe_pct >= 10: roe_scale = 0.50
        elif roe_pct >= 5:  roe_scale = 0.25
        else: roe_scale = 0.0
    roe_component = roe_scale * w_roe
    score += roe_component
    components["roe"] = round(roe_component, 4)

    # 4) final
    final_score = round(float(score), 4)
    details = {
        "components": components,
        "weights": {"pe": w_pe, "roe": w_roe},
        "fundamentals": fund,
    }
    return final_score, details
