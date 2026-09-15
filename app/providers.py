from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf


def normalize_yahoo(df):
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna(subset=["Close"])


def us_history(symbol, period="3y"):
    return normalize_yahoo(yf.download(symbol, period=period, auto_adjust=True, progress=False))


def _period_to_lookback_days(period):
    """Parse the simple '<N><unit>' periods used in this project ('3y', '6m', '90d')."""
    try:
        unit = period[-1].lower()
        n = int(period[:-1])
    except (ValueError, IndexError):
        return 365 * 3
    if unit == "y":
        return n * 365
    if unit == "m":
        return n * 30
    if unit == "d":
        return n
    return 365 * 3


def kr_history(symbol, period="3y"):
    """Fetch Korean OHLCV via pykrx, keyed on the raw 6-digit KRX code.

    The previous implementation guessed a Yahoo Finance suffix (always
    ".KS", i.e. KOSPI) for Korean tickers. That silently breaks for every
    KOSDAQ-listed symbol (which needs ".KQ"), and Yahoo's Korea coverage is
    also less complete/reliable than KRX's own data. pykrx takes the bare
    ticker and resolves it against the real KRX market data regardless of
    which board (KOSPI/KOSDAQ) it trades on, so no suffix guessing is
    needed at all.
    """
    from pykrx import stock

    ticker = symbol.split(".")[0]  # tolerate an old-style "005930.KS" input too
    days = _period_to_lookback_days(period)
    end = datetime.today()
    start = end - timedelta(days=days + 15)  # pad for non-trading days

    raw = stock.get_market_ohlcv_by_date(
        start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), ticker, adjusted=True
    )
    if raw is None or raw.empty:
        return pd.DataFrame()

    df = raw.rename(columns={
        "시가": "Open", "고가": "High", "저가": "Low",
        "종가": "Close", "거래량": "Volume",
    })
    keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
    df = df[keep].dropna(subset=["Close"])
    df.index = pd.to_datetime(df.index)
    return df


def benchmark_history(market):
    return us_history("SPY") if market == "US" else kr_history("069500")
