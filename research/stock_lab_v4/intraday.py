"""5-minute-bar long-only opening-range breakout variants, not paper replication."""
import numpy as np
import pandas as pd
from engine import metrics,stop_fill,Rules

def sessions(data,market,opening):
    out={};audit={}
    start='09:30' if market=='us' else '09:00';end='15:55' if market=='us' else '14:25'
    # Korea: flatten at 14:30 open, before end-of-day data gap.
    for s,d in data.items():
      d=d.between_time(start,'16:00' if market=='us' else '15:30');history=[];accepted=0;rejected=[]
      for day,g in d.groupby(d.index.normalize()):
        expected=pd.date_range(str(day.date())+' '+start,str(day.date())+' '+end,freq='5min')
        if not expected.isin(g.index).all() or (market=='kr' and day+pd.Timedelta(hours=14,minutes=30) not in g.index):
          rejected.append(str(day.date()));continue
        g=g.loc[expected] if market=='us' else g.loc[expected.append(pd.DatetimeIndex([day+pd.Timedelta(hours=14,minutes=30)]))]
        vol=float(g.volume.iloc[:opening].sum());baseline=np.mean(history[-14:]) if len(history)>=14 else np.nan
        history.append(vol);accepted+=1
        if not np.isfinite(baseline) or baseline<=0:continue
        b=g.iloc[:opening];high=float(b.high.max());low=float(b.low.min());op=float(b.open.iloc[0]);cl=float(b.close.iloc[-1]);rv=vol/baseline
        if rv<=1 or cl<=op or not .001<=(high-low)/op<=.03:continue
        # Wait until a completed bar closes above the opening range; next bar open entry.
        for k in range(opening,len(g)-1):
          bar=g.iloc[k]
          if g.index[k].hour>=11:break
          if bar.close>high:
            ent=g.iloc[k+1];price=float(ent.open)
            if price<=low or price>high*1.02:break
            stop=low;exit_price=None;reason='session_close';exit_time=None
            # Korea auction bar has only its opening print used for flattening.
            stop_end=len(g) if market=='us' else len(g)-1
            for j in range(k+1,stop_end):
              hit=stop_fill(float(g.iloc[j].open),float(g.iloc[j].low),stop)
              if hit is not None:exit_price=hit;exit_time=g.index[j];reason='stop';break
            if exit_price is None:
              exit_price=float(g.iloc[-1].close if market=='us' else g.iloc[-1].open);exit_time=g.index[-1]+pd.Timedelta(minutes=5) if market=='us' else g.index[-1]
            out.setdefault(day,[]).append(dict(symbol=s,time=g.index[k+1],exit_time=exit_time,price=price,exit_price=exit_price,stop=stop,rvol=rv,volume=float(bar.volume),reason=reason));break
      audit[s]=dict(complete_sessions=accepted,rejected_dates=rejected)
    return out,audit

def run(events,dates,buy,sell,initial=100000.,rules=Rules(max_positions=3)):
    cash=initial;eq={};adds={};trades=[];orders=[]
    for day in dates:
      pending=[];opened=0;losses=0.;opening_equity=cash
      evs=sorted(events.get(day,[]),key=lambda x:(x['time'],-x['rvol'],x['symbol']))
      def settle(until):
        nonlocal cash,losses,pending
        rest=[]
        for p in pending:
          # At a bar timestamp the bar low has not yet been observed. Stop exits
          # settle at the following bar boundary, conservatively avoiding cash reuse.
          if p['settle_time']<=until:
            cash+=p['proceeds'];losses+=min(0,p['pnl']);trades.append(p['trade'])
          else:rest.append(p)
        pending=rest
      for e in evs:
        settle(e['time'])
        if opened>=3 or len(pending)>=3 or losses<=-opening_equity*.01:continue
        qty=int(min(opening_equity*rules.risk/(e['price']-e['stop']),opening_equity*rules.cap/e['price'],cash/(e['price']*(1+buy)),e['volume']*rules.participation))
        if qty<1:continue
        cost=qty*e['price']*(1+buy);cash-=cost;proceeds=qty*e['exit_price']*(1-sell);pnl=proceeds-cost;opened+=1
        trade=dict(symbol=e['symbol'],entry=e['time'],exit=e['exit_time'],pnl=pnl,return_net=pnl/cost,reason=e['reason'])
        settle_time=e['exit_time']+pd.Timedelta(minutes=5) if e['reason']=='stop' else e['exit_time']
        pending.append(dict(proceeds=proceeds,pnl=pnl,trade=trade,settle_time=settle_time))
        orders.extend([dict(date=e['time'],symbol=e['symbol'],side='BUY',qty=qty,price=e['price']),dict(date=e['exit_time'],symbol=e['symbol'],side='SELL',qty=qty,price=e['exit_price'])])
        if cash < -1e-7:raise AssertionError('cash leverage')
      settle(day+pd.Timedelta(days=1));eq[day]=cash;adds[day]=0.
    m=metrics(eq,adds,trades,initial);m['annualized_metrics_unreliable_short_sample']=True
    return m,pd.DataFrame({'equity':pd.Series(eq),'contribution':pd.Series(adds)}),trades,orders
