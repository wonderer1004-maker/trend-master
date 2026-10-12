"""Fixed V8 and V7/ETF comparison over a user-specified period, no optimization."""
import argparse,json,hashlib
from pathlib import Path
from datetime import date,timedelta
import pandas as pd
from trend_refined_v8 import enrich,simulate,download,ETF,LEVER,SYMBOLS

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--start',default='2024-01-01');ap.add_argument('--end',default='2026-10-12')
    ap.add_argument('--output',default='reports/v8_20240101_20261012');ap.add_argument('--data-dir');a=ap.parse_args()
    start=date.fromisoformat(a.start);end=date.fromisoformat(a.end)
    if start>=end:raise ValueError('start must precede end')
    out=Path(a.output);out.mkdir(parents=True,exist_ok=True);snap=out/'input';snap.mkdir(exist_ok=True)
    raw={};coverage=[]
    for s in [ETF,LEVER,*SYMBOLS]:
        raw[s]=pd.read_csv(Path(a.data_dir)/(s+'.csv'),index_col=0,parse_dates=True) if a.data_dir else download(s,(end+timedelta(days=1)).isoformat())
        raw[s]=raw[s].loc[:a.end]
        raw[s].to_csv(snap/(s+'.csv'))
        coverage.append(dict(symbol=s,first_date=str(raw[s].index[0].date()),last_date=str(raw[s].index[-1].date()),rows=len(raw[s])))
        print('loaded',s,coverage[-1]['last_date'],flush=True)
    data=enrich(raw);last=data[ETF].index[-1]
    if any(x['last_date']!=str(last.date()) for x in coverage):raise ValueError('inconsistent latest symbol dates; do not report stale coverage as current')
    rows=[];states={}
    for model in ('DUAL_BAND45','MIX45','BUY_HOLD'):
        for mult in (1,2):
            met,eq,orders,state=simulate(data,a.start,a.end,model,mult)
            key=f'{model}_{mult}x'
            eq.to_csv(out/(key+'_equity.csv'));orders.to_csv(out/(key+'_orders.csv'),index=False)
            rows.append(dict(strategy=model,cost_multiplier=mult,pnl=met['end_value']-10_000_000,**met))
            states[key]=state
            for freq,label in [('ME','monthly'),('YE','annual')]:
                e=eq.resample(freq).last();p=e.shift();p.iloc[0]=10_000_000
                pd.DataFrame(dict(period=e.index.strftime('%Y-%m' if label=='monthly' else '%Y'),
                    start_value=p.values,end_value=e.values,pnl=(e-p).values,return_pct=((e/p-1)*100).values)).to_csv(out/(key+'_'+label+'.csv'),index=False)
    summary=pd.DataFrame(rows);summary.to_csv(out/'comparison.csv',index=False)
    (out/'ending_states.json').write_text(json.dumps(states,indent=2))
    pd.DataFrame(coverage).to_csv(out/'coverage.csv',index=False)
    meta=dict(requested_start=a.start,requested_end=a.end,first_valuation_date=str(data[ETF].loc[a.start:a.end].index[0].date()),
        actual_last_date=str(last.date()),covers_requested_end=bool(last.date()==end),initial_cash=10_000_000,
        fixed_strategy='DUAL_BAND45',optimization=False,execution='close decision, next trading day open',
        final_valuation='mark open holdings to last close; no fictional terminal liquidation',
        input_sha256={s:hashlib.sha256(d.to_csv().encode()).hexdigest() for s,d in raw.items()},
        costs=dict(fee_each_side=.0005,slippage_each_side=.001,stock_sell_tax_assumption=.002,etf_sell_tax_assumption=0),
        limitations=['account-specific taxes excluded','Yahoo adjusted prices','surviving 10 stocks and leverage',
        'period previously used in strategy selection, not unseen validation','no live orders'])
    (out/'methodology.json').write_text(json.dumps(meta,indent=2));print(summary.to_string(index=False))
    print(json.dumps({k:v for k,v in meta.items() if k!='input_sha256'}))
if __name__=='__main__':main()
