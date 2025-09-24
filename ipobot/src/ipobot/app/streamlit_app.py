
import sys, pathlib
SRC = pathlib.Path(__file__).resolve().parents[2] 
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import json
import re
import streamlit as st

from ipobot.pipeline import run_pipeline
from ipobot.data.lookup import resolve_symbol, suggest_symbol
from ipobot.data.ipo_calendar import fetch_upcoming_ipos

st.set_page_config(page_title="IPOBot (IPOMONSTER)", page_icon="📈", layout="wide")

st.title("IPOBot — Personal Prototype")
st.caption("Type an IPO name or pick from 'Upcoming IPOs'. I’ll fetch news, run sentiment + fundamentals, and recommend Buy/Hold/Avoid.")


st.sidebar.header("⚙️ Thresholds")
buy_thr = st.sidebar.slider("Buy threshold (prob)", 0.50, 0.90, 0.62, 0.01)
hold_thr = st.sidebar.slider("Hold threshold (prob)", 0.30, buy_thr, 0.45, 0.01)

def decide(prob: float, buy_t: float, hold_t: float):
    if prob >= buy_t:
        return "BUY"
    if prob >= hold_t:
        return "HOLD"
    return "AVOID"


_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9\-\.]{0,9}$")  

def looks_like_ticker(s: str) -> bool:
    """Treat raw input as a ticker if it's clearly a ticker (keeps TSLA/AAPL/RELIANCE.NS as-is)."""
    if not s:
        return False
    s = s.strip()
    
    if "." in s or ":" in s:
        return True
    
    return bool(_TICKER_RE.match(s.upper()))

def normalize_fundamentals(f: dict) -> dict:
    """Accept either UI-style keys ('P/E', 'ROE (%)', …) or code-style keys ('pe','roe', …)."""
    f = f or {}

    def pick(*keys):
        for k in keys:
            if k in f and f[k] is not None:
                return f[k]
        return None

    out = {
        "P/E": pick("P/E", "pe"),
        "Peer P/E": pick("Peer P/E", "peer_pe"),
        "ROE (%)": pick("ROE (%)", "roe", "roe_pct"),
        "D/E": pick("D/E", "de", "debt_to_equity"),
        "Revenue CAGR (%)": pick("Revenue CAGR (%)", "revenue_cagr", "rev_cagr", "rev_cagr_pct"),
        "P/E discount vs peer (%)": pick("P/E discount vs peer (%)", "pe_discount_vs_peer"),
    }

    
    d = out["P/E discount vs peer (%)"]
    try:
        if d is not None:
            d = float(d)
            out["P/E discount vs peer (%)"] = round(d * 100, 2) if abs(d) <= 1 else round(d, 2)
    except Exception:
        pass

   
    for k, v in list(out.items()):
        try:
            if v is not None:
                out[k] = round(float(v), 2)
        except Exception:
            pass
    return out

def format_peer_gap(pe: float | None, peer: float | None):
    """Return (label, value) where label is 'discount' or 'premium' vs peer."""
    try:
        if pe in (None, 0) or peer in (None, 0):
            return None, None
        frac = 1 - (float(pe) / float(peer)) 
        pct = round(frac * 100, 2)
        label = "P/E discount vs peer" if pct >= 0 else "P/E premium vs peer"
        return label, abs(pct)
    except Exception:
        return None, None


st.subheader("🔎 Quick analyze by IPO name")
ipo_name = st.text_input("IPO name or ticker", placeholder="e.g., OYO, LICI.NS, Zomato, TSLA, AAPL").strip()
colA, colB = st.columns([1, 3])
run_click = colA.button("🚀 Analyze")

if run_click:
    raw = ipo_name
    sym = None
    learned = False

    
    if looks_like_ticker(raw):
        sym = raw.upper()
    else:
        sym, learned = resolve_symbol(raw)

    if sym is None:
        sym = suggest_symbol(raw)
        st.warning(f"Symbol not found in mappings or APIs. Using fallback: {sym}")
    elif learned:
        st.success(f"Learned mapping: {raw} → {sym}")

    st.info(f"Using symbol: **{sym}**")

    query = f"{raw} IPO latest news"
    with st.spinner(f"Analyzing {raw} ({sym})…"):
        res = run_pipeline(
            sym,
            query,
            override_thresholds={"buy_prob": buy_thr, "hold_prob": hold_thr},
        )

    prob = float(res["probability"])
    res["decision"] = decide(prob, buy_thr, hold_thr)

    # KPI row
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Decision", res["decision"])
    k2.metric("Gain Probability", f"{prob:.2f}")
    k3.metric("Expected Gain %", f"{res['expected_gain_pct']:.1f}%")
    k4.metric("News Sentiment", f"{float(res.get('sentiment',0)):+.2f}")

    st.divider()

   
    left, right = st.columns([1.3, 1])
    with left:
        st.subheader("🧠 Why")
        st.markdown(res["reasoning"])
        st.caption("Prototype explanation combining rules + model output.")
        st.download_button(
            "⬇️ Download result JSON",
            data=json.dumps(res, indent=2, ensure_ascii=False),
            file_name=f"ipobot_{sym}.json",
            mime="application/json",
            use_container_width=True
        )
    with right:
        st.subheader("📊 Fundamentals")
        f_ui = normalize_fundamentals(res.get("fundamentals", {}))

       
        gap_label, gap_val = format_peer_gap(f_ui.get("P/E"), f_ui.get("Peer P/E"))
        if gap_label is not None:
            f_ui[gap_label + " (%)"] = gap_val
            f_ui.pop("P/E discount vs peer (%)", None)

        st.write(f_ui)

    st.divider()
    st.subheader("📰 News snapshot")
    for n in res.get("news_sample", []):
        tone = (n.get("sent") or "neutral").capitalize()
        st.markdown(f"- **{n.get('title','(no title)')}** — _{tone}_")

    with st.expander("🔧 Debug Info"):
        st.json(res.get("meta", {}))
        st.write("Warnings:", res.get("warnings", []))
        st.write("Errors:", res.get("errors", []))


st.subheader("📅 Upcoming IPOs (auto-fetched)")
try:
    cal_items = fetch_upcoming_ipos()
except Exception as e:
    cal_items = []
    st.warning(f"Calendar fetch failed: {e}")

if not cal_items:
    st.caption("No calendar items fetched right now (or sources throttled). Try again later.")
else:
    choices = [
        f"{it.get('name','?')} — {it.get('open_date') or '?'} to {it.get('close_date') or '?'}"
        for it in cal_items
    ]
    sel = st.multiselect("Select IPOs to analyze", options=choices, max_selections=5)

    if st.button("🔎 Analyze selected IPOs"):
        for c in sel:
            idx = choices.index(c)
            it = cal_items[idx]
            ipo = it.get("name", "").strip()

            
            sym, learned = resolve_symbol(ipo)
            if sym is None:
                sym = it.get("symbol") or suggest_symbol(ipo)
                st.warning(f"[{ipo}] Symbol not found; using fallback: {sym}")
            elif learned:
                st.success(f"Learned mapping: {ipo} → {sym}")

            st.info(f"[{ipo}] Using symbol: **{sym}**")

            q = f"{ipo} IPO latest news"
            with st.spinner(f"Analyzing {ipo} ({sym})…"):
                res = run_pipeline(
                    sym,
                    query,
                    override_thresholds={"buy_prob": buy_thr, "hold_prob": hold_thr},
                    symbol_is_final=True,  
                )


            p = float(res["probability"])
            dec = decide(p, buy_thr, hold_thr)
            st.markdown(
                f"### {ipo}  \n**Decision:** {dec}  •  **Prob:** {p:.2f}  •  **Gain %:** {res['expected_gain_pct']:.1f}%"
            )
            st.markdown(res["reasoning"])
            with st.expander("Fundamentals / News / Debug"):
                st.json(res["fundamentals"])
                st.write("News:")
                for n in res.get("news_sample", []):
                    tone = (n.get("sent") or "neutral").capitalize()
                    st.markdown(f"- **{n.get('title','(no title)')}** — _{tone}_")
                st.write("Meta:", res.get("meta", {}))
                st.write("Warnings:", res.get("warnings", []))
                st.write("Errors:", res.get("errors", []))


with st.expander("✏️ Edit IPO name → symbol mappings"):
    st.write(
        "Auto-learned mappings are saved to `src/ipobot/data/mappings.json`.\n"
        "You can also hardcode seeds in `lookup.py` (NAME_TO_SYMBOL)."
    )
    st.code('NAME_TO_SYMBOL = {"oyo": "OYO.NS", "lic": "LICI.NS", "zomato": "ZOMATO.NS"}', language="python")
