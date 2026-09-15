import numpy as np
import pandas as pd

def sma(s, n):
    return s.rolling(n).mean()

def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()

def atr(df, n=20):
    h, l, c = df["High"], df["Low"], df["Close"]
    prev = c.shift(1)
    tr = pd.concat([(h-l), (h-prev).abs(), (l-prev).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def rs_ratio(df, benchmark):
    x = df["Close"] / benchmark["Close"]
    return x / x.rolling(50).mean()

def breakout(df, n):
    prior_high = df["High"].rolling(n).max().shift(1)
    return df["Close"] > prior_high

def volume_ratio(df, n=20):
    return df["Volume"] / df["Volume"].rolling(n).mean()

def high_52w_distance(df):
    high = df["High"].rolling(252).max()
    return df["Close"] / high

def stage2_features(df):
    ma30w = df["Close"].rolling(150).mean()
    return {
        "ma30w": ma30w.iloc[-1],
        "above_ma30w": bool(df["Close"].iloc[-1] > ma30w.iloc[-1]),
        "ma30w_rising": bool(ma30w.iloc[-1] > ma30w.iloc[-21]),
    }
