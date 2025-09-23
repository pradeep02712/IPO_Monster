
import argparse, json
from .pipeline import run_pipeline

def main():
    p = argparse.ArgumentParser(description="IPOBot CLI")
    p.add_argument("--symbol", required=True, help="IPO symbol or ticker code")
    p.add_argument("--query", required=True, help="News search query")
    args = p.parse_args()

    result = run_pipeline(args.symbol, args.query)
    print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
