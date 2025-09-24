# IPOMONSTER

Personal-use prototype to analyze IPOs: aggregate news, compute fundamentals, run sentiment, and output a Buy/Hold/Avoid decision with reasoning.



## Quickstart

```bash
# 1) (Optional) create venv, then install deps
pip install -r requirements.txt

# 2) Train a tiny demo model (synthetic features -> label)
python -m ipobot.scripts.train_demo

# 3) Run CLI
python -m ipobot --symbol ABC --query "ABC IPO latest news"

# 4) (Optional) Run Streamlit UI
streamlit run src/ipobot/app/streamlit_app.py
```



## Architecture (ASCII)

┌────────────────────┐
│   User Interface   │ ← CLI / Streamlit
└────────┬───────────┘
         │
         ▼
┌─────────────────────────────┐
│       IPOBot Engine         │
├─────────────────────────────┤
│ 1) Data Collector           │
│    • News (APIs/Web)        │
│    • Financial APIs/DRHP    │
│    • Peer data              │
├─────────────────────────────┤
│ 2) NLP Sentiment            │
│    • FinBERT (optional)     │
│    • Rule-based fallback    │
├─────────────────────────────┤
│ 3) Fundamentals             │
│    • Ratios + Scores        │
│    • Peer comparison        │
├─────────────────────────────┤
│ 4) Prediction               │
│    • Demo RF/XGBoost        │
│    • Gain prob, % estimate  │
├─────────────────────────────┤
│ 5) Reasoning                │
│    • Human-readable why     │
├─────────────────────────────┤
│ 6) Automation (future)      │
│    • Scheduler + Notifier   │
└─────────────────────────────┘
         │
         ▼
   Buy/Hold/Avoid + Why


## Legal

Not investment advice. Use for personal research only.
