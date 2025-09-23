
# src/ipobot/app/cli.py

# --- fix imports when run directly ---
import sys, pathlib
SRC = pathlib.Path(__file__).resolve().parents[2]  # .../src
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
# --------------------------------------

from ipobot.pipeline import run_pipeline
from ipobot.data.lookup import resolve_symbol


def run(symbol: str, query: str):
    """Run IPOBot with a known symbol & query."""
    return run_pipeline(symbol, query)


def run_name(ipo_name: str):
    """Run IPOBot by just giving IPO name (will auto-resolve to symbol)."""
    symbol = resolve_symbol(ipo_name)
    if not symbol:
        raise SystemExit(f"❌ Unknown IPO name: {ipo_name}. Add it in data/lookup.py")
    query = f"{ipo_name} IPO latest news"
    return run_pipeline(symbol, query)


if __name__ == "__main__":
    import argparse, json
    p = argparse.ArgumentParser(description="IPOBot CLI")
    p.add_argument("--ipo_name", help="IPO name (e.g., OYO, LIC, Zomato)")
    p.add_argument("--symbol", help="Ticker symbol (if known)")
    p.add_argument("--query", help="Custom news query")
    args = p.parse_args()

    if args.ipo_name:
        result = run_name(args.ipo_name)
    elif args.symbol:
        q = args.query or f"{args.symbol} IPO latest news"
        result = run(args.symbol, q)
    else:
        raise SystemExit("❌ You must provide either --ipo_name or --symbol")

    print(json.dumps(result, indent=2, ensure_ascii=False))
