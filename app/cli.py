import argparse
import pandas as pd
from .providers import us_history, kr_history, benchmark_history
from .scoring import score_symbol

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--market", choices=["US", "KR"], required=True)
    p.add_argument("--symbols", nargs="+", required=True)
    p.add_argument("--csv", default=None)
    args = p.parse_args()

    bench = benchmark_history(args.market)
    rows = []
    for s in args.symbols:
        try:
            df = us_history(s) if args.market == "US" else kr_history(s)
            r = score_symbol(df, bench)
            rows.append({"symbol": s, **r})
        except Exception as e:
            rows.append({"symbol": s, "score": 0, "signal": "ERROR", "error": str(e)})

    out = pd.DataFrame(rows).sort_values("score", ascending=False)
    cols = ["symbol", "score", "signal", "market_regime", "close", "atr20", "suggested_initial_stop",
            "52w_high_distance", "volume_ratio"]
    print(out[[c for c in cols if c in out.columns]].to_string(index=False))
    if args.csv:
        out.to_csv(args.csv, index=False, encoding="utf-8-sig")
        print(f"saved: {args.csv}")

if __name__ == "__main__":
    main()
