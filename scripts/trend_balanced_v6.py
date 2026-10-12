"""Cash defense, hybrid momentum and volatility sizing. Research/paper only."""
import argparse,json
from pathlib import Path
import numpy as np
import pandas as pd
from trend_rotation_v3 import prepare,download,ETF,SYMBOLS,INITIAL,record_intent
LEVER='122630.KS'
MODELS={'CASH50':None,'CASH100':None,'HYBRID':None,'VOL25':.25,'VOL35':.35}
BASELINES=('BUY_HOLD','LEVER_HOLD','V5_L50')

def strong(data,day):
    r=data[ETF].loc[day]
    return bool(r.close>r.ma200 and r.ma50>r.ma200 and r.close>r.ma50 and r.r60>0)

def target(data,day,model,blocked=()):
    if model=='BUY_HOLD':return {ETF:1.}
    if model=='LEVER_HOLD':return {LEVER:1.}
    if model=='V5_L50':return {ETF:.5,LEVER:.5} if strong(data,day) else {ETF:1.}
    if not strong(data,day):return {}
    if model=='CASH50':return {ETF:.5,LEVER:.5}
    if model=='CASH100':return {LEVER:1.}
    market=data[ETF].loc[day];leaders=[]
    for s,d in data.items():
        if s in (ETF,LEVER) or s in blocked:continue
        r=d.loc[day]
        if (r.close>r.ma50 and r.ma50>r.ma150 and r.r60>0 and r.r120>0
            and r.value20>=5e9 and r.near_high>=.8):leaders.append((r.score-market.score,s))
    names=[s for _,s in sorted(leaders,reverse=True)[:2]]
    weights={LEVER:.7 if names else 1.}
    for s in names:weights[s]=.3/len(names)
    vol_target=MODELS[model]
    if vol_target:
        # Real asset portfolio trailing covariance, data through today's close only.
        series=pd.concat({s:data[s].loc[:day,'close'].pct_change() for s in weights},axis=1).tail(60).dropna()
        if len(series)<50:return {}
        vector=np.array([weights[s] for s in series.columns]);cov=series.cov().to_numpy()*252
        sigma=float(np.sqrt(max(0,vector@cov@vector)))
        scale=min(1,vol_target/sigma) if sigma>0 else 1
        weights={s:float(w*scale) for s,w in weights.items()}
    return weights

def simulate(data,start,end,model,multiplier=1,target_fn=None,strong_fn=None,weekly=None,min_rebalance_delta=0.):
    choose=target_fn or target
    condition=strong_fn or strong
    days=data[ETF].loc[start:end].index
    if len(days)<2:raise ValueError('short evaluation window')
    fee=.0005*multiplier;slip=.001*multiplier;tax=.002*multiplier
    cash=float(INITIAL);holdings={};highs={};cooldown={};pending=None
    curve=[];orders=[];exposures=[];last_strong=None;last_month=None;peak=float(INITIAL);pause_until=-1
    controls=model not in BASELINES
    for i,day in enumerate(days):
        if pending is not None:
            nav=cash+sum(q*float(data[s].loc[day,'open']) for s,q in holdings.items())
            quantities={s:int(nav*w/(float(data[s].loc[day,'open'])*(1+slip)*(1+fee))) for s,w in pending.items()}
            for s,q in list(holdings.items()):
                qty=max(0,q-quantities.get(s,0))
                if qty:
                    px=float(data[s].loc[day,'open'])*(1-slip)
                    cash+=qty*px*(1-fee-(0 if s in (ETF,LEVER) else tax));holdings[s]-=qty
                    orders.append(dict(date=str(day.date()),symbol=s,side='SELL',qty=qty,price=px))
                    if holdings[s]==0:del holdings[s];highs.pop(s,None)
            for s,w in sorted(pending.items(),key=lambda z:(-z[1],z[0])):
                px=float(data[s].loc[day,'open'])*(1+slip)
                qty=min(max(0,quantities[s]-holdings.get(s,0)),int(cash/(px*(1+fee))))
                if qty:
                    cash-=qty*px*(1+fee);holdings[s]=holdings.get(s,0)+qty
                    orders.append(dict(date=str(day.date()),symbol=s,side='BUY',qty=qty,price=px))
            pending=None
        nav=cash+sum(q*float(data[s].loc[day,'close']) for s,q in holdings.items())
        curve.append((day,nav));exposures.append(1-cash/nav);peak=max(peak,nav)
        for s in holdings:highs[s]=max(highs.get(s,0),float(data[s].loc[day,'close']))
        state=condition(data,day);month=(day.year,day.month)
        exits=[]
        if controls:
            for s in holdings:
                if s not in (ETF,LEVER) and (data[s].loc[day,'close']<data[s].loc[day,'ma50'] or data[s].loc[day,'close']<highs[s]*.88):
                    exits.append(s);cooldown[s]=i+20
            if i==pause_until:peak=nav
            if nav<=peak*.75 and i>=pause_until:
                pause_until=i+10;pending={}
        # Hybrid/vol sizing update weekly; fixed ETF mixes update monthly or regime changes.
        periodic=(day.weekday()==4) if (weekly is True or (weekly is None and model in ('HYBRID','VOL25','VOL35'))) else month!=last_month
        if model in ('BUY_HOLD','LEVER_HOLD'):periodic=(i==0)
        changed=(state!=last_strong) if model not in ('BUY_HOLD','LEVER_HOLD') else False
        if periodic or changed or exits or (controls and i==pause_until):
            blocked=[s for s,j in cooldown.items() if i<j]
            pending=choose(data,day,model,blocked)
        if pending is not None and min_rebalance_delta>0 and not changed and not exits and i!=pause_until and pending:
            current={s:q*float(data[s].loc[day,'close'])/nav for s,q in holdings.items()}
            drift=max(abs(pending.get(s,0)-current.get(s,0)) for s in set(pending)|set(current))
            if drift<min_rebalance_delta:pending=None
        if controls and i<pause_until:pending={}
        last_strong=state;last_month=month
    eq=pd.Series(dict(curve),name='equity');ext=pd.concat([pd.Series([INITIAL],index=[days[0]-pd.Timedelta(days=1)]),eq])
    years=max((days[-1]-days[0]).days/365.25,1/365.25)
    met=dict(total_return=float(eq.iloc[-1]/INITIAL-1),cagr=float((eq.iloc[-1]/INITIAL)**(1/years)-1),
        mdd=float((ext/ext.cummax()-1).min()),end_value=float(eq.iloc[-1]),order_fills=len(orders),avg_exposure=float(np.mean(exposures)))
    return met,eq,pd.DataFrame(orders),dict(cash=cash,holdings=holdings,next_target=pending,
        data_asof=str(days[-1].date()),mode='PAPER_REPLAY',pause_remaining=max(0,pause_until-len(days)+1))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--end',default='2026-10-01');ap.add_argument('--output',default='reports/trend_balanced_v6')
    ap.add_argument('--data-dir');a=ap.parse_args();out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    raw={}
    for s in [ETF,LEVER,*SYMBOLS]:
        raw[s]=pd.read_csv(Path(a.data_dir)/(s+'.csv'),index_col=0,parse_dates=True) if a.data_dir else download(s,a.end)
        print('loaded',s,flush=True)
    data=prepare(raw);rows=[]
    for model in [*MODELS,*BASELINES]:
        for period,start,end in [('development','2020-01-01','2023-12-31'),('reused_validation','2024-01-01','2026-09-30')]:
            for mult in (1,2):
                met,eq,orders,_=simulate(data,start,end,model,mult)
                rows.append(dict(strategy=model,period=period,cost_multiplier=mult,**met))
                key=f'{model}_{period}_{mult}x';eq.to_csv(out/(key+'_equity.csv'));orders.to_csv(out/(key+'_orders.csv'),index=False)
    table=pd.DataFrame(rows)
    # Robust development selection: worst cost-case Calmar; validation never selects.
    dev=table[(table.period=='development')&table.strategy.isin(MODELS)].copy()
    dev['calmar']=dev.cagr/dev.mdd.abs().clip(lower=.01)
    scores=dev.groupby('strategy').calmar.min().to_dict();selected=max(sorted(scores),key=lambda s:scores[s])
    benchmarks=table[table.strategy=='V5_L50'][['period','cost_multiplier','total_return','mdd']].rename(columns={'total_return':'v5_return','mdd':'v5_mdd'})
    table=table.merge(benchmarks,on=['period','cost_multiplier'])
    table['improves_both_v5']=(table.total_return>table.v5_return)&(table.mdd>table.v5_mdd)
    table.to_csv(out/'comparison.csv',index=False)
    _,_,orders,state=simulate(data,'2020-01-01',str(data[ETF].index[-1].date()),selected)
    decision=state['next_target'];asof=state['data_asof'];intent=record_intent(out/'paper_intents.sqlite',asof,selected,decision) if decision is not None else None
    state.update(strategy=selected,intent_id=intent,action='REBALANCE_NEXT_OPEN' if decision is not None else 'HOLD')
    (out/'paper_state.json').write_text(json.dumps(state,indent=2));orders.tail(100).to_csv(out/'paper_orders.csv',index=False)
    # Pure screen allocation isn't necessarily the order: cooldown/circuit controls can override it.
    screen=target(data,data[ETF].index[-1],selected)
    pd.DataFrame([dict(symbol=s,date=asof,score=float(d.iloc[-1].score),screen_weight=screen.get(s,0),
        next_order_weight=decision.get(s,0) if decision is not None else None) for s,d in data.items()]).to_csv(out/'screen.csv',index=False)
    chosen=table[(table.strategy==selected)&(table.period=='reused_validation')]
    status=dict(selected_on_development=selected,development_worst_cost_calmar=scores,
        improves_both_v5_both_costs=bool(chosen.improves_both_v5.all()),status='RESEARCH_ONLY_NO_LIVE_BROKER',
        limitations=['reused validation after many trials; overfitting risk','10 current surviving stocks, not historical full market',
        'close risk decisions fill next open; gaps exceed loss thresholds','cash return assumed zero',
        'leverage, adjusted prices, before account-specific taxes','no live feed, no broker order routing'])
    (out/'STATUS.json').write_text(json.dumps(status,indent=2));print(table.to_string(index=False));print(json.dumps(status))
if __name__=='__main__':main()
