"""Fully invested relative-momentum challengers. Research/paper only, no broker."""
import argparse,json
from pathlib import Path
import numpy as np
import pandas as pd
from trend_rotation_v3 import prepare,download,SYMBOLS,ETF,INITIAL,record_intent
MODELS={'LEADER1':(0.,1),'LEADER2':(0.,2),'CORE30':(.3,2)}

def target(data,day,model):
    if model=='BUY_HOLD':return {ETF:1.}
    core,n=MODELS[model];market=data[ETF].loc[day]
    eligible=[]
    for s,d in data.items():
        if s==ETF:continue
        r=d.loc[day]
        if (r.close>r.ma50 and r.ma50>r.ma150 and r.r60>market.r60 and r.r120>market.r120
            and r.r60>0 and r.r120>0 and r.value20>=5e9 and np.isfinite(r.score)):
            eligible.append((r.score-market.score,s))
    names=[s for _,s in sorted(eligible,reverse=True)[:n]]
    if not names:return {ETF:1.}
    weights={s:(1-core)/len(names) for s in names}
    if core:weights[ETF]=core
    return weights

def simulate(data,start,end,model,multiplier=1):
    days=data[ETF].loc[start:end].index
    if len(days)<2:raise ValueError('short period')
    fee=.0005*multiplier;slip=.001*multiplier;tax=.002*multiplier
    cash=float(INITIAL);holdings={};pending=None;last_month=None;curve=[];orders=[]
    previous_target=None
    for i,day in enumerate(days):
        if pending is not None:
            nav=cash+sum(q*float(data[s].loc[day,'open']) for s,q in holdings.items())
            quantities={s:int(nav*w/(float(data[s].loc[day,'open'])*(1+slip)*(1+fee))) for s,w in pending.items()}
            for s,q in list(holdings.items()):
                qty=max(0,q-quantities.get(s,0))
                if qty:
                    px=float(data[s].loc[day,'open'])*(1-slip)
                    cash+=qty*px*(1-fee-(tax if s!=ETF else 0));holdings[s]-=qty
                    orders.append(dict(date=str(day.date()),symbol=s,side='SELL',qty=qty,price=px))
                    if holdings[s]==0:del holdings[s]
            for s,w in sorted(pending.items(),key=lambda p:(-p[1],p[0])):
                px=float(data[s].loc[day,'open'])*(1+slip)
                qty=min(max(0,quantities[s]-holdings.get(s,0)),int(cash/(px*(1+fee))))
                if qty:
                    cash-=qty*px*(1+fee);holdings[s]=holdings.get(s,0)+qty
                    orders.append(dict(date=str(day.date()),symbol=s,side='BUY',qty=qty,price=px))
            pending=None
        nav=cash+sum(q*float(data[s].loc[day,'close']) for s,q in holdings.items())
        curve.append((day,nav));month=(day.year,day.month)
        # Monthly selection, and daily removal of leaders losing the 50-day trend.
        rebalance=month!=last_month
        if model=='BUY_HOLD':rebalance=(i==0)
        invalid=any(s!=ETF and data[s].loc[day,'close']<data[s].loc[day,'ma50'] for s in holdings)
        if rebalance or (model!='BUY_HOLD' and invalid):
            pending=target(data,day,model);previous_target=pending.copy()
        last_month=month
    eq=pd.Series(dict(curve),name='equity');ext=pd.concat([pd.Series([INITIAL],index=[days[0]-pd.Timedelta(days=1)]),eq])
    years=max((days[-1]-days[0]).days/365.25,1/365.25)
    met=dict(total_return=float(eq.iloc[-1]/INITIAL-1),cagr=float((eq.iloc[-1]/INITIAL)**(1/years)-1),
             mdd=float((ext/ext.cummax()-1).min()),end_value=float(eq.iloc[-1]),order_fills=len(orders))
    return met,eq,pd.DataFrame(orders),dict(cash=cash,holdings=holdings,next_target=pending,
         last_target=previous_target,data_asof=str(days[-1].date()),mode='PAPER_REPLAY')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--end',default='2026-10-01');ap.add_argument('--output',default='reports/trend_alpha_v4')
    ap.add_argument('--data-dir');a=ap.parse_args();out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    raw={s:pd.read_csv(Path(a.data_dir)/(s+'.csv'),index_col=0,parse_dates=True) if a.data_dir else download(s,a.end) for s in [ETF,*SYMBOLS]}
    data=prepare(raw);rows=[]
    for model in [*MODELS,'BUY_HOLD']:
        for period,start,end in [('development','2020-01-01','2023-12-31'),('reused_validation','2024-01-01','2026-09-30')]:
            for mult in (1,2):
                met,eq,orders,state=simulate(data,start,end,model,mult)
                rows.append(dict(strategy=model,period=period,cost_multiplier=mult,**met))
                key=f'{model}_{period}_{mult}x';eq.to_csv(out/(key+'_equity.csv'));orders.to_csv(out/(key+'_orders.csv'),index=False)
    table=pd.DataFrame(rows)
    dev=table[(table.period=='development')&(table.cost_multiplier==1)]
    # Select highest development CAGR among challengers, regardless of validation outcomes.
    selected=dev[dev.strategy!='BUY_HOLD'].sort_values(['cagr','strategy'],ascending=[False,True]).iloc[0].strategy
    benchmark=table[table.strategy=='BUY_HOLD'][['period','cost_multiplier','total_return','mdd']].rename(columns={'total_return':'benchmark_return','mdd':'benchmark_mdd'})
    table=table.merge(benchmark,on=['period','cost_multiplier']);table['excess_return']=table.total_return-table.benchmark_return
    table.to_csv(out/'comparison.csv',index=False)
    chosen=table[(table.strategy==selected)&(table.period=='reused_validation')]
    passed=bool((chosen.excess_return>0).all())
    _,_,orders,state=simulate(data,'2020-01-01',str(data[ETF].index[-1].date()),selected)
    decision=state['next_target'];asof=state['data_asof']
    intent=record_intent(out/'paper_intents.sqlite',asof,selected,decision) if decision is not None else None
    state.update(strategy=selected,intent_id=intent,action='REBALANCE_NEXT_OPEN' if decision is not None else 'HOLD')
    (out/'paper_state.json').write_text(json.dumps(state,indent=2));orders.tail(100).to_csv(out/'paper_orders.csv',index=False)
    allocations=target(data,data[ETF].index[-1],selected)
    pd.DataFrame([dict(symbol=s,date=asof,score=float(d.iloc[-1].score),return60=float(d.iloc[-1].r60),
        return120=float(d.iloc[-1].r120),screen_weight=allocations.get(s,0),
        next_order_weight=decision.get(s,0) if decision is not None else None) for s,d in data.items()]).to_csv(out/'screen.csv',index=False)
    status=dict(selected_on_development=selected,outperformed_reused_validation_both_costs=passed,
        status='RESEARCH_ONLY_NO_LIVE_BROKER',risk='up to 100% in one stock; no leverage; ETF fallback remains equity risk',
        limitations=['10 surviving stocks, not historical whole market','reused validation, not unseen holdout',
        'Yahoo adjusted price approximation, independent data verification needed','close exit -> next open, loss can gap',
        'no broker routing, no guaranteed market outperformance'])
    (out/'STATUS.json').write_text(json.dumps(status,indent=2));print(table.to_string(index=False));print(json.dumps(status))
if __name__=='__main__':main()
