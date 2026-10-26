# SPDX-License-Identifier: GPL-3.0-or-later
"""Backtrader order execution; only lagged close allocations and current opens size trades."""
import numpy as np
import pandas as pd
import backtrader as bt

class Costs(bt.CommInfoBase):
    params=(('stocklike',True),('commtype',bt.CommInfoBase.COMM_PERC),('percabs',True),('buy_rate',0.),('sell_rate',0.))
    def _getcommission(self,size,price,pseudoexec):return abs(size)*price*(self.p.buy_rate if size>0 else self.p.sell_rate)

class FundingBroker(bt.brokers.BackBroker):
    """Apply known opening cash contributions before any order executes."""
    def __init__(self):super().__init__();self.open_flow=0.
    def next(self):
      if self.open_flow:
        self.cash+=self.open_flow
        # Fund-mode is not used. Returns are computed independently from the cash ledger.
        self.open_flow=0.
      super().next()


def rate(symbol,market,stress):
    etfs={'SPY','QQQ','SSO','QLD','SHY','069500.KS','122630.KS'}
    if market=='us':b=s=.0007 if symbol in etfs else .001
    elif symbol in etfs:b=s=.0015
    else:b=.0015;s=.0035
    return b*stress,s*stress

def schedule(weights,start,end,flow,delay=1,benchmark=False):
    w=weights.shift(delay);w=w.loc[start:end]
    if w.isna().any().any():raise ValueError('unwarmed weights')
    dates=w.index;month=pd.Series(dates.to_period('M'),index=dates);first=month.ne(month.shift())
    additions=pd.Series(0.,index=dates)
    if flow:additions.loc[first]=flow;additions.iloc[0]=0.
    changed=w.diff().abs().max(axis=1)>1e-9
    event=changed|first;event.iloc[0]=True
    if benchmark:event=pd.Series(False,index=dates);event.iloc[0]=True;event|=additions>0
    return w,event,additions

class Allocation(bt.Strategy):
    params=(('weights',None),('events',None),('flows',None),('rates',None),('initial',100000.),('benchmark',False))
    def __init__(self):
      self.eq=[];self.orders=[];self.failures=[];self.last_flow=0.;self.prev_notional=0.;self.names=[d._name for d in self.datas];self.traded_notional=0.;self.fundshares=self.p.initial
    def prenext_open(self):self.next_open()
    def nextstart_open(self):self.next_open()
    def next_open(self):
      date=pd.Timestamp(self.datas[0].datetime.date(0))
      if date not in self.p.weights.index:return
      flow=float(self.p.flows.loc[date]);self.last_flow=flow;self.broker.open_flow=flow
      op=np.array([float(d.open[0]) for d in self.datas]);qty=np.array([self.getposition(d).size for d in self.datas]);cash=self.broker.getcash()+flow
      before_flow=self.broker.getcash()+float(qty@op)
      if flow:self.fundshares+=flow/(before_flow/self.fundshares)
      if not self.p.events.loc[date]:return
      nav=cash+float(qty@op);w=self.p.weights.loc[date,self.names].to_numpy()
      goal=nav*w/op
      if self.p.benchmark and len(self.eq)>0:
        goal=qty.copy();j=int(np.argmax(w));goal[j]+=cash/(op[j]*(1+self.p.rates[j][0]))
      # All reductions precede all buys. Project cash using exact configured costs.
      delta=goal-qty;projected=cash
      for j in range(len(qty)):
        if delta[j]<-1e-9:
          size=-delta[j];self.sell(data=self.datas[j],size=size);projected+=size*op[j]*(1-self.p.rates[j][1])
      for j in sorted(range(len(qty)),key=lambda j:(-w[j],self.names[j])):
        if delta[j]>1e-9:
          size=min(delta[j],max(0,projected-self.p.initial*1e-8)/(op[j]*(1+self.p.rates[j][0])))
          # Prior completed bar liquidity, in matching research price units.
          dv=float(self.datas[j].volume[-1])*float(self.datas[j].close[-1])
          size=min(size,.005*dv/op[j])
          if size>1e-9:self.buy(data=self.datas[j],size=size);projected-=size*op[j]*(1+self.p.rates[j][0])
    def notify_order(self,order):
      if order.status==order.Completed:
        e=order.executed;self.traded_notional+=abs(e.size*e.price)
        self.orders.append(dict(date=pd.Timestamp(bt.num2date(e.dt).date()),symbol=order.data._name,side='BUY' if order.isbuy() else 'SELL',qty=abs(e.size),price=e.price,commission=e.comm))
      elif order.status in [order.Margin,order.Rejected,order.Canceled]:self.failures.append(dict(date=str(self.datas[0].datetime.date(0)),symbol=order.data._name,status=order.getstatusname(),size=order.created.size,cash=self.broker.getcash()))
    def next(self):
      date=pd.Timestamp(self.datas[0].datetime.date(0))
      if date not in self.p.weights.index:return
      nav=float(self.broker.getvalue());cash=float(self.broker.getcash())
      if cash<-1e-5:raise AssertionError('negative cash')
      if any(self.getposition(d).size<-1e-8 for d in self.datas):raise AssertionError('short position')
      self.eq.append(dict(date=date,equity=nav,unit_nav=nav/self.fundshares,contribution=self.last_flow,exposure=1-cash/nav,cash=cash))

def execute(data,weights,start,end,market,stress=1,flow=0.,delay=1,benchmark=False,initial=100000.):
    # Only subscribe to instruments the model can hold; common calendar remains fixed.
    active=[s for s in weights if weights[s].abs().max()>0]
    if not active:active=[weights.columns[0]]
    weights=weights[active];w,event,add=schedule(weights,start,end,flow,delay,benchmark)
    first=weights.index.searchsorted(w.index[0]);feed_dates=weights.index[max(0,first-1):weights.index.searchsorted(w.index[-1])+1]
    cerebro=bt.Cerebro(cheat_on_open=True,stdstats=False);broker=FundingBroker();cerebro.setbroker(broker);broker.setcash(initial);broker.set_checksubmit(False)
    rates=[]
    for s in active:
      r=rate(s,market,stress);rates.append(r);broker.addcommissioninfo(Costs(buy_rate=r[0],sell_rate=r[1]),name=s)
      cerebro.adddata(bt.feeds.PandasData(dataname=data[s].loc[feed_dates]),name=s)
    cerebro.addstrategy(Allocation,weights=w,events=event,flows=add,rates=rates,initial=initial,benchmark=benchmark)
    result=cerebro.run(runonce=True,preload=True)[0]
    eq=pd.DataFrame(result.eq).set_index('date');orders=pd.DataFrame(result.orders)
    if not eq.index.equals(w.index):raise AssertionError('skipped execution date')
    if result.failures:raise AssertionError('broker failure '+str(result.failures[:3]))
    return eq,orders,dict(rejected=len(result.failures),gross_traded=result.traded_notional)


def reference(data,weights,start,end,market,stress=1,flow=0.,delay=1,benchmark=False,initial=100000.):
    """Independent vector ledger; no Backtrader objects, prices executed at open."""
    active=[s for s in weights if weights[s].abs().max()>0] or [weights.columns[0]]
    weights=weights[active];w,event,adds=schedule(weights,start,end,flow,delay,benchmark)
    names=list(w);opens=np.column_stack([data[s].loc[w.index,'open'] for s in names]);closes=np.column_stack([data[s].loc[w.index,'close'] for s in names])
    rates=np.array([rate(s,market,stress) for s in names]);cash=initial;units=np.zeros(len(names));fundshares=initial;out=[]
    for i,date in enumerate(w.index):
      o=opens[i]
      if adds.iloc[i]:fundshares+=adds.iloc[i]/((cash+units@o)/fundshares)
      cash+=adds.iloc[i]
      if event.iloc[i]:
        goal=(cash+units@o)*w.iloc[i].to_numpy()/o
        if benchmark and i>0:
          goal=units.copy();j=int(w.iloc[i].to_numpy().argmax());goal[j]+=cash/(o[j]*(1+rates[j,0]))
        for j in range(len(names)):
          if goal[j]<units[j]-1e-9:
            sell=units[j]-goal[j];cash+=sell*o[j]*(1-rates[j,1]);units[j]-=sell
        for j in sorted(range(len(names)),key=lambda j:(-w.iloc[i,j],names[j])):
          need=goal[j]-units[j]
          if need<=1e-9:continue
          ix=data[names[j]].index.searchsorted(date)-1;prior=data[names[j]].iloc[ix]
          buy=min(need,max(0,cash-initial*1e-8)/(o[j]*(1+rates[j,0])),.005*prior.volume*prior.close/o[j])
          if buy>1e-9:units[j]+=buy;cash-=buy*o[j]*(1+rates[j,0])
      nav=cash+units@closes[i];out.append(dict(date=date,equity=nav,unit_nav=nav/fundshares,contribution=adds.iloc[i],exposure=1-cash/nav,cash=cash))
    return pd.DataFrame(out).set_index('date')
