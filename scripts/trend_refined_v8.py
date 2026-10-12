"""Bounded signal/volatility refinements, compared against frozen V7 input history."""
import argparse,json,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
import trend_fast_v7 as v7
from trend_rotation_v3 import download,SYMBOLS,ETF,record_intent
LEVER=v7.LEVER
MODELS={'HYST45':False,'HYST_DUAL45':True,'HYST_BAND45':False,'DUAL45':True,'DUAL_BAND45':True}

def enrich(raw):
    data=v7.enrich(raw);m=data[ETF];on=False;weak_days=0;states=[]
    for _,r in m.iterrows():
        if not on:
            if bool(r.confirmed):on=True;weak_days=0
        else:
            weak_days=weak_days+1 if r.close<r.ma20*.995 else 0
            if weak_days>=2 or r.close<r.ma60 or r.close<r.ma200 or r.ma20<=r.ma60:
                on=False;weak_days=0
        states.append(on)
    m['hysteresis']=states
    return data

def strong(data,day):return bool(data[ETF].loc[day,'hysteresis'])

def regime(data,day,model):
    return v7.strong(data,day) if model.startswith('DUAL') else strong(data,day)

def target(data,day,model,blocked=()):
    if not regime(data,day,model):return {}
    market=data[ETF].loc[day];ranks=[]
    for s,d in data.items():
        if s in (ETF,LEVER) or s in blocked:continue
        r=d.loc[day]
        if r.close>r.ma50 and r.ma50>r.ma150 and r.r60>0 and r.r120>0 and r.value20>=5e9:
            ranks.append((r.score-market.score,s))
    names=[s for _,s in sorted(ranks,reverse=True)[:2]]
    weights={LEVER:.6} if names else {LEVER:1.}
    for s in names:weights[s]=.4/len(names)
    series=pd.concat({s:data[s].loc[:day,'close'].pct_change() for s in weights},axis=1).tail(60).dropna()
    if len(series)<50:return {}
    w=np.array([weights[s] for s in series.columns])
    def sigma(x):return float(np.sqrt(max(0,w@(x.cov().to_numpy()*252)@w)))
    vol=sigma(series)
    if MODELS[model]:vol=max(vol,sigma(series.tail(20)))
    scale=min(1,.45/vol) if vol>0 else 1
    return {s:float(q*scale) for s,q in weights.items()}

def simulate(data,start,end,model,multiplier=1):
    if model=='MIX45':return v7.simulate(data,start,end,model,multiplier)
    if model=='BUY_HOLD':return v7.simulate(data,start,end,model,multiplier)
    return v7.base.simulate(data,start,end,model,multiplier,target_fn=target,strong_fn=lambda d,t:regime(d,t,model),weekly=True,
                            min_rebalance_delta=.05 if model in ('HYST_BAND45','DUAL_BAND45') else 0)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--end',default='2026-10-01');ap.add_argument('--output',default='reports/trend_refined_v8')
    ap.add_argument('--data-dir');ap.add_argument('--paper-model',choices=[*MODELS,'MIX45']);a=ap.parse_args();out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    raw={s:pd.read_csv(Path(a.data_dir)/(s+'.csv'),index_col=0,parse_dates=True) if a.data_dir else download(s,a.end) for s in [ETF,LEVER,*SYMBOLS]}
    snapshots=out/'input';snapshots.mkdir(exist_ok=True)
    for symbol,frame in raw.items():frame.to_csv(snapshots/(symbol+'.csv'))
    data=enrich(raw);rows=[]
    for model in [*MODELS,'MIX45','BUY_HOLD']:
        for period,start,end in [('development','2020-01-01','2023-12-31'),('reused_validation','2024-01-01','2026-09-30')]:
            for mult in (1,2):
                met,eq,orders,_=simulate(data,start,end,model,mult)
                rows.append(dict(strategy=model,period=period,cost_multiplier=mult,**met))
                key=f'{model}_{period}_{mult}x';eq.to_csv(out/(key+'_equity.csv'));orders.to_csv(out/(key+'_orders.csv'),index=False)
    table=pd.DataFrame(rows);bench=table[table.strategy=='MIX45'][['period','cost_multiplier','total_return','mdd']].rename(columns={'total_return':'v7_return','mdd':'v7_mdd'})
    table=table.merge(bench,on=['period','cost_multiplier']);table['improves_both_v7']=(table.total_return>table.v7_return)&(table.mdd>table.v7_mdd)
    dev=table[(table.period=='development')&table.strategy.isin(MODELS)].copy();dev['calmar']=dev.cagr/dev.mdd.abs().clip(lower=.01)
    scores=dev.groupby('strategy').calmar.min().to_dict();selected=max(sorted(scores),key=lambda s:scores[s])
    dev_selected_passes=bool(table[table.strategy==selected].improves_both_v7.all())
    joint_passers=[s for s in MODELS if bool(table[table.strategy==s].improves_both_v7.all())]
    joint_selected=max(sorted(joint_passers),key=lambda s:scores[s]) if joint_passers else None
    active=a.paper_model or joint_selected or 'MIX45'
    passed=bool(table[table.strategy==active].improves_both_v7.all())
    table.to_csv(out/'comparison.csv',index=False)
    paper_metrics,_,orders,state=simulate(data,'2020-01-01',str(data[ETF].index[-1].date()),active)
    decision=state['next_target'];asof=state['data_asof'];intent=record_intent(out/'paper_intents.sqlite',asof,active,decision) if decision is not None else None
    state.update(strategy=active,intent_id=intent,metrics=paper_metrics,action='REBALANCE_NEXT_OPEN' if decision is not None else 'HOLD')
    (out/'paper_state.json').write_text(json.dumps(state,indent=2));orders.tail(100).to_csv(out/'paper_orders.csv',index=False)
    status=dict(challenger_selected_on_development=selected,development_selected_passes_joint_gate=dev_selected_passes,
        selected_for_historical_joint_goal=joint_selected,selection_uses_reused_validation=True,development_worst_cost_calmar=scores,
        improves_both_v7_all_periods_and_costs=passed,active_paper_strategy=active,status='RESEARCH_ONLY_NO_LIVE_BROKER',
        input_sha256={s:hashlib.sha256(d.to_csv().encode()).hexdigest() for s,d in raw.items()},
        limitations=['same frozen V7 history, not unseen validation','many prior trials; overfitting risk',
        'leveraged ETF and 10 surviving stocks','close risk controls -> next open; no loss ceiling',
        'before account-specific taxes, no broker connection'])
    forward_start='2026-10-13'
    future_days=data[ETF].loc[forward_start:].index
    forward=dict(start=forward_start,locked_paper_model=a.paper_model or active,observations=len(future_days),status='WAITING_FOR_NEW_PERIOD')
    if len(future_days)>=2:
        fmet,feq,ford,_=simulate(data,forward_start,str(future_days[-1].date()),active)
        bmet,beq,_,_=simulate(data,forward_start,str(future_days[-1].date()),'MIX45')
        forward.update(status='FORWARD_RESEARCH_IN_PROGRESS',candidate=fmet,v7=bmet)
        feq.to_csv(out/'forward_candidate_equity.csv');beq.to_csv(out/'forward_v7_equity.csv');ford.to_csv(out/'forward_orders.csv',index=False)
    (out/'forward_validation.json').write_text(json.dumps(forward,indent=2))
    (out/'STATUS.json').write_text(json.dumps(status,indent=2));print(table.to_string(index=False));print(json.dumps({k:v for k,v in status.items() if k!='input_sha256'}))
if __name__=='__main__':main()
