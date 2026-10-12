"""Daily research and automated paper execution. Does not submit broker orders."""
from pathlib import Path
import argparse, json
import numpy as np
import pandas as pd

INITIAL = 10_000_000
SYMBOLS = ['005930.KS','000660.KS','005380.KS','035420.KS','005490.KS',
           '051910.KS','068270.KS','006400.KS','012330.KS','055550.KS']

def features(x):
    d=x.copy().sort_index()
    if d.index.has_duplicates: raise ValueError('duplicate dates')
    for n in (20,50,150,200): d[f'ma{n}']=d.close.rolling(n).mean()
    d['high60']=d.high.shift().rolling(60).max()
    d['vol20']=d.volume.shift().rolling(20).mean()
    d['value20']=(d.close*d.volume).rolling(20).mean()
    d['atr']=pd.concat([d.high-d.low,(d.high-d.close.shift()).abs(),
                        (d.low-d.close.shift()).abs()],axis=1).max(axis=1).rolling(14).mean()
    d['mom60']=d.close.pct_change(60)
    return d

def market_states(m):
    bull=(m.close>m.ma200*1.02)&(m.ma50>m.ma200)&(m.ma200>m.ma200.shift(20))
    bear=(m.close<m.ma200*.98)&(m.ma50<m.ma200)
    s=pd.Series('SIDEWAYS',index=m.index)
    s.loc[bull]='BULL'; s.loc[bear]='BEAR'
    s.loc[m.ma200.isna()]='WARMUP'
    return s

def prepare(raw,market,variant='BREAKOUT'):
    m=features(market); states=market_states(m); out={}
    for symbol,x in raw.items():
        d=features(x)
        state=states.reindex(d.index).ffill().fillna('WARMUP')
        rs=d.mom60-m.mom60.reindex(d.index).ffill()
        trend=(d.close>d.ma50)&(d.ma50>d.ma150)&(d.ma150>d.ma200)&(d.ma150>d.ma150.shift(20))
        base=trend&(state=='BULL')&(d.value20>=5e9)&(rs>0)&(d.atr/d.close<=.05)
        breakout=(d.close>d.high60)&(d.volume>=d.vol20*1.5)&(d.close<=d.ma20*1.12)
        pullback=(d.close>d.ma20)&(d.close.shift()<=d.ma20.shift())&(d.volume>=d.vol20)
        d['signal']=(base&(breakout if variant=='BREAKOUT' else breakout|pullback)).fillna(False)
        d['rank']=rs; d['state']=state
        out[symbol]=d
    return out

def simulate(data,start,end,fee=.001,slip=.001,initial=INITIAL):
    """Close decisions -> next open. Stops active intraday, raised only after close."""
    dates=sorted(set().union(*(set(d.loc[start:end].index) for d in data.values())))
    if not dates: raise ValueError('empty simulation period')
    cash=float(initial); pos={}; deals=[]; curve=[]; events=[]; peak=float(initial)
    day_start_equity=float(initial)
    def sell(symbol,px,day,reason):
        nonlocal cash
        p=pos.pop(symbol); proceeds=p['qty']*px*(1-slip)*(1-fee); cash+=proceeds
        deals.append(dict(symbol=symbol,entry_date=str(p['date'].date()),exit_date=str(day.date()),
                          quantity=p['qty'],entry=p['buy'],exit=px,pnl=proceeds-p['cost'],reason=reason))
        events.append(dict(date=str(day.date()),symbol=symbol,side='SELL',quantity=p['qty'],reason=reason,price=px))
    for day in dates:
        # Previous-close exits are executable at this open and can finance open buys.
        for symbol,p in list(pos.items()):
            if day in data[symbol].index and p['pending']:
                sell(symbol,float(data[symbol].loc[day,'open']),day,p['pending'])
        marked=cash+sum(p['qty']*float(data[s].loc[:day].close.iloc[-2] if day in data[s].index and len(data[s].loc[:day])>1 else p['buy']) for s,p in pos.items())
        candidates=[]
        for symbol,d in data.items():
            if symbol in pos or day not in d.index: continue
            i=d.index.get_loc(day)
            if i and bool(d.signal.iloc[i-1]): candidates.append((float(d['rank'].iloc[i-1]),symbol,i))
        for _,symbol,i in sorted(candidates,reverse=True):
            if len(pos)>=5 or marked<peak*.92: break
            d=data[symbol]; prev=d.iloc[i-1]; row=d.iloc[i]
            # Skip >3% upward opening gaps; allow no chasing or leveraged instruments.
            if row.open>prev.close*1.03 or row.open<prev.close*.97: continue
            buy=float(row.open)*(1+slip); distance=max(buy*.04,2*float(prev.atr))
            if not np.isfinite(distance) or distance>buy*.08: continue
            stop=buy-distance
            open_risk=sum(p['qty']*max(0,p['buy']-p['stop']) for p in pos.values())
            budget=max(0,min(marked*.005,marked*.025-open_risk))
            available=min(cash,max(0,marked*.80-sum(p['qty']*p['buy'] for p in pos.values())))
            qty=int(min(budget/distance,marked*.20/(buy*(1+fee)),available/(buy*(1+fee))))
            if qty<1: continue
            cost=qty*buy*(1+fee); cash-=cost
            pos[symbol]=dict(qty=qty,buy=buy,cost=cost,date=day,stop=stop,age=0,high=buy,pending='')
            events.append(dict(date=str(day.date()),symbol=symbol,side='BUY',quantity=qty,reason='previous_close_signal',price=buy))
        for symbol,p in list(pos.items()):
            d=data[symbol]
            if day not in d.index: continue
            row=d.loc[day]
            if row.open<=p['stop']: sell(symbol,float(row.open),day,'gap_stop'); continue
            if row.low<=p['stop']: sell(symbol,p['stop'],day,'stop'); continue
            p['age']+=1; p['high']=max(p['high'],float(row.high))
            # Today's high can only raise tomorrow's stop, avoiding intraday ordering bias.
            p['stop']=max(p['stop'],p['high']-3*float(row.atr))
            if row.state=='BEAR': p['pending']='bear_next_open'
            elif row.close<row.ma50: p['pending']='trend_next_open'
            elif p['age']>=60: p['pending']='time_next_open'
        value=cash+sum(p['qty']*float(data[s].loc[:day].close.iloc[-1]) for s,p in pos.items())
        peak=max(peak,value)
        if value<peak*.92 or value<day_start_equity*.98:
            for p in pos.values(): p['pending']='circuit_breaker_next_open'
        day_start_equity=value
        curve.append((day,value))
    eq=pd.Series(dict(curve),name='equity',dtype=float)
    # No fictional liquidation: terminal positions are marked to market.
    draw=pd.concat([pd.Series([initial],index=[eq.index[0]-pd.Timedelta(days=1)]),eq])
    years=max((eq.index[-1]-eq.index[0]).days/365.25,1/365.25)
    trades=pd.DataFrame(deals)
    wins=[t['pnl'] for t in deals if t['pnl']>0]; losses=[t['pnl'] for t in deals if t['pnl']<0]
    metrics=dict(total_return=float(eq.iloc[-1]/initial-1),cagr=float((eq.iloc[-1]/initial)**(1/years)-1),
                 mdd=float((draw/draw.cummax()-1).min()),closed_trades=len(deals),
                 win_rate=len(wins)/len(deals) if deals else None,
                 profit_factor=sum(wins)/-sum(losses) if losses else None,
                 end_cash=cash,open_positions=len(pos))
    return metrics,trades,eq,events,pos

def download(symbol,end):
    import yfinance as yf
    x=yf.download(symbol,start='2018-01-01',end=end,auto_adjust=True,progress=False,
                  threads=False,multi_level_index=False,timeout=30)
    if isinstance(x.columns,pd.MultiIndex): x.columns=x.columns.get_level_values(0)
    d=x[['Open','High','Low','Close','Volume']].rename(columns=str.lower).dropna()
    d.index=pd.to_datetime(d.index).tz_localize(None)
    if len(d)<250: raise ValueError(f'insufficient history: {symbol}')
    if (d[['open','high','low','close']]<=0).any().any(): raise ValueError('invalid prices')
    return d

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--data-dir'); ap.add_argument('--output',default='reports/trend_guard_v2')
    ap.add_argument('--end',default='2026-10-01'); args=ap.parse_args()
    out=Path(args.output); out.mkdir(parents=True,exist_ok=True)
    def load(s):
        if args.data_dir:
            return pd.read_csv(Path(args.data_dir)/(s+'.csv'),index_col=0,parse_dates=True)
        return download(s,args.end)
    market=load('^KS11'); raw={s:load(s) for s in SYMBOLS} # Fail closed on missing coverage.
    rows=[]; latest=[]
    for variant in ('BREAKOUT','MIXED'):
        data=prepare(raw,market,variant)
        for label,start,end in [('development','2020-01-01','2023-12-31'),('reused_validation','2024-01-01','2026-09-30')]:
            for fee,slip,cost in [(.001,.001,'base'),(.002,.002,'double_cost')]:
                metrics,trades,eq,events,pos=simulate(data,start,end,fee,slip)
                key=f'{variant}_{label}_{cost}'
                trades.to_csv(out/(key+'_trades.csv'),index=False)
                eq.to_csv(out/(key+'_equity.csv'))
                idx=market.loc[start:end].close
                if len(idx)<2: raise ValueError('benchmark missing')
                benchmark=float(idx.iloc[-1]/idx.iloc[0]-1)
                rows.append(dict(strategy=variant,period=label,cost=cost,benchmark_price_return=benchmark,
                                 excess_return=metrics['total_return']-benchmark,**metrics))
        for s,d in data.items():
            r=d.iloc[-1]
            latest.append(dict(variant=variant,symbol=s,date=str(d.index[-1].date()),state=r.state,
                               signal=bool(r.signal),close=float(r.close),breakout_level=float(r.high60),
                               relative_strength=float(r['rank']),atr=float(r.atr)))
        # Paper execution is a deterministic replay; repeated runs cannot duplicate broker orders.
        met,tr,eq,events,pos=simulate(data,'2020-01-01',str(market.index[-1].date()))
        (out/(variant+'_paper_state.json')).write_text(json.dumps(dict(mode='PAPER_REPLAY',asof=str(market.index[-1].date()),
             cash=met['end_cash'],positions=pos,events=events[-30:]),default=str,ensure_ascii=False,indent=2))
    pd.DataFrame(rows).to_csv(out/'comparison.csv',index=False)
    pd.DataFrame(latest).to_csv(out/'signals.csv',index=False)
    (out/'STATUS.json').write_text(json.dumps(dict(status='RESEARCH_ONLY_NOT_APPROVED_FOR_LIVE',
        limitations=['10 surviving KOSPI stocks, not full market','2024+ reused validation, NOT fresh out-of-sample',
        'Yahoo adjusted daily prices, no live feed','benchmark is price index, not total return',
        'daily stop fills approximate; limits, suspensions, taxes need broker validation',
        'No broker orders submitted; paper replay only','No future profitability claim']),indent=2))
    print(pd.DataFrame(rows).to_string(index=False))

if __name__=='__main__': main()
