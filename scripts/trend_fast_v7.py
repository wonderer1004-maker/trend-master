"""Fast trend confirmation and portfolio volatility cap. Exploratory paper research."""
import argparse,json
from pathlib import Path
import numpy as np
import pandas as pd
import trend_balanced_v6 as base
from trend_rotation_v3 import prepare,download,ETF,SYMBOLS,record_intent
LEVER=base.LEVER
MODELS={'FAST100':None,'FAST45':.45,'MIX45':.45}

def enrich(raw):
    data=prepare(raw)
    for d in data.values():
        d['ma20']=d.close.rolling(20).mean();d['ma60']=d.close.rolling(60).mean()
    d=data[ETF]
    condition=(d.close>d.ma20)&(d.ma20>d.ma60)&(d.close>d.ma200)
    d['confirmed']=condition.rolling(3).sum().eq(3)
    return data

def strong(data,day):return bool(data[ETF].loc[day,'confirmed'])

def target(data,day,model,blocked=()):
    if not strong(data,day):return {}
    weights={LEVER:1.}
    if model=='MIX45':
        market=data[ETF].loc[day];ranks=[]
        for s,d in data.items():
            if s in (ETF,LEVER) or s in blocked:continue
            r=d.loc[day]
            if (r.close>r.ma50 and r.ma50>r.ma150 and r.r60>0 and r.r120>0 and r.value20>=5e9):
                ranks.append((r.score-market.score,s))
        names=[s for _,s in sorted(ranks,reverse=True)[:2]]
        if names:
            weights={LEVER:.6};weights.update({s:.4/len(names) for s in names})
    vol_target=MODELS[model]
    if vol_target:
        series=pd.concat({s:data[s].loc[:day,'close'].pct_change() for s in weights},axis=1).tail(60).dropna()
        if len(series)<50:return {}
        w=np.array([weights[s] for s in series.columns]);sigma=float(np.sqrt(max(0,w@(series.cov().to_numpy()*252)@w)))
        scale=min(1,vol_target/sigma) if sigma>0 else 1
        weights={s:float(v*scale) for s,v in weights.items()}
    return weights

def simulate(data,start,end,model,multiplier=1):
    if model in MODELS:
        return base.simulate(data,start,end,model,multiplier,target_fn=target,strong_fn=strong,weekly=model!='FAST100')
    return base.simulate(data,start,end,model,multiplier)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--end',default='2026-10-01');ap.add_argument('--output',default='reports/trend_fast_v7')
    ap.add_argument('--data-dir');a=ap.parse_args();out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    raw={s:pd.read_csv(Path(a.data_dir)/(s+'.csv'),index_col=0,parse_dates=True) if a.data_dir else download(s,a.end) for s in [ETF,LEVER,*SYMBOLS]}
    # Save input snapshots so the exact adjusted history can be replayed later.
    snap=out/'input';snap.mkdir(exist_ok=True)
    for s,d in raw.items():d.to_csv(snap/(s+'.csv'))
    data=enrich(raw);rows=[]
    for model in [*MODELS,'BUY_HOLD','V5_L50']:
        for period,start,end in [('development','2020-01-01','2023-12-31'),('reused_validation','2024-01-01','2026-09-30')]:
            for mult in (1,2):
                met,eq,orders,_=simulate(data,start,end,model,mult)
                rows.append(dict(strategy=model,period=period,cost_multiplier=mult,**met))
                key=f'{model}_{period}_{mult}x';eq.to_csv(out/(key+'_equity.csv'));orders.to_csv(out/(key+'_orders.csv'),index=False)
    table=pd.DataFrame(rows);dev=table[(table.period=='development')&table.strategy.isin(MODELS)].copy()
    dev['calmar']=dev.cagr/dev.mdd.abs().clip(lower=.01)
    scores=dev.groupby('strategy').calmar.min().to_dict();selected=max(sorted(scores),key=lambda s:scores[s])
    bench=table[table.strategy=='V5_L50'][['period','cost_multiplier','total_return','mdd']].rename(columns={'total_return':'v5_return','mdd':'v5_mdd'})
    table=table.merge(bench,on=['period','cost_multiplier']);table['improves_both_v5']=(table.total_return>table.v5_return)&(table.mdd>table.v5_mdd)
    table.to_csv(out/'comparison.csv',index=False)
    _,_,orders,state=simulate(data,'2020-01-01',str(data[ETF].index[-1].date()),selected)
    decision=state['next_target'];asof=state['data_asof'];intent=record_intent(out/'paper_intents.sqlite',asof,selected,decision) if decision is not None else None
    state.update(strategy=selected,intent_id=intent,action='REBALANCE_NEXT_OPEN' if decision is not None else 'HOLD')
    (out/'paper_state.json').write_text(json.dumps(state,indent=2));orders.tail(100).to_csv(out/'paper_orders.csv',index=False)
    screen=target(data,data[ETF].index[-1],selected)
    pd.DataFrame([dict(symbol=s,date=asof,screen_weight=screen.get(s,0),next_order_weight=decision.get(s,0) if decision is not None else None) for s in data]).to_csv(out/'screen.csv',index=False)
    chosen=table[(table.strategy==selected)&(table.period=='reused_validation')]
    status=dict(selected_on_development=selected,development_worst_cost_calmar=scores,
      improves_both_v5_both_costs=bool(chosen.improves_both_v5.all()),status='RESEARCH_ONLY_NO_LIVE_BROKER',
      limitations=['repeated validation reuse and adaptive strategy changes; high overfitting risk',
        'no independent unseen validation','leverage and surviving stock selection','adjusted prices and account taxes excluded',
        'next-open risk controls can exceed thresholds','no live broker connection'])
    (out/'STATUS.json').write_text(json.dumps(status,indent=2));print(table.to_string(index=False));print(json.dumps(status))
if __name__=='__main__':main()
