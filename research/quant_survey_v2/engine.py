"""Fixed literature-inspired long-only rules. No parameter search. Adjusted-unit replay."""
import json
from pathlib import Path
import numpy as np
import pandas as pd

RULES={
 'BENCH_HOLD':'SPY / KODEX200 buy and hold',
 'GROWTH_HOLD':'QQQ buy and hold (US only)',
 'BASKET_HOLD':'equal-weight initial basket; no rebalancing',
 'EW_MONTHLY':'equal-weight basket; monthly rebalance',
 'MA200':'benchmark above 200-day mean; daily state changes',
 'MA10M':'benchmark above 10 completed month-end mean; monthly',
 'TSM12':'each asset positive 252-session return versus defensive hurdle; 1/N slots',
 'CSM12_1':'top 3 by return from 252 sessions ago to 21 sessions ago; monthly',
 'DUAL12':'top 3 by 252-session return, each must beat SHY (US) or zero (KR); monthly',
 'HIGH52':'top 3 by close / 252-session high; monthly',
 'LOWVOL':'lowest 60-session volatility top 3; monthly; not BAB replication',
 'INVVOL':'all assets weighted by inverse 60-session volatility; monthly; not exact risk parity',
 'VOL15':'benchmark weight min(1, 15%/20-session annual volatility); daily with 5pp target band',
 'BREAKOUT55':'benchmark close breaks prior 55-session high; exit below prior 20-session low; daily',
 'R2':'benchmark above MA200, RSI2 falls 3 days with first below65; exit RSI2>75; daily next open',
 'ENSEMBLE':'equal 1/3 blend of MA10M, TSM12 and DUAL12; monthly',
 'CORE50':'50% benchmark + 50% DUAL12; monthly',
 'MOM_VOL18':'CSM12_1 weights scaled by min(1,18%/60-session portfolio volatility); monthly'}
BASELINES={'BENCH_HOLD','GROWTH_HOLD','BASKET_HOLD','EW_MONTHLY'}


def prepare(raw,market):
    symbols=list(raw);idx=raw[symbols[0]].index
    for s,d in raw.items():
        if d.index.has_duplicates or not d.index.is_monotonic_increasing:raise ValueError('invalid date index '+s)
        if not np.isfinite(d[['open','high','low','close','volume']]).all().all():raise ValueError('nonfinite '+s)
        if (d[['open','high','low','close']]<=0).any().any():raise ValueError('nonpositive '+s)
        idx=idx.intersection(d.index)
    removed={s:[str(x.date()) for x in d.index.difference(idx)] for s,d in raw.items()}
    panels={k:pd.DataFrame({s:d.loc[idx,k] for s,d in raw.items()}) for k in ['open','high','low','close','volume']}
    c=panels['close'];r=c.pct_change()
    bench='SPY' if market=='us' else '069500.KS'
    assets=[s for s in symbols if s!='SHY'] if market=='us' else [s for s in symbols if s!=bench]
    apos=[symbols.index(s) for s in assets];b=symbols.index(bench)
    defense=symbols.index('SHY') if 'SHY' in symbols else None
    month=c.resample('ME').last();m10=month.rolling(10).mean()
    # Attach only completed calendar month observations. Current partial month is never a monthly decision.
    monthly_ma=m10.copy();monthly_ma.index=pd.to_datetime(monthly_ma.index)
    monthly_ma=monthly_ma.reindex(idx.union(monthly_ma.index)).ffill().reindex(idx)
    # Month-end timestamps can fall on weekends: use group transform on observed month ends instead.
    last_dates=pd.Series(idx,index=idx).groupby(idx.to_period('M')).last()
    mm=m10.copy();mm.index=pd.DatetimeIndex([last_dates.loc[x.to_period('M')] for x in m10.index])
    mm=mm.reindex(idx).ffill()
    delta=c.diff();up=delta.clip(lower=0).ewm(alpha=.5,adjust=False,min_periods=2).mean()
    down=(-delta.clip(upper=0)).ewm(alpha=.5,adjust=False,min_periods=2).mean()
    rsi=100-100/(1+up/down);rsi=rsi.mask((down==0)&(up>0),100).mask((down==0)&(up==0),50)
    feat={'ma200':c.rolling(200).mean(),'ma10m':mm,'r252':c/c.shift(252)-1,
          'mom':c.shift(21)/c.shift(252)-1,'high52':c/panels['high'].rolling(252).max(),
          'vol60':r.rolling(60).std()*np.sqrt(252),'vol20':r.rolling(20).std()*np.sqrt(252),
          'prior55':panels['high'].shift().rolling(55).max(),'prior20':panels['low'].shift().rolling(20).min(),
          'rsi2':rsi}
    return dict(idx=idx,symbols=symbols,assets=assets,apos=apos,b=b,defense=defense,
                panels=panels,feat={k:v.to_numpy() for k,v in feat.items()},returns=r.to_numpy(),
                open=panels['open'].to_numpy(),close=c.to_numpy(),removed=removed,market=market)


def schedules(d,start):
    n,p=d['close'].shape;f=d['feat'];c=d['close'];b=d['b'];apos=d['apos'];de=d['defense'];idx=d['idx']
    first=int(idx.searchsorted(pd.Timestamp(start)))
    if first>=n or first<253:raise ValueError('start lacks 253-session warmup')
    models=[x for x in RULES if x!='GROWTH_HOLD' or d['market']=='us']
    targets={x:np.full((n,p),np.nan) for x in models};held={x:False for x in ['MA200','BREAKOUT55','R2']}
    previous_vol=None
    def defensive(w):
        w=np.nan_to_num(w,nan=0.,posinf=0.,neginf=0.)
        w=np.maximum(w,0.)
        if w.sum()>1+1e-9:raise AssertionError('leverage')
        if de is not None:w[de]+=max(0,1-w.sum())
        return w
    def alloc(names):
        w=np.zeros(p)
        if names:w[names]=1/len(names)
        return w
    def top(x,k=3,reverse=True):
        names=[j for j in apos if np.isfinite(x[j])]
        return sorted(names,key=lambda j:((-x[j] if reverse else x[j]),d['symbols'][j]))[:k]
    for i in range(first,n):
        initial=i==first
        # Known calendar boundaries; never use the final partial month as an extra rebalance.
        month_end=(i+1<n and idx[i].month!=idx[i+1].month)
        monthly=initial or month_end
        if initial:
            targets['BENCH_HOLD'][i]=alloc([b]);targets['BASKET_HOLD'][i]=alloc(apos)
            if 'GROWTH_HOLD' in targets:targets['GROWTH_HOLD'][i]=alloc([d['symbols'].index('QQQ')])
        ma=bool(c[i,b]>f['ma200'][i,b]);break_state=held['BREAKOUT55'];r2=held['R2']
        if c[i,b]>f['prior55'][i,b]:break_state=True
        elif c[i,b]<f['prior20'][i,b]:break_state=False
        rs=f['rsi2'][:,b]
        if r2 and rs[i]>75:r2=False
        elif not r2 and ma and rs[i-2]<65 and rs[i]<rs[i-1]<rs[i-2]:r2=True
        for name,state in [('MA200',ma),('BREAKOUT55',break_state),('R2',r2)]:
            if initial or state!=held[name]:targets[name][i]=defensive(alloc([b]) if state else np.zeros(p))
            held[name]=state
        vol=f['vol20'][i,b];vw=min(1,.15/vol) if np.isfinite(vol) and vol>0 else 0
        if initial or previous_vol is None or abs(vw-previous_vol)>=.05:
            w=np.zeros(p);w[b]=vw;targets['VOL15'][i]=defensive(w);previous_vol=vw
        if monthly:
            targets['EW_MONTHLY'][i]=alloc(apos)
            w=np.zeros(p);w[b]=float(c[i,b]>f['ma10m'][i,b]);targets['MA10M'][i]=defensive(w)
            hurdle=f['r252'][i,de] if de is not None else 0
            w=np.zeros(p)
            for j in apos:
                if f['r252'][i,j]>hurdle:w[j]=1/len(apos)
            targets['TSM12'][i]=defensive(w)
            mom_names=top(f['mom'][i]);targets['CSM12_1'][i]=alloc(mom_names)
            names=top(f['r252'][i]);w=np.zeros(p)
            for j in names:
                if f['r252'][i,j]>hurdle:w[j]=1/3
            targets['DUAL12'][i]=defensive(w)
            targets['HIGH52'][i]=alloc(top(f['high52'][i]))
            targets['LOWVOL'][i]=alloc(top(f['vol60'][i],reverse=False))
            inv=np.zeros(p)
            for j in apos:
                if np.isfinite(f['vol60'][i,j]) and f['vol60'][i,j]>0:inv[j]=1/f['vol60'][i,j]
            targets['INVVOL'][i]=inv/inv.sum()
            w=targets['CSM12_1'][i].copy();cov=np.cov(d['returns'][i-59:i+1],rowvar=False)*252
            v=np.sqrt(max(0,float(w@cov@w)));w*=min(1,.18/v) if v>0 else 1
            targets['MOM_VOL18'][i]=defensive(w)
            targets['ENSEMBLE'][i]=(targets['MA10M'][i]+targets['TSM12'][i]+targets['DUAL12'][i])/3
            targets['CORE50'][i]=.5*alloc([b])+.5*targets['DUAL12'][i]
    return targets


def replay(d,target,start,end,mult=1,delay=1,initial=None):
    initial=initial or (100_000 if d['market']=='us' else 10_000_000)
    idx=d['idx'];start_i=idx.searchsorted(pd.Timestamp(start));end_i=idx.searchsorted(pd.Timestamp(end),side='right')
    p=len(d['symbols']);units=np.zeros(p);cash=float(initial);eq=[];orders=[]
    fee=(.0002 if d['market']=='us' else .0005)*mult
    slip=(.0005 if d['market']=='us' else .001)*mult
    for i in range(start_i,end_i):
        k=i-delay
        if k>=start_i and np.isfinite(target[k]).all():
            w=target[k];op=d['open'][i]
            nav=cash+float(units@op);goal=nav*w/op
            delta=goal-units
            sold=np.maximum(-delta,0)
            sell_tax=np.array([.002*mult if d['market']=='kr' and s!='069500.KS' else 0 for s in d['symbols']])
            proceeds=sold*op*(1-slip)*(1-fee-sell_tax)
            cash+=float(proceeds.sum());units-=sold
            buy=np.maximum(delta,0);cost=buy*op*(1+slip)*(1+fee)
            scale=min(1,cash/cost.sum()) if cost.sum()>0 else 1
            buy*=max(0,scale);cash-=float((buy*op*(1+slip)*(1+fee)).sum());units+=buy
            for j in range(p):
                if sold[j]*op[j]>initial*1e-8:orders.append((str(idx[k].date()),str(idx[i].date()),d['symbols'][j],'SELL',float(sold[j]),float(op[j]*(1-slip))))
                if buy[j]*op[j]>initial*1e-8:orders.append((str(idx[k].date()),str(idx[i].date()),d['symbols'][j],'BUY',float(buy[j]),float(op[j]*(1+slip))))
        if cash<-.001 or (units< -1e-8).any():raise AssertionError('cash or short constraint violated')
        positions=units*d['close'][i];nav=cash+float(positions.sum())
        defensive=float(positions[d['defense']]) if d['defense'] is not None else 0
        eq.append((idx[i],nav,cash,float(positions.sum()-defensive)/nav))
    curve=pd.DataFrame(eq,columns=['date','equity','cash','risk_assets_weight']).set_index('date')
    x=curve.equity.to_numpy();path=np.r_[initial,x];ret=np.diff(path)/path[:-1]
    years=(curve.index[-1]-curve.index[0]).days/365.25
    mdd=float(np.min(path/np.maximum.accumulate(path)-1));vol=float(np.std(ret,ddof=1)*np.sqrt(252))
    cagr=float((x[-1]/initial)**(1/years)-1)
    annual=curve.equity.resample('YE').last();ar=annual/annual.shift()-1;ar.iloc[0]=annual.iloc[0]/initial-1
    stats=dict(cagr_pct=cagr*100,total_return_pct=(x[-1]/initial-1)*100,mdd_pct=mdd*100,
       calmar=cagr/abs(mdd) if mdd<0 else 0,volatility_pct=vol*100,
       sharpe_zero_rf=float(np.mean(ret)/np.std(ret,ddof=1)*np.sqrt(252)) if vol>0 else 0,
       final_value=float(x[-1]),initial_value=initial,currency='USD' if d['market']=='us' else 'KRW',
       order_count=len(orders),average_risk_assets_pct=float(curve.risk_assets_weight.mean()*100),
       positive_calendar_years=int((ar>0).sum()),calendar_years=len(ar),
       first=str(curve.index[0].date()),last=str(curve.index[-1].date()))
    return stats,curve,pd.DataFrame(orders,columns=['signal_date','fill_date','symbol','side','adjusted_units','fill_price'])


def exposure_control(d,target):
    out=np.full_like(target,np.nan)
    for i,w in enumerate(target):
        if np.isfinite(w).all():
            risk=float(w.sum()-(w[d['defense']] if d['defense'] is not None else 0))
            out[i]=0;out[i,d['b']]=risk
            if d['defense'] is not None:out[i,d['defense']]=1-risk
    return out
