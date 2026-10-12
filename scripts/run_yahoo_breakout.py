"""Yahoo Finance OHLCV-only screen and historical four-strategy backtest.

Yahoo OHLCV does not include foreign/institution net buying: these filters are
intentionally omitted and outputs must not be described as Kiwoom-exact.
"""
import ast
import json
import os
import time
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "1_신고가_4전략.py"
tree = ast.parse(PAGE.read_text(encoding="utf-8"))
functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "simulate"]
namespace = {"pd": pd, "np": np}
exec(compile(ast.Module(body=functions, type_ignores=[]), str(PAGE), "exec"), namespace)
simulate = namespace["simulate"]

SYMBOLS = {
    "005930.KS": "삼성전자",
    "000660.KS": "SK하이닉스",
    "005380.KS": "현대차",
    "035420.KS": "NAVER",
    "005490.KS": "POSCO홀딩스",
    "051910.KS": "LG화학",
    "068270.KS": "셀트리온",
    "006400.KS": "삼성SDI",
    "012330.KS": "현대모비스",
    "055550.KS": "신한지주",
}
START = os.environ.get("BT_START", "2020-01-01")
END = os.environ.get("BT_END", "2026-09-30")
REPORT = ROOT / "reports" / "yahoo_breakout"
REPORT.mkdir(parents=True, exist_ok=True)


def get_history(ticker):
    for attempt in range(1, 4):
        try:
            raw = yf.download(
                ticker, start="2019-06-01",
                end=(pd.Timestamp(END) + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                auto_adjust=False, progress=False, threads=False,
                multi_level_index=False, timeout=25,
            )
            if raw is None or raw.empty:
                raise RuntimeError("empty Yahoo response")
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            needed = ["Open", "High", "Low", "Close", "Volume"]
            if any(c not in raw.columns for c in needed):
                raise RuntimeError(f"missing columns: {list(raw.columns)}")
            d = raw[needed].rename(columns=str.lower).sort_index()
            d.index = pd.to_datetime(d.index).tz_localize(None)
            d = d.dropna(subset=["open", "high", "low", "close", "volume"])
            if len(d) < 90:
                raise RuntimeError(f"insufficient bars: {len(d)}")
            if (d[["open", "high", "low", "close"]] <= 0).any().any():
                raise RuntimeError("nonpositive prices")
            return d
        except Exception as exc:
            print(f"{ticker} attempt {attempt}/3: {type(exc).__name__}: {exc}", flush=True)
            if attempt == 3:
                raise
            time.sleep(3 * attempt)


def screen(d):
    d = d.copy()
    # Raw unadjusted OHLC and volume for KRW turnover threshold.
    d["prior_high60"] = d.high.shift(1).rolling(60).max()
    d["prior_vol60"] = d.volume.shift(1).rolling(60).mean()
    d["ma20"] = d.close.rolling(20).mean()
    d["turnover"] = d.close * d.volume
    d["signal"] = (
        (d.volume >= 1_000_000)
        & (d.close > d.prior_high60)
        & (d.volume >= 5 * d.prior_vol60)
        & (d.turnover >= 2_000_000_000)
    ).fillna(False)
    return d


def run():
    data, latest, errors = {}, [], {}
    for ticker, name in SYMBOLS.items():
        try:
            d = screen(get_history(ticker))
            d = d.loc[START:END]
            if d.empty:
                raise RuntimeError("no rows in requested period")
            data[ticker] = d
            last = d.iloc[-1]
            latest.append({
                "ticker": ticker, "name": name, "date": d.index[-1].date(),
                "close_krw": last.close, "volume": int(last.volume),
                "volume_multiple": last.volume / last.prior_vol60
                if pd.notna(last.prior_vol60) and last.prior_vol60 > 0 else np.nan,
                "prior_60d_high": last.prior_high60,
                "turnover_krw": last.turnover,
                "signal": bool(last.signal),
            })
            print(f"{ticker}: {len(d)} rows; signals={int(d.signal.sum())}", flush=True)
        except Exception as exc:
            errors[ticker] = f"{type(exc).__name__}: {exc}"
            print(f"{ticker}: FAILED {errors[ticker]}", flush=True)
    (REPORT / "fetch_errors.json").write_text(
        json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if not data:
        raise RuntimeError("Yahoo returned no usable symbols; cannot produce backtest")
    pd.DataFrame(latest).to_csv(REPORT / "latest_screen.csv", index=False, encoding="utf-8-sig")
    all_signals = []
    for ticker, d in data.items():
        hits = d.loc[d.signal, ["close", "volume", "turnover", "prior_high60"]].copy()
        hits.insert(0, "ticker", ticker)
        hits.index.name = "signal_date"
        all_signals.append(hits.reset_index())
    pd.concat(all_signals, ignore_index=True).to_csv(
        REPORT / "historical_signals.csv", index=False, encoding="utf-8-sig"
    )
    metrics = []
    yearly_equity = []
    monthly_equity = []
    for mode in ("당일", "5일", "20일", "추세"):
        m, trades, eq = simulate(data, mode, 10_000_000, 2_000_000, 0.001, 0.001)
        metrics.append(m)
        trades.to_csv(REPORT / f"trades_{mode}.csv", index=False, encoding="utf-8-sig")
        if not trades.empty:
            trades = trades.copy()
            trades["매도일"] = pd.to_datetime(trades["매도일"])
            trades["연도"] = trades["매도일"].dt.year
            trades["월"] = trades["매도일"].dt.to_period("M").astype(str)
            for period, col in (("annual", "연도"), ("monthly", "월")):
                summary = trades.groupby(col, as_index=False).agg(
                    거래건수=("손익", "size"), 실현손익_원=("손익", "sum"),
                    승리건수=("손익", lambda x: int((x > 0).sum())))
                summary["승률"] = summary["승리건수"] / summary["거래건수"]
                summary.to_csv(REPORT / f"{period}_{mode}.csv",
                               index=False, encoding="utf-8-sig")
        else:
            for period in ("annual", "monthly"):
                pd.DataFrame(columns=["기간", "거래건수", "실현손익_원", "승리건수", "승률"]).to_csv(
                    REPORT / f"{period}_{mode}.csv", index=False, encoding="utf-8-sig")
        eq.rename("equity").to_csv(REPORT / f"equity_{mode}.csv", encoding="utf-8-sig")
        # Calendar-period account returns include open positions and cash.
        for frequency, output in (("YE", yearly_equity), ("ME", monthly_equity)):
            checkpoints = eq.resample(frequency).last()
            if checkpoints.empty:
                continue
            previous = pd.concat([pd.Series([10_000_000.0]), checkpoints.iloc[:-1].reset_index(drop=True)], ignore_index=True)
            for dt, ending, beginning in zip(checkpoints.index, checkpoints.values, previous.values):
                output.append({"전략":mode, "기간":dt.strftime("%Y" if frequency=="YE" else "%Y-%m"),
                               "기초자산_원":round(float(beginning)),
                               "기말자산_원":round(float(ending)),
                               "기간손익_원":round(float(ending-beginning)),
                               "기간수익률":float(ending/beginning-1) if beginning>0 else float("nan")})
        # Equity changes include unrealized P/L and transaction costs.
        for freq, label in (("ME", "monthly"), ("YE", "yearly")):
            period_end = eq.resample(freq).last().dropna()
            previous = period_end.shift(1)
            if not previous.empty:
                previous.iloc[0] = 10_000_000
            period = pd.DataFrame({
                "기간": period_end.index.strftime("%Y-%m" if label=="monthly" else "%Y"),
                "기간초자산": previous.values,
                "기간말자산": period_end.values,
                "기간손익": (period_end-previous).values,
                "기간수익률": (period_end/previous-1).values,
            })
            period.to_csv(REPORT / f"{label}_pnl_{mode}.csv",index=False,encoding="utf-8-sig")
        if not trades.empty:
            realized = trades.copy()
            realized["매도월"] = pd.to_datetime(realized["매도일"]).dt.strftime("%Y-%m")
            realized["매도연도"] = pd.to_datetime(realized["매도일"]).dt.strftime("%Y")
            for group, label in (("매도월","monthly"),("매도연도","yearly")):
                realized.groupby(group,as_index=False).agg(
                    청산거래수=("손익","size"),
                    실현손익=("손익","sum"),
                    승리거래수=("손익",lambda x:int((x>0).sum())),
                ).to_csv(REPORT/f"{label}_realized_{mode}.csv",index=False,encoding="utf-8-sig")
    pd.DataFrame(metrics).to_csv(REPORT / "comparison.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(yearly_equity).to_csv(REPORT / "annual_account_returns.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(monthly_equity).to_csv(REPORT / "monthly_account_returns.csv", index=False, encoding="utf-8-sig")
    (REPORT / "methodology.json").write_text(json.dumps({
        "provider": "Yahoo Finance via yfinance",
        "start": START, "end": END,
        "requested_universe": list(SYMBOLS), "analyzed_universe": list(data),
        "excluded_universe": errors,
        "foreign_institution_filters": "NOT AVAILABLE: OMITTED",
        "signal": "Close > previous 60-day intraday high; volume >= 5x previous 60-day average; volume >= 1m; close*volume >= 2bn KRW",
        "prices": "unadjusted OHLC; stock splits/dividends may distort multi-year results",
        "cautions": ["not the exact Kiwoom strategy", "survivorship bias: present-day selected tickers",
                    "only selected 10 stocks, not full KOSPI", "entry-day stops not modeled",
                    "same-bar stop/take-profit order unknown", "excludes symbols with failed downloads"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(pd.DataFrame(metrics).to_string(index=False), flush=True)


if __name__ == "__main__":
    run()
