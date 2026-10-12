"""Market-regime leverage overlay; real ETF history, paper research only."""
import argparse,json
from pathlib import Path
import pandas as pd
from trend_alpha_v4 import simulate
from trend_rotation_v3 import prepare,download,ETF,record_intent
LEVER='122630.KS'
MODELS={'L25':.25,'L50':.5,'L100':1.}

def target(data,day,model):
    if model=='BUY_HOLD':return {ETF:1.}
    if model=='LEVER_HOLD':return {LEVER:1.}
    r=data[ETF].loc[day]
    strong=bool(r.close>r.ma200 and r.ma50>r.ma200 and r.close>r.ma50 and r.r60>0)
    w=MODELS[model] if strong else 0
    return {ETF:1-w,LEVER:w} if 0<w<1 else ({LEVER:1.} if w else {ETF:1.})

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--end',default='2026-10-01');ap.add_argument('--output',default='reports/trend_leverage_v5')
    ap.add_argument('--data-dir');a=ap.parse_args();out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    data=prepare({s:pd.read_csv(Path(a.data_dir)/(s+'.csv'),index_col=0,parse_dates=True) if a.data_dir else download(s,a.end) for s in [ETF,LEVER]})
    rows=[]
    for model in [*MODELS,'BUY_HOLD','LEVER_HOLD']:
        for period,start,end in [('development','2020-01-01','2023-12-31'),('reused_validation','2024-01-01','2026-09-30')]:
            for mult in (1,2):
                met,eq,orders,_=simulate(data,start,end,model,mult,target_fn=target,daily_target=True,tax_exempt=(LEVER,))
                rows.append(dict(strategy=model,period=period,cost_multiplier=mult,**met))
                key=f'{model}_{period}_{mult}x';eq.to_csv(out/(key+'_equity.csv'));orders.to_csv(out/(key+'_orders.csv'),index=False)
    table=pd.DataFrame(rows);dev=table[(table.period=='development')&(table.cost_multiplier==1)&table.strategy.isin(MODELS)]
    selected=dev.sort_values(['cagr','strategy'],ascending=[False,True]).iloc[0].strategy
    bench=table[table.strategy=='BUY_HOLD'][['period','cost_multiplier','total_return','mdd']].rename(columns={'total_return':'benchmark_return','mdd':'benchmark_mdd'})
    table=table.merge(bench,on=['period','cost_multiplier']);table['excess_return']=table.total_return-table.benchmark_return
    table.to_csv(out/'comparison.csv',index=False)
    met,eq,orders,state=simulate(data,'2020-01-01',str(data[ETF].index[-1].date()),selected,target_fn=target,daily_target=True,tax_exempt=(LEVER,))
    decision=state['next_target'];asof=state['data_asof'];intent=record_intent(out/'paper_intents.sqlite',asof,selected,decision) if decision is not None else None
    state.update(strategy=selected,intent_id=intent,action='REBALANCE_NEXT_OPEN' if decision is not None else 'HOLD')
    (out/'paper_state.json').write_text(json.dumps(state,indent=2));orders.tail(100).to_csv(out/'paper_orders.csv',index=False)
    current=target(data,data[ETF].index[-1],selected)
    pd.DataFrame([dict(symbol=s,date=asof,close=float(d.iloc[-1].close),screen_weight=current.get(s,0),
        next_order_weight=decision.get(s,0) if decision is not None else None) for s,d in data.items()]).to_csv(out/'screen.csv',index=False)
    chosen=table[(table.strategy==selected)&(table.period=='reused_validation')]
    passed=bool((chosen.excess_return>0).all())
    (out/'STATUS.json').write_text(json.dumps(dict(selected_on_development=selected,
        outperformed_reused_validation_both_costs=passed,status='RESEARCH_ONLY_NO_LIVE_BROKER',
        attribution='leverage exposure, NOT demonstrated stock-selection alpha',
        limitations=['repeated reuse of historical validation, overfitting risk',
          'real leveraged ETF history; daily leverage differs from long-period 2x',
          'adjusted prices, before account-specific taxes','ETF risk remains in fallback',
          'no live orders; no guarantee of future outperformance']),indent=2))
    print(table.to_string(index=False));print('Selected on development:',selected)
if __name__=='__main__':main()
