import argparse
from .providers import us_history, kr_history
from .backtest import run_breakout_backtest

p=argparse.ArgumentParser()
p.add_argument('--market', choices=['US','KR'], required=True)
p.add_argument('--symbol', required=True)
p.add_argument('--cash', type=float, default=10_000_000)
p.add_argument('--breakout', type=int, default=55)
p.add_argument('--risk', type=float, default=.01)
p.add_argument('--fee', type=float, default=.00015)
p.add_argument('--slippage', type=float, default=.0005)
a=p.parse_args()
df=us_history(a.symbol) if a.market=='US' else kr_history(a.symbol)
r=run_breakout_backtest(df, a.cash, a.risk, a.breakout, fee_rate=a.fee, slippage=a.slippage)
print('=== BACKTEST ===')
for k,v in r['metrics'].items(): print(f'{k}: {v}')
if not r['trades'].empty: print(r['trades'].to_string(index=False))
