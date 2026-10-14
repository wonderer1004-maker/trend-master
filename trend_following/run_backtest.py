"""Recompute, never overwrite the frozen published study results."""
import argparse,json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import engine
from publish import MARKETS,fetch_symbol

def main():
    p=argparse.ArgumentParser();p.add_argument('--market',choices=['KR','US'],required=True);p.add_argument('--start',required=True);p.add_argument('--end',required=True,help='Completed trading day YYYY-MM-DD');p.add_argument('--output',default='reports/tf_following');a=p.parse_args()
    with ThreadPoolExecutor(max_workers=3) as pool:items=list(pool.map(lambda s:fetch_symbol(a.market,s,a.end),MARKETS[a.market]['symbols']))
    data={s:d for s,d,_,_,_ in items};start=max(d.index[0] for d in data.values());data={s:d.loc[start:] for s,d in data.items()}
    ix=next(iter(data.values())).index
    if not all(d.index.equals(ix) for d in data.values()):raise ValueError('Market calendars differ')
    if sum(ix<a.start)<200:raise ValueError('Need at least 200 warm-up bars before start')
    f=engine.features(data);rows=[];out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    for model in ['HOLD_EQUAL','FIXED50','SMA200','MA50_200','BREAK120','BLEND']:
        for cost in [.001,.005]:
            met,frame,orders=engine.simulate(f,model,a.start,a.end,cost)
            rows.append(dict(market=a.market,model=model,cost=cost,**met));frame.to_json(out/f'{a.market}_{model}_{cost}_equity.json',date_format='iso');(out/f'{a.market}_{model}_{cost}_orders.json').write_text(json.dumps(orders))
    (out/f'{a.market}_comparison.json').write_text(json.dumps(rows,indent=2));print(out/f'{a.market}_comparison.json')

if __name__=='__main__':main()
