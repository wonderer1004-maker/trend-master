from .indicators import sma, atr, breakout, volume_ratio, high_52w_distance, rs_ratio, stage2_features

MIN_MARKET_BARS = 171  # 150dma + 21 bars of history to check its slope


def market_regime(benchmark):
    """Classify the market environment from the benchmark index alone.

    Returns (regime, score_0_to_20, reasons). regime is one of
    BULL / NEUTRAL / BEAR / UNKNOWN (UNKNOWN when no usable benchmark
    history was supplied -- callers should not silently treat that as BULL).
    """
    if benchmark is None or len(benchmark) < MIN_MARKET_BARS:
        return "UNKNOWN", 0, []

    bclose = benchmark["Close"]
    bma150 = sma(bclose, 150)
    above = bool(bclose.iloc[-1] > bma150.iloc[-1])
    rising = bool(bma150.iloc[-1] > bma150.iloc[-21])

    score = (10 if above else 0) + (10 if rising else 0)
    reasons = []
    if above:
        reasons.append("market_index_above_150dma")
    if rising:
        reasons.append("market_150dma_rising")

    if above and rising:
        regime = "BULL"
    elif not above and not rising:
        regime = "BEAR"
    else:
        regime = "NEUTRAL"
    return regime, score, reasons


def score_symbol(df, benchmark=None):
    if len(df) < 260:
        return {"score": 0, "signal": "INSUFFICIENT_DATA"}

    close = df["Close"]
    ma50 = sma(close, 50)
    ma150 = sma(close, 150)
    f = stage2_features(df)

    reasons = []
    detail = {}

    # 0) Market environment (Section 7 of the spec): 20 points.
    # This bucket was missing from the original implementation, which meant
    # 90+/STRONG_BUY_CANDIDATE could never be reached (max score capped at 80).
    regime, market_score, market_reasons = market_regime(benchmark)
    detail["market"] = market_score
    reasons.extend(market_reasons)
    if regime == "UNKNOWN":
        detail["market_status"] = "benchmark_missing_or_insufficient"

    # 1) Weinstein Stage 2 (~30-week / 150-day MA): 20
    weinstein_score = (10 if f["above_ma30w"] else 0) + (10 if f["ma30w_rising"] else 0)
    if f["above_ma30w"]:
        reasons.append("price_above_30week_ma")
    if f["ma30w_rising"]:
        reasons.append("30week_ma_rising")
    detail["weinstein"] = weinstein_score

    # 2) Livermore/Turtle breakout: 20
    b20 = bool(breakout(df, 20).iloc[-1])
    b55 = bool(breakout(df, 55).iloc[-1])
    d52 = float(high_52w_distance(df).iloc[-1])
    breakout_score = (5 if b20 else 0) + (5 if b55 else 0) + (5 if d52 >= .95 else 0) + (5 if (b20 or b55) else 0)
    if b20 or b55:
        reasons.append("breakout")
    if d52 >= 0.95:
        reasons.append("within_5pct_of_52w_high")
    detail["breakout"] = breakout_score

    # 3) O'Neil / Minervini trend alignment: 20
    above_50 = close.iloc[-1] > ma50.iloc[-1]
    ma50_above_150 = ma50.iloc[-1] > ma150.iloc[-1]
    ma150_rising = ma150.iloc[-1] > ma150.iloc[-21]
    near_52w_high = d52 >= .90
    quality_score = sum([5 if above_50 else 0, 5 if ma50_above_150 else 0,
                         5 if ma150_rising else 0, 5 if near_52w_high else 0])
    if above_50:
        reasons.append("above_50dma")
    if ma50_above_150:
        reasons.append("50dma_above_150dma")
    if ma150_rising:
        reasons.append("150dma_rising")
    if near_52w_high:
        reasons.append("near_52w_high")
    detail["quality"] = quality_score

    # 4) Volume / relative strength: 20
    vr = float(volume_ratio(df).iloc[-1])
    vr_score = (5 if vr >= 1.5 else 0) + (5 if vr >= 2.0 else 0)
    if vr >= 1.5:
        reasons.append("volume_1_5x")
    if vr >= 2.0:
        reasons.append("volume_2x")
    if benchmark is not None and len(benchmark) >= 260:
        rs = rs_ratio(df, benchmark).iloc[-1]
        if rs > 1.0:
            vr_score += 5
            reasons.append("relative_strength_above_1")
        if rs > 1.05:
            vr_score += 5
            reasons.append("relative_strength_strong")
    else:
        # Do not fake RS if benchmark data is unavailable.
        detail["rs_status"] = "benchmark_missing"
    detail["volume_relative_strength"] = vr_score

    score = market_score + weinstein_score + breakout_score + quality_score + vr_score

    a = float(atr(df).iloc[-1])
    entry = float(close.iloc[-1])
    stop = entry - 2.0 * a
    risk_pct = max(0.0, (entry - stop) / entry)

    if score >= 90:
        signal = "STRONG_BUY_CANDIDATE"
    elif score >= 80:
        signal = "BUY_CANDIDATE"
    elif score >= 70:
        signal = "READY"
    elif score >= 60:
        signal = "WATCH"
    else:
        signal = "AVOID"

    # Section 2 / Section 7 absolute rule: a bad market regime must strongly
    # restrict new-buy signals, not just nudge the score. BEAR blocks new buy
    # candidates outright; NEUTRAL halves conviction by capping STRONG_BUY.
    buy_signals = ("STRONG_BUY_CANDIDATE", "BUY_CANDIDATE", "READY")
    if regime == "BEAR" and signal in buy_signals:
        reasons.append(f"signal_capped_by_market_regime:{regime}")
        signal = "WATCH"
    elif regime == "NEUTRAL" and signal == "STRONG_BUY_CANDIDATE":
        reasons.append(f"signal_capped_by_market_regime:{regime}")
        signal = "BUY_CANDIDATE"

    return {
        "score": int(min(score, 100)),
        "signal": signal,
        "market_regime": regime,
        "close": round(entry, 4),
        "atr20": round(a, 4),
        "suggested_initial_stop": round(stop, 4),
        "52w_high_distance": round(d52, 4),
        "volume_ratio": round(vr, 2),
        "reasons": reasons,
        "detail": detail,
    }
