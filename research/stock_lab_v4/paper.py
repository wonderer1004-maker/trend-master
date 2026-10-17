"""Fail-closed paper plan, never submits to a brokerage.
Usage: python research/stock_lab_v4/paper.py --market kr --capital 100000000
Daily adjusted prices are indicative only, not executable broker price units.
"""
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
from run import load,ROOT,OUT
from engine import features,entry_signal

def plan(market,capital):
    if capital<=0:raise ValueError('capital must be positive')
    gate=json.loads((OUT/'execution_gate.json').read_text())
    chosen=gate['selections'][market];data=load(market,'1d');bench=['SPY','QQQ','069500.KS'];last=max(d.index[-1] for d in data.values());watch=[]
    for symbol,d in data.items():
      if symbol in bench or d.index[-1]!=last:continue
      r=features(d).iloc[-1]
      if entry_signal(r,chosen):
        distance=2*r.atr;qty=int(min(capital*.0025/distance,capital*.2/r.close,r.dv*.005/r.close))
        watch.append(dict(symbol=symbol,signal_date=str(last.date()),reference_adjusted_close=float(r.close),indicative_stop=float(r.close-distance),indicative_quantity=qty,reference_notional=float(qty*r.close),risk_budget=capital*.0025))
    decision=next(x for x in gate['decisions'] if x['market']==market and x['strategy']==chosen)
    return dict(market=market,strategy=chosen,as_of=str(last.date()),generated_at=datetime.now(timezone.utc).isoformat(),mode='RESEARCH_WATCHLIST',live_enabled=False,broker_orders=[],watchlist=watch,blocks=['broker adapter absent','historical survivor universe; independent forward validation required','adjusted-price research units require corporate-action mapping before trading']+([] if decision['research_gate'] else ['validation/test index-outperformance gate failed']))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--market',choices=['us','kr'],required=True);p.add_argument('--capital',type=float,required=True);a=p.parse_args()
    result=plan(a.market,a.capital);target=OUT/f'paper_{a.market}.json';target.write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
