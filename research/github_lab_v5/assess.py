"""Cashflow-neutral TWR, calendar XIRR and development-only selection."""
import numpy as np
import pandas as pd
WINDOWS={'development':('2018-01-01','2021-12-31'),'validation_reused':('2022-01-01','2023-12-31'),'test_reused':('2024-01-01','2026-10-16'),'full':('2018-01-01','2026-10-16')}

def returns(e,initial):
    r=e.unit_nav.pct_change();r.iloc[0]=e.unit_nav.iloc[0]-1
    return r

def xirr(dates,flows,terminal):
    days=(pd.DatetimeIndex(dates)-dates[0]).days.to_numpy()/365.25;lo,hi=-5.,5.
    # Flows are contributions (positive), compounded forward to terminal.
    horizons=days[-1]-days;flows=np.array(flows)
    for _ in range(100):
      mid=(lo+hi)/2;value=np.dot(flows,np.exp(mid*horizons))
      if value>terminal:hi=mid
      else:lo=mid
    return float(np.expm1((lo+hi)/2))

def metrics(e,orders,initial,window):
    start,end=WINDOWS[window];r=returns(e,initial).loc[start:end];z=e.loc[r.index];loc=e.index.get_loc(r.index[0]);starting=initial if loc==0 else float(e.equity.iloc[loc-1]);previous_date=r.index[0] if loc==0 else e.index[loc-1]
    nav=(1+r).cumprod();years=(r.index[-1]-previous_date).days/365.25;funding=z.contribution.copy();funding.iloc[0]+=starting
    irr=xirr([previous_date,*list(z.index)], [starting,*list(z.contribution)],float(z.equity.iloc[-1]))
    if orders.empty:fills=0;fees=0.
    else:
      o=orders[(orders.date>=r.index[0])&(orders.date<=r.index[-1])];fills=len(o);fees=float(o.commission.sum())
    return dict(start=str(r.index[0].date()),end=str(r.index[-1].date()),observations=len(r),cagr=float(nav.iloc[-1]**(1/years)-1),total_return=float(nav.iloc[-1]-1),xirr=irr,mdd=float((nav/nav.cummax().clip(lower=1)-1).min()),sharpe=float(np.sqrt(252)*r.mean()/r.std()) if r.std()>0 else 0.,avg_exposure=float(z.exposure.mean()),paid=float(funding.sum()),final=float(z.equity.iloc[-1]),fills=fills,costs=fees)

def select(frame,case):
    d=frame[(frame.case==case)&(frame.window=='development')&(frame.stage=='primary')&(~frame.strategy.isin(['HOLD','LEV2_HOLD','STATIC125']))].copy()
    d['score']=d.cagr/d.mdd.abs().clip(lower=.02)
    scores=d.groupby('strategy').score.min().to_dict()
    return sorted(scores,key=lambda s:(-scores[s],s))[0],scores

def block_bootstrap_excess(e,baseline,initial,seed=20261017):
    r=returns(e,initial).loc['2024-01-01':];b=returns(baseline,initial).reindex(r.index)
    rm=(1+r).groupby(r.index.to_period('M')).prod().to_numpy();bm=(1+b).groupby(b.index.to_period('M')).prod().to_numpy();n=len(rm)
    rng=np.random.default_rng(seed);diff=[]
    for _ in range(2000):
      starts=rng.integers(0,n,size=(n+2)//3);idx=np.concatenate([(np.arange(3)+k)%n for k in starts])[:n]
      diff.append(np.prod(rm[idx])**(12/n)-np.prod(bm[idx])**(12/n))
    lo,hi=np.percentile(diff,[2.5,97.5]);return dict(block_months=3,resamples=2000,excess_cagr_ci95=[float(lo),float(hi)],positive_lower_bound=bool(lo>0),limitations='conditional on selected model and surviving universe; not adjusted for full research selection')
