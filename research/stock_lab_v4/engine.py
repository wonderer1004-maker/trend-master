"""Long-only research simulator. Signals known before entry; no broker connection."""
from dataclasses import dataclass
import numpy as np
import pandas as pd
@dataclass(frozen=True)
class Rules:
    risk:float=.0025
    cap:float=.20
    max_positions:int=5
    stop_atr:float=2.
    max_days:int=20
    participation:float=.005

STRATEGIES=['BREAK20','BREAK55','RSI2','PULLBACK','MOM20']

def invalid_bars(d):
    return (d.high+1e-7<d[['open','close']].max(axis=1))|(d.low-1e-7>d[['open','close']].min(axis=1))|(d.volume<0)

def features(d):
    d=d.copy();c=d.close
    d['ma200']=c.rolling(200).mean();d['ma20']=c.rolling(20).mean();d['ma5']=c.rolling(5).mean()
    tr=pd.concat([d.high-d.low,(d.high-c.shift()).abs(),(d.low-c.shift()).abs()],axis=1).max(axis=1)
    d['atr']=tr.rolling(14).mean();d['dv']= (c*d.volume).rolling(20).mean();d['v20']=d.volume.rolling(20).mean()
    delta=c.diff();up=delta.clip(lower=0).ewm(alpha=.5,adjust=False,min_periods=2).mean();dn=(-delta.clip(upper=0)).ewm(alpha=.5,adjust=False,min_periods=2).mean()
    d['rsi2']=100-100/(1+up/dn.replace(0,np.nan));d.loc[(dn==0)&(up>0),'rsi2']=100;d.loc[(dn==0)&(up==0),'rsi2']=50
    for n in [10,20,55]:d[f'h{n}']=d.high.shift().rolling(n).max();d[f'l{n}']=d.low.shift().rolling(n).min()
    d['mom']=c/c.shift(60)-1
    return d

def entry_signal(r,name):
    if not np.isfinite(r.ma200) or r.close<=r.ma200 or not np.isfinite(r.atr) or r.atr<=0:return False
    if name.startswith('BREAK'):return r.close>getattr(r,'h'+name[5:])
    if name=='RSI2':return r.rsi2<10
    if name=='PULLBACK':return r.close<r.ma5 and r.close>r.ma20 and r.rsi2<35
    if name=='MOM20':return r.mom>0
    raise ValueError(name)

def exit_signal(r,name):
    if name=='RSI2':return r.close>r.ma5 or r.rsi2>70
    if name=='PULLBACK':return r.close>r.ma5
    return r.close<r.l10 or r.close<r.ma200

def stop_fill(o,l,stop):
    return o if o<=stop else (stop if l<=stop else None)

def xirr(dates,flows,terminal):
    t=(pd.DatetimeIndex(dates)-dates[0]).days.to_numpy()/365.25
    def f(rate):return np.sum(np.array(flows)/(1+rate)**t)+terminal/(1+rate)**t[-1]
    lo,hi=-.9999,100.
    if f(lo)*f(hi)>0:return None
    for _ in range(120):
      mid=(lo+hi)/2
      if f(mid)>0:lo=mid
      else:hi=mid
    return (lo+hi)/2

def metrics(eq,contrib,trades,initial):
    e=pd.Series(eq,dtype=float);a=pd.Series(contrib,index=e.index,dtype=float)
    ret=(e-a)/e.shift()-1;ret.iloc[0]=(e.iloc[0]-a.iloc[0])/initial-1
    nav=(1+ret).cumprod();years=(e.index[-1]-e.index[0]).days/365.25
    pnl=np.array([x['pnl'] for x in trades]);gross_win=pnl[pnl>0].sum();gross_loss=-pnl[pnl<0].sum()
    return dict(total_return=float(nav.iloc[-1]-1),cagr=float(nav.iloc[-1]**(1/years)-1) if years>0 else 0.,mdd=float((nav/nav.cummax().clip(lower=1)-1).min()),sharpe=float(ret.mean()/ret.std()*np.sqrt(252)) if ret.std()>0 else 0.,xirr=xirr(list(e.index),list(-a-np.where(np.arange(len(a))==0,initial,0)),float(e.iloc[-1])),final=float(e.iloc[-1]),paid=float(initial+a.sum()),trades=len(trades),win_rate=float(np.mean(pnl>0)) if len(pnl) else 0.,profit_factor=float(gross_win/gross_loss) if gross_loss else None)

_CACHE={}
def prepare(data,benchmark):
    key=tuple((s,id(d)) for s,d in data.items())
    if key in _CACHE:return _CACHE[key]
    bydate={};prior_bydate={}
    calendar=benchmark.index
    for d in data.values():calendar=calendar.union(d.index)
    for sym,d in data.items():
      f=features(d).rename_axis('date').reset_index();records={r.date:r for r in f.itertuples(index=False)};prev=None
      for date in calendar:
        if prev is not None:prior_bydate.setdefault(date,{})[sym]=prev
        if date in records:
          bydate.setdefault(date,{})[sym]=records[date];prev=records[date]
    _CACHE[key]=(bydate,prior_bydate);return bydate,prior_bydate

def daily(data,benchmark,name,start,end,buy,sell,contribution=0.,rules=Rules(),initial=100000.):
    """Adjusted-price fractional units: total-return proxy, not broker share counts.
    Missing symbol bars block entry; held positions keep last marks, never fake a fill.
    Existing stops set from previous information, exits at next available open.
    """
    bydate,prior_bydate=prepare(data,benchmark);calendar=pd.DatetimeIndex(sorted(bydate));calendar=calendar[(calendar>=pd.Timestamp(start))&(calendar<=pd.Timestamp(end))]
    cash=initial;positions={};last={};eq={};adds={};trades=[];orders=[];missing=0;exposure={};peak_positions=0
    previous_month=None
    for date in calendar:
      month=(date.year,date.month);add=contribution if previous_month is not None and month!=previous_month else 0.;cash+=add;adds[date]=add;previous_month=month
      rows=bydate.get(date,{});prior=prior_bydate.get(date,{})
      # Exit signals from completed prior session. Stops can gap beyond intended loss.
      exited=set()
      for s,p in list(positions.items()):
        if s not in rows:missing+=1;continue
        r=rows[s];pr=prior[s];p['age']+=1
        price=None;reason=''
        if exit_signal(pr,name) or p['age']>=rules.max_days:price=r.open;reason='next_open_exit'
        elif r.open<=p['stop']:price=r.open;reason='gap_stop'
        if price is not None:
          proceeds=p['qty']*price*(1-sell);cash+=proceeds;pnl=proceeds-p['cost']
          trades.append(dict(symbol=s,entry=p['date'],exit=date,pnl=pnl,return_net=pnl/p['cost'],reason=reason,age=p['age']))
          orders.append(dict(date=date,symbol=s,side='SELL',price=price,qty=p['qty'],reason=reason));del positions[s];exited.add(s)
      # MOM20 ranks prior close momentum every 20 benchmark sessions, exits via max hold.
      candidates=[]
      if name!='MOM20' or (len(eq)%20==0):
        for s,pr in prior.items():
          if s in rows and s not in positions and s not in exited and entry_signal(pr,name):
            if (date-pr.date).days>7:continue
            candidates.append((float(pr.mom) if name=='MOM20' else float(pr.dv),s))
      # Equity at open for sizing; proceeds/capital cannot be reused beyond available cash.
      open_equity=cash+sum(p['qty']*(rows[s].open if s in rows else last[s]) for s,p in positions.items())
      for _,s in sorted(candidates,reverse=True):
        if len(positions)>=rules.max_positions:break
        r=rows[s];pr=prior[s];distance=rules.stop_atr*pr.atr
        if distance>=r.open or r.open>pr.close*1.10:continue
        qty=min(open_equity*rules.risk/distance,open_equity*rules.cap/r.open,cash/(r.open*(1+buy)),pr.dv*rules.participation/r.open)
        if qty<=0:continue
        cost=qty*r.open*(1+buy);cash-=cost;stop=r.open-distance
        p=dict(qty=qty,cost=cost,stop=stop,date=date,age=0);positions[s]=p
        orders.append(dict(date=date,symbol=s,side='BUY',price=r.open,qty=qty,reason='prior_close_signal'))
      # Intraday stop exits happen after all open entries; their cash cannot finance open fills.
      for s,p in list(positions.items()):
        if s not in rows:continue
        r=rows[s];fill=stop_fill(r.open,r.low,p['stop'])
        if fill is not None:
          proceeds=p['qty']*fill*(1-sell);cash+=proceeds
          trades.append(dict(symbol=s,entry=p['date'],exit=date,pnl=proceeds-p['cost'],return_net=(proceeds-p['cost'])/p['cost'],reason='intraday_stop',age=p['age']));del positions[s]
      for s,r in rows.items():last[s]=r.close
      # Trail is calculated after the close and is active only from the next session.
      for s,p in positions.items():
        if s in rows and name in ['BREAK20','BREAK55','MOM20']:p['stop']=max(p['stop'],rows[s].close-rules.stop_atr*rows[s].atr)
      eq[date]=cash+sum(p['qty']*last[s] for s,p in positions.items());exposure[date]=1-cash/eq[date];peak_positions=max(peak_positions,len(positions))
      if cash < -1e-7:raise AssertionError('cash leverage')
    # Force liquidation at final close; declared at the beginning of this research window.
    if eq:
      date=calendar[-1]
      for s,p in positions.items():
        price=last[s];proceeds=p['qty']*price*(1-sell);cash+=proceeds
        trades.append(dict(symbol=s,entry=p['date'],exit=date,pnl=proceeds-p['cost'],return_net=(proceeds-p['cost'])/p['cost'],reason='terminal_mark_liquidation',age=p['age']))
        orders.append(dict(date=date,symbol=s,side='SELL',price=price,qty=p['qty'],reason='terminal_mark_liquidation'))
      eq[date]=cash
    result=metrics(eq,adds,trades,initial);result['held_missing_bars']=missing;result['avg_close_exposure']=float(np.mean(list(exposure.values())));result['max_close_positions']=peak_positions
    return result,pd.DataFrame({'equity':pd.Series(eq),'contribution':pd.Series(adds),'exposure':pd.Series(exposure)}),trades,orders

def hold(b,start,end,buy,sell,contribution=0.,initial=100000.):
    b=b.loc[start:end];cash=initial;qty=0.;eq={};adds={};prev=None
    for date,r in b.iterrows():
      month=(date.year,date.month);add=contribution if prev is not None and month!=prev else 0.;prev=month;cash+=add;adds[date]=add
      qty+=cash/(r.open*(1+buy));cash=0.;eq[date]=qty*r.close
    eq[b.index[-1]]*=1-sell
    return metrics(eq,adds,[],initial)
