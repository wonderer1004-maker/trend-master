import pandas as pd
import numpy as np
from .indicators import atr
from .scoring import score_symbol


def run_breakout_backtest(df, initial_cash=10_000_000, risk_pct=0.01,
                          breakout_days=55, atr_mult=2.0,
                          fee_rate=0.00015, slippage=0.0005):
    """Long-only, next-bar execution backtest. Signal uses data through t; entry at t+1 open."""
    d = df.copy().dropna().copy()
    if len(d) < 300:
        return {"metrics": {}, "trades": pd.DataFrame(), "equity": pd.Series(dtype=float)}
    d['ATR'] = atr(d, 20)
    d['PriorHigh'] = d['High'].rolling(breakout_days).max().shift(1)
    d['MA50'] = d['Close'].rolling(50).mean()
    d['MA150'] = d['Close'].rolling(150).mean()
    d['MA150_up'] = d['MA150'] > d['MA150'].shift(21)
    d['MA50_above_150'] = d['MA50'] > d['MA150']
    d['Above50'] = d['Close'] > d['MA50']
    d['Signal'] = (d['Close'] > d['PriorHigh']) & d['Above50'] & d['MA50_above_150'] & d['MA150_up']

    cash = float(initial_cash)
    shares = 0
    entry = stop = 0.0
    entry_date = None
    trades = []
    equity = []

    idx = d.index
    for i in range(1, len(d)-1):
        today = d.iloc[i]
        nxt = d.iloc[i+1]
        date = idx[i]

        if shares == 0 and bool(today['Signal']) and np.isfinite(today['ATR']):
            px = float(nxt['Open']) * (1 + slippage)
            stop_candidate = px - atr_mult * float(today['ATR'])
            risk_cash = cash * risk_pct
            risk_per_share = max(px - stop_candidate, px * 0.005)
            qty = int(risk_cash / risk_per_share)
            max_qty = int((cash * 0.20) / px)
            qty = min(qty, max_qty)
            if qty > 0:
                cost = qty * px * (1 + fee_rate)
                if cost <= cash:
                    cash -= cost
                    shares = qty
                    entry = px
                    stop = stop_candidate
                    entry_date = idx[i+1]

        if shares > 0:
            # Conservative stop ordering: if intraday low breaches stop, assume stop execution.
            exit_px = None
            exit_reason = None
            if float(nxt['Low']) <= stop:
                exit_px = stop * (1 - slippage)
                exit_reason = 'ATR_STOP'
            elif float(nxt['Close']) < float(nxt['MA50']):
                exit_px = float(nxt['Open']) * (1 - slippage)
                exit_reason = 'MA50_EXIT'
            if exit_px is not None:
                proceeds = shares * exit_px * (1 - fee_rate)
                pnl = proceeds - shares * entry * (1 + fee_rate)
                cash += proceeds
                trades.append({
                    'entry_date': entry_date, 'exit_date': idx[i+1],
                    'entry': entry, 'exit': exit_px, 'shares': shares,
                    'pnl': pnl, 'return_pct': pnl / (shares*entry),
                    'reason': exit_reason
                })
                shares = 0; entry = stop = 0.0; entry_date = None

        equity.append((date, cash + shares * float(today['Close'])))

    eq = pd.Series({k: v for k, v in equity}).sort_index()
    if shares:
        final_px = float(d['Close'].iloc[-1])
        proceeds = shares * final_px * (1-fee_rate)
        cash += proceeds
        trades.append({'entry_date': entry_date, 'exit_date': d.index[-1], 'entry': entry,
                       'exit': final_px, 'shares': shares, 'pnl': proceeds-shares*entry*(1+fee_rate),
                       'return_pct': final_px/entry-1, 'reason': 'END_OF_TEST'})
        shares = 0
    if len(eq) == 0:
        return {"metrics": {}, "trades": pd.DataFrame(), "equity": eq}

    total_return = eq.iloc[-1] / initial_cash - 1
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1/365.25)
    cagr = (eq.iloc[-1] / initial_cash) ** (1/years) - 1
    peak = eq.cummax()
    dd = eq / peak - 1
    mdd = dd.min()
    daily = eq.pct_change().dropna()
    sharpe = (daily.mean()/daily.std()*np.sqrt(252)) if daily.std() > 0 else np.nan
    t = pd.DataFrame(trades)
    if len(t):
        wins = t[t.pnl > 0].pnl.sum(); losses = -t[t.pnl < 0].pnl.sum()
        win_rate = (t.pnl > 0).mean(); pf = wins/losses if losses > 0 else np.inf
        avg_win = t.loc[t.pnl > 0, 'pnl'].mean() if (t.pnl > 0).any() else 0
        avg_loss = t.loc[t.pnl < 0, 'pnl'].mean() if (t.pnl < 0).any() else 0
    else:
        win_rate = pf = avg_win = avg_loss = 0
    metrics = {
        'initial_cash': initial_cash, 'final_equity': float(eq.iloc[-1]),
        'total_return': total_return, 'CAGR': cagr, 'MDD': float(mdd),
        'win_rate': float(win_rate), 'profit_factor': float(pf),
        'avg_win': float(avg_win), 'avg_loss': float(avg_loss),
        'Sharpe': float(sharpe) if np.isfinite(sharpe) else None,
        'trade_count': int(len(t))
    }
    return {'metrics': metrics, 'trades': t, 'equity': eq}
