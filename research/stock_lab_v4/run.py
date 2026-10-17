"""Frozen candidate study. Train-only selection; later periods not used for ranking."""
import gzip,hashlib,json,sys
from pathlib import Path
import numpy as np
import pandas as pd
from engine import daily,hold,STRATEGIES,invalid_bars
from intraday import sessions,run as intraday_run
ROOT=Path(__file__).resolve().parent;OUT=ROOT.parents[1]/'reports'/'stock_lab_v4'
WINDOWS={'train':('2018-01-01','2021-12-31'),'validation':('2022-01-01','2023-12-31'),'test':('2024-01-01','2026-10-16'),'full':('2018-01-01','2026-10-16')}
def load(m,kind):
    out={}
    for p in sorted((ROOT/'input'/m).glob(f'*_{kind}.csv.gz')):
      d=pd.read_csv(p,index_col=0,parse_dates=True)
      invalid=invalid_bars(d)
      out[p.name.split('_')[0]]=d.loc[~invalid]
    return out

def write_details(key,e,t,o):
    p=OUT/'details';p.mkdir(exist_ok=True,parents=True)
    e.to_csv(p/(key+'_equity.csv.gz'));pd.DataFrame(t).to_csv(p/(key+'_trades.csv.gz'),index=False);pd.DataFrame(o).to_csv(p/(key+'_orders.csv.gz'),index=False)

def main():
    OUT.mkdir(exist_ok=True,parents=True)
    # Write before any strategy evaluation; not evidence of external preregistration.
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.glob('*.py')}
    (OUT/'rules_hashes.json').write_text(json.dumps(hashes,indent=2))
    rows=[];decisions=[];audit={};selected={}
    for market in ['us','kr']:
      d=load(market,'1d');benches=['SPY','QQQ'] if market=='us' else ['069500.KS'];b=d[benches[0]];stocks={s:v for s,v in d.items() if s not in benches}
      if len(stocks)!=(20 if market=='us' else 10):raise ValueError('universe incomplete')
      initial=100000. if market=='us' else 100000000.
      audit[market]={'symbols':list(stocks),'invalid_source_ohlc_removed':{p.name:[str(x.date()) for x in (lambda z:z.index[(z.high+1e-7<z[['open','close']].max(axis=1))|(z.low-1e-7>z[['open','close']].min(axis=1))|(z.volume<0)])(pd.read_csv(p,index_col=0,parse_dates=True))] for p in (ROOT/'input'/market).glob('*_1d.csv.gz')},'daily_missing_vs_benchmark':{s:[str(z.date()) for z in b.loc['2018':].index.difference(v.index)] for s,v in stocks.items()},'intraday':{}}
      # Assumptions include fees, spread, slippage and a Korean sell-side allowance.
      # They are scenarios, not assertions about a user's actual broker/tax rates.
      for stress in [1,2]:
        buy=(.001 if market=='us' else .0015)*stress;sell=(.001 if market=='us' else .0035)*stress
        for window,(start,end) in WINDOWS.items():
          for flow in ['lump','monthly']:
            contribution=initial*.01 if flow=='monthly' else 0.
            for strategy in STRATEGIES:
              m,e,t,o=daily(stocks,b,strategy,start,end,buy,sell,contribution,initial=initial)
              row=dict(market=market,kind='swing',strategy=strategy,window=window,stress=stress,flow=flow,start=str(e.index[0].date()),end=str(e.index[-1].date()),**m);rows.append(row)
              write_details(f'{market}_{strategy}_{window}_{stress}_{flow}',e,t,o)
            for sym in benches:
              m=hold(d[sym],start,end,buy,sell,contribution,initial)
              rows.append(dict(market=market,kind='benchmark',strategy=sym,window=window,stress=stress,flow=flow,start=start,end=end,**m))
      # Select a single model using training data ONLY, base costs, lump sum.
      training=[r for r in rows if r['market']==market and r['kind']=='swing' and r['window']=='train' and r['stress']==1 and r['flow']=='lump']
      chosen=max(training,key=lambda r:r['sharpe'])['strategy'];selected[market]=chosen
      checks=[]
      for window in ['validation','test']:
        for stress in [1,2]:
          for flow in ['lump','monthly']:
            r=next(r for r in rows if r['market']==market and r['strategy']==chosen and r['window']==window and r['stress']==stress and r['flow']==flow)
            benchmarks=[r for r in rows if r['market']==market and r['kind']=='benchmark' and r['window']==window and r['stress']==stress and r['flow']==flow]
            metric='xirr' if flow=='monthly' else 'cagr'
            checks.append(dict(window=window,stress=stress,flow=flow,positive=r[metric]>0,outperform_all=all(r[metric]>bb[metric] for bb in benchmarks),mdd_better_all=all(r['mdd']>=bb['mdd'] for bb in benchmarks),trades=r['trades']))
      passed=all(c['positive'] and c['outperform_all'] and c['mdd_better_all'] and c['trades']>=30 for c in checks)
      decisions.append(dict(market=market,strategy=chosen,selection='max training Sharpe, base costs lump; ties fixed candidate order',research_gate=passed,live_enabled=False,status='PAPER_ONLY' if passed else 'CASH_BLOCKED',checks=checks,reason='fixed surviving-stock sample; no independent forward paper record; live broker not connected'))
      # Intraday: only complete regular sessions; first 14 complete sessions warmup.
      idata=load(market,'5m')
      if len(idata)!=10:raise ValueError('intraday universe incomplete')
      all_dates=sorted(set.intersection(*[set(v.index.normalize()) for v in idata.values()]))
      # Full and chronological halves are diagnostic only; never annualized income claims.
      for opening in [1,3]:
        events,qa=sessions(idata,market,opening);audit[market]['intraday'][str(opening*5)]=qa
        accepted_days=sorted(set(all_dates)-set(pd.Timestamp(x) for q in qa.values() for x in q['rejected_dates']))
        # Exclude warmup using complete sessions, independently for every stock.
        eligible=[]
        for date in accepted_days:
          if all(sum(pd.Timestamp(x)<date for x in set(v.index.normalize()) if str(pd.Timestamp(x).date()) not in qa[s]['rejected_dates'])>=14 for s,v in idata.items()):eligible.append(date)
        if len(eligible)<10:raise ValueError('too few complete intraday sessions')
        mid=len(eligible)//2
        for window,dates in [('full',eligible),('first_half',eligible[:mid]),('second_half',eligible[mid:])]:
          for stress in [1,2]:
            buy=(.001 if market=='us' else .0015)*stress;sell=(.001 if market=='us' else .0035)*stress
            m,e,t,o=intraday_run(events,dates,buy,sell,initial)
            rows.append(dict(market=market,kind='day',strategy=f'ORB{opening*5}'+('_EXIT1430' if market=='kr' else ''),window=window,stress=stress,flow='lump',start=str(dates[0].date()),end=str(dates[-1].date()),**m))
            write_details(f'{market}_ORB{opening*5}_{window}_{stress}',e,t,o)
      decisions.append(dict(market=market,strategy='ORB5/ORB15',status='CASH_BLOCKED',live_enabled=False,reason='only recent 60-session raw 5-minute sample; insufficient independent evidence'))
    frame=pd.DataFrame(rows);frame.to_csv(OUT/'comparison.csv',index=False)
    (OUT/'comparison.csv.gz').write_bytes(gzip.compress((OUT/'comparison.csv').read_bytes(),mtime=0))
    (OUT/'decisions.json').write_text(json.dumps(decisions,ensure_ascii=False,indent=2));(OUT/'data_audit.json').write_text(json.dumps(audit,indent=2))
    # No live orders. Explicit machine-readable eligibility for downstream paper routing.
    (OUT/'execution_gate.json').write_text(json.dumps({'live_enabled':False,'mode':'research','selections':selected,'decisions':decisions,'broker_orders':[]},ensure_ascii=False,indent=2))
    print(json.dumps(dict(runs=len(rows),selected=selected,decisions=decisions),ensure_ascii=False))
if __name__=='__main__':main()
