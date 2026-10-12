"""Prespecified momentum rotation research. Automated paper replay, no live orders."""
import argparse,json,hashlib,sqlite3
from pathlib import Path
import numpy as np
import pandas as pd
from trend_guard_v2 import download,SYMBOLS,INITIAL
ETF='069500.KS'
CANDIDATES={'MOM3':(0.,3),'CORE50':(.5,3),'MOM5':(0.,5)}

def prepare(raw):
    frames={}
    for s,x in raw.items():
        d=x.copy().sort_index()
        if d.index.has_duplicates or not d.index.is_monotonic_increasing: raise ValueError('invalid dates')
        if (d[['open','high','low','close']]<=0).any().any(): raise ValueError('invalid price')
        for n in (50,150,200): d[f'ma{n}']=d.close.rolling(n).mean()
        for n in (20,60,120): d[f'r{n}']=d.close.pct_change(n)
        d['vol']=d.close.pct_change().rolling(60).std()*np.sqrt(252)
        d['value20']=(d.close*d.volume).rolling(20).mean()
        d['score']=.2*d.r20+.4*d.r60+.4*d.r120
        d['near_high']=d.close/d.high.shift().rolling(120).max()
        frames[s]=d
    # Common calendar prevents fills on missing/security suspension days.
    calendar=frames[ETF].index
    for d in frames.values(): calendar=calendar.intersection(d.index)
    if len(calendar)<250: raise ValueError('insufficient synchronized history')
    return {s:d.loc[calendar] for s,d in frames.items()}

def allocation(data,day,kind,blocked=()):
    if kind=='BUY_HOLD': return {ETF:1.},'BENCHMARK'
    m=data[ETF].loc[day]
    if pd.isna(m.ma200): return {},'WARMUP'
    bull=m.close>m.ma200 and m.ma50>m.ma200
    bear=m.close<m.ma200 and m.r60<0
    budget=1. if bull else (0. if bear else .5)
    state='BULL' if bull else ('BEAR' if bear else 'SIDEWAYS')
    core,n=CANDIDATES[kind]; weights={ETF:core*budget} if core else {}
    ranks=[]
    for s,d in data.items():
        if s==ETF or s in blocked: continue
        r=d.loc[day]
        eligible=(r.close>r.ma150 and r.ma50>r.ma150 and r.r60>0 and r.r120>0
                  and r.value20>=5e9 and r.near_high>=.8 and np.isfinite(r.vol) and r.vol>0)
        if eligible: ranks.append((r.score-float(m.score),s,r.vol))
    leaders=sorted(ranks,reverse=True)[:n]
    inv=sum(1/v for _,_,v in leaders)
    for _,s,v in leaders:
        weights[s]=min(.35,(1-core)*budget*(1/v)/inv)
    return weights,state # unused slots and caps deliberately leave cash.

def replay(data,start,end,kind,fee=.0005,slip=.001,tax=.002,initial=INITIAL):
    days=data[ETF].loc[start:end].index
    if len(days)<2: raise ValueError('short evaluation window')
    cash=float(initial); holdings={}; highs={}; orders=[]; values=[]; exposures=[]
    peak=float(initial); cooldown={}; pause_until=-1; pending=None; last_month=None; previous_state=None
    ledger=[]; buy_cost={}
    for i,day in enumerate(days):
        # The preceding close creates a target, filled exclusively at today's open.
        if pending is not None:
            nav=cash+sum(q*float(data[s].loc[day,'open']) for s,q in holdings.items())
            desired={s:int(nav*w/(float(data[s].loc[day,'open'])*(1+slip)*(1+fee))) for s,w in pending.items()}
            for s,q in list(holdings.items()):
                sell=q-desired.get(s,0)
                if sell<=0:continue
                px=float(data[s].loc[day,'open'])*(1-slip)
                cost=sell*buy_cost.get(s,0)
                net=sell*px*(1-fee-(0 if s==ETF else tax));cash+=net
                holdings[s]-=sell;ledger.append(dict(date=str(day.date()),symbol=s,qty=sell,pnl=net-cost))
                orders.append(dict(date=str(day.date()),symbol=s,side='SELL',qty=sell,price=px))
                if holdings[s]==0: del holdings[s];highs.pop(s,None);buy_cost.pop(s,None)
            for s,w in sorted(pending.items(),key=lambda z:(-z[1],z[0])):
                px=float(data[s].loc[day,'open'])*(1+slip)
                qty=min(max(0,desired[s]-holdings.get(s,0)),int(cash/(px*(1+fee))))
                if qty<=0:continue
                old=holdings.get(s,0);total=old+qty
                buy_cost[s]=(old*buy_cost.get(s,0)+qty*px*(1+fee))/total
                cash-=qty*px*(1+fee);holdings[s]=total
                highs[s]=max(highs.get(s,0),float(data[s].loc[day,'close']))
                orders.append(dict(date=str(day.date()),symbol=s,side='BUY',qty=qty,price=px))
            pending=None
        nav=cash+sum(q*float(data[s].loc[day,'close']) for s,q in holdings.items())
        peak=max(peak,nav);values.append((day,nav));exposures.append(1-cash/nav)
        for s in holdings:highs[s]=max(highs.get(s,0),float(data[s].loc[day,'close']))
        # Initial observation also supplies a close signal, first possible trade is day 2.
        blocked=[s for s,j in cooldown.items() if i<j]
        target,state=allocation(data,day,kind,blocked)
        month=(day.year,day.month)
        rebalance=last_month!=month or previous_state!=state
        if kind=='BUY_HOLD':rebalance=not holdings and i==0
        if rebalance:pending=target
        if kind!='BUY_HOLD':
            exits=[]
            for s in holdings:
                r=data[s].loc[day]
                if s!=ETF and (r.close<r.ma50 or r.close<highs[s]*.88):
                    exits.append(s);cooldown[s]=i+20
            if exits:
                if pending is None:
                    pending={s:q*float(data[s].loc[day,'close'])/nav for s,q in holdings.items()}
                for s in exits:pending.pop(s,None)
            if nav<=peak*.80 and i>=pause_until:
                pause_until=i+20;pending={};peak=nav
            if i<pause_until:pending={}
            elif i==pause_until:pending=allocation(data,day,kind,blocked)[0]
        last_month=month;previous_state=state
    eq=pd.Series(dict(values),name='equity')
    extended=pd.concat([pd.Series([initial],index=[days[0]-pd.Timedelta(days=1)]),eq])
    years=max((days[-1]-days[0]).days/365.25,1/365.25)
    pnls=[r['pnl'] for r in ledger];profits=sum(x for x in pnls if x>0);losses=-sum(x for x in pnls if x<0)
    metrics=dict(total_return=float(eq.iloc[-1]/initial-1),cagr=float((eq.iloc[-1]/initial)**(1/years)-1),
         mdd=float((extended/extended.cummax()-1).min()),avg_exposure=float(np.mean(exposures)),
         sell_fills=len(ledger),profit_factor=profits/losses if losses else None,end_value=float(eq.iloc[-1]))
    return metrics,eq,pd.DataFrame(orders),dict(cash=cash,holdings=holdings,next_target=pending,
                                               data_asof=str(days[-1].date()),mode='PAPER_REPLAY')

def record_intent(db_path,asof,kind,target):
    """Persist one deterministic close intent per date/strategy; no broker network call."""
    if any(not np.isfinite(w) or w<0 for w in target.values()) or sum(target.values())>1.00001:
        raise ValueError('invalid target weights')
    payload=json.dumps(target,sort_keys=True); key=hashlib.sha256(f'{asof}:{kind}:{payload}'.encode()).hexdigest()
    with sqlite3.connect(db_path) as c:
        c.execute('CREATE TABLE IF NOT EXISTS intents(asof TEXT, strategy TEXT, id TEXT UNIQUE, target TEXT, status TEXT, UNIQUE(asof,strategy))')
        old=c.execute('SELECT id FROM intents WHERE asof=? AND strategy=?',(asof,kind)).fetchone()
        if old and old[0]!=key:raise ValueError('same-date conflicting intent; review required')
        c.execute('INSERT OR IGNORE INTO intents VALUES (?,?,?,?,?)',(asof,kind,key,payload,'PAPER_ONLY'))
    return key

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',default='reports/trend_rotation_v3')
    ap.add_argument('--end',default='2026-10-01');ap.add_argument('--data-dir');args=ap.parse_args()
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    raw={}
    for s in [ETF,*SYMBOLS]:
        raw[s]=pd.read_csv(Path(args.data_dir)/(s+'.csv'),index_col=0,parse_dates=True) if args.data_dir else download(s,args.end)
        print('loaded',s,flush=True)
    data=prepare(raw);rows=[];results={}
    for kind in [*CANDIDATES,'BUY_HOLD']:
        for label,start,end in [('development','2020-01-01','2023-12-31'),('reused_validation','2024-01-01','2026-09-30')]:
            for multiplier in (1,2):
                met,eq,orders,state=replay(data,start,end,kind,fee=.0005*multiplier,slip=.001*multiplier,tax=.002*multiplier)
                key=f'{kind}_{label}_{multiplier}x';eq.to_csv(out/(key+'_equity.csv'));orders.to_csv(out/(key+'_orders.csv'),index=False)
                rows.append(dict(strategy=kind,period=label,cost_multiplier=multiplier,**met))
                if label=='development' and multiplier==1 and kind!='BUY_HOLD':results[kind]=met['cagr']-.5*abs(met['mdd'])
    # Model selection uses development only. Later results are never fed back to selection.
    selected=max(results,key=results.get)
    met,eq,orders,state=replay(data,'2020-01-01',str(data[ETF].index[-1].date()),selected)
    target,regime=allocation(data,data[ETF].index[-1],selected)
    # Actual next replay target includes pending stops/circuit control. No new rebalance -> HOLD.
    decision=state['next_target']
    intent_id=record_intent(out/'paper_intents.sqlite',state['data_asof'],selected,decision) if decision is not None else None
    state.update(strategy=selected,regime=regime,intent_id=intent_id,action='REBALANCE_NEXT_OPEN' if decision is not None else 'HOLD')
    (out/'paper_state.json').write_text(json.dumps(state,indent=2))
    orders.tail(100).to_csv(out/'paper_orders.csv',index=False)
    scan=[]
    for s,d in data.items():
        r=d.iloc[-1];scan.append(dict(symbol=s,date=str(d.index[-1].date()),score=float(r.score),
            return60=float(r.r60),near_high=float(r.near_high),selected_weight=target.get(s,0),
            next_order_weight=decision.get(s,0) if decision is not None else None))
    pd.DataFrame(scan).to_csv(out/'screen.csv',index=False)
    summary=pd.DataFrame(rows);summary.to_csv(out/'comparison.csv',index=False)
    validation=summary[(summary.period=='reused_validation')&(summary.cost_multiplier==1)]
    chosen=validation[validation.strategy==selected].iloc[0];bench=validation[validation.strategy=='BUY_HOLD'].iloc[0]
    status=dict(selected_on_development=selected,selection_score=results,
        status='RESEARCH_ONLY_NO_LIVE_BROKER',beats_benchmark_return=bool(chosen.total_return>bench.total_return),
        limitations=['10 current surviving stocks; survivorship bias','2024+ reused validation, not unseen holdout',
          'Yahoo adjusted price reinvestment approximation; not execution quotes',
          'Fixed research fee/tax/slippage, not current tax advice','No order routing, partial-fill reconciliation or live feed',
          'Daily close stops -> next open; gaps can exceed risk limits'])
    (out/'STATUS.json').write_text(json.dumps(status,indent=2));print(summary.to_string(index=False));print(json.dumps(status))
if __name__=='__main__':main()
