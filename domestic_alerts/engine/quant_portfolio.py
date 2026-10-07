"""Daily short-term multi-asset portfolio: causal signals, next-session execution."""
from dataclasses import dataclass,asdict
from collections import Counter
import numpy as np,pandas as pd

MODELS=['breakout20','pullback_recovery','rsi2_reversion','etf_rotation','etf_direction','adaptive']
@dataclass
class QuantConfig:
 capital:float=5_000_000
 fee:float=.00015
 slip:float=.001
 stock_tax:float=.002
 tax_stress:float=0.0
 risk:float=.005
 weight:float=.20
 max_positions:int=4
 total_risk:float=.015
 sector_weight:float=.40
 participation:float=.001
 turnover:float=5_000_000_000
 drawdown_halt:float=.08
 daily_loss:float=.02
 model:str='adaptive'


def prepare(daily,metadata):
 out=[]
 for s,g in daily.groupby('symbol'):
  g=g.sort_values('timestamp').copy();c=g.close;prev=c.shift()
  tr=pd.concat([g.high-g.low,(g.high-prev).abs(),(g.low-prev).abs()],axis=1).max(axis=1)
  g['atr']=tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
  for n in [5,20,60,200]:g['ma'+str(n)]=c.rolling(n).mean()
  delta=c.diff();up=delta.clip(lower=0).ewm(alpha=.5,adjust=False,min_periods=2).mean();dn=(-delta.clip(upper=0)).ewm(alpha=.5,adjust=False,min_periods=2).mean();g['rsi2']=100-100/(1+up/dn.replace(0,np.nan));g.loc[(dn==0)&(up>0),'rsi2']=100
  g['prev_rsi2']=g.rsi2.shift();g['prev_close']=prev;g['high20']=g.high.shift().rolling(20).max();g['r20']=c/c.shift(20)-1;g['turnover20']=(c*g.volume).rolling(20).mean()
  g['kind']=metadata.get(s,{}).get('kind','stock');g['group']=metadata.get(s,{}).get('group',s);out.append(g)
 return pd.concat(out).sort_values(['timestamp','symbol']).reset_index(drop=True)


def regime(m):
 if not np.isfinite(m.ma60):return 'WARMUP'
 if m.close>m.ma20>m.ma60:return 'BULL'
 if m.close<m.ma20<m.ma60:return 'BEAR'
 return 'NEUTRAL'


def make_signal(r,m,model,c):
 reg=regime(m);etf=r.kind!='stock';inverse=r.symbol=='114800';risk=c.risk;hold=5;leg=None
 liquid=r.turnover20>=(500_000_000 if etf else c.turnover)
 if not liquid or r.close<1000 or not np.isfinite(r.atr) or r.atr<=0:return None
 if model in ['breakout20','adaptive'] and reg=='BULL' and not etf and r.close>r.high20 and r.close>r.ma20>r.ma60 and r.prev_close<=r.high20:leg='breakout20'
 if model in ['pullback_recovery','adaptive'] and reg=='BULL' and not etf and r.close>r.ma20>r.ma60 and r.prev_rsi2<20 and r.close>r.prev_close:leg='pullback_recovery'
 if model in ['rsi2_reversion','adaptive'] and reg!='BEAR' and not etf and r.close>r.ma200 and r.rsi2<10 and r.close<r.ma5:
  leg='rsi2_reversion';hold=3;risk=.003
 if model=='etf_rotation' and r.kind=='equity_etf' and reg=='BULL' and r.close>r.ma20>r.ma60 and r.r20>0:
  leg='etf_rotation';hold=10
 if model in ['etf_direction','adaptive'] and etf and ((reg=='BULL' and r.symbol=='122630') or (reg=='BEAR' and inverse)) and r.close>r.ma20 and r.r20>0:
  leg='etf_direction';hold=5;risk=.003 if inverse else c.risk
 if not leg:return None
 return {'symbol':r.symbol,'leg':leg,'kind':r.kind,'group':r.group,'signal_time':r.timestamp,'stop':r.close-2*r.atr,'ceiling':r.close+.5*r.atr,'volume':r.volume,'risk':risk,'hold':hold,'rank':float(r.r20) if np.isfinite(r.r20) else -1,'regime':reg}


def quantity(eq,cash,fill,z,c,remaining,sector_value):
 tax=c.stock_tax if z['kind']=='stock' else 0
 unit=fill-z['stop']+fill*(2*c.fee+2*c.slip+tax)
 if not .005<=(fill-z['stop'])/fill<=.15:return 0
 return max(0,int(min(eq*z['risk']/unit,remaining/unit,eq*c.weight/fill,(eq*c.sector_weight-sector_value)/fill,cash/(fill*(1+c.fee)),z['volume']*c.participation)))


def exit_quote(r,p,forced=None,end=False):
 if r.open<=p['stop']:return r.open,'gap_stop'
 if forced:return r.open,forced
 if r.low<=p['stop']:return p['stop'],'stop'
 if end:return r.close,'end_period_close'
 return None,None


def backtest(f,index,start,end,c=None,liquidate=True):
 c=c or QuantConfig();ix=index.set_index('timestamp');cash=c.capital;pos={};orders=[];trades=[];curve=[];audit=Counter();last={};halt=False;peak=c.capital;previous_eq=c.capital;last_market=None
 for ts,g in f.groupby('timestamp',sort=True):
  if ts<start or ts>end or ts not in ix.index:continue
  rows={r.symbol:r for r in g.itertuples()};m=ix.loc[ts]
  # Prior close exits execute first at this session's open; then entries.
  for s,p in list(pos.items()):
   p['age']+=1
   if s not in rows:
    audit['stale_position_sessions']+=1
    continue
   r=rows[s];forced=p['forced']
   if halt:forced='risk_halt_exit'
   elif last_market is not None:
    rg=regime(last_market)
    if s=='114800' and rg!='BEAR':forced='regime_exit'
    elif s!='114800' and rg=='BEAR':forced='regime_exit'
   # At the open, today's later LOW is unknown and cannot fund another open entry.
   if r.open<=p['stop']:price,reason=r.open,'gap_stop'
   elif forced:price,reason=r.open,forced
   else:price,reason=None,None
   if price is not None:
    fill=price*(1-c.slip);taxrate=c.stock_tax if p['kind']=='stock' else 0;wh=max(0,p['qty']*(fill-p['entry']))*c.tax_stress if p['kind']=='derivative_etf' else 0
    proceeds=p['qty']*fill*(1-c.fee-taxrate)-wh;pnl=proceeds-p['cost'];cash+=proceeds
    trades.append({'symbol':s,'leg':p['leg'],'kind':p['kind'],'entry_time':p['time'],'exit_time':str(ts),'entry':p['entry'],'exit':fill,'qty':p['qty'],'pnl':pnl,'R':pnl/(p['qty']*(p['entry']-p['initial_stop'])),'reason':reason,'holding_sessions':p['age'],'tax_stress':wh});del pos[s]
  for z in orders:
   s=z['symbol']
   if halt or (liquidate and ts>=end) or s not in rows or s in pos or len(pos)>=c.max_positions:continue
   r=rows[s];fill=r.open*(1+c.slip)
   if fill>z['ceiling'] or fill<=z['stop']:audit['reject_gap']+=1;continue
   # Use prior-known marks plus this session OPEN of held positions, never today's close.
   eq=cash+sum(p['qty']*(rows[k].open if k in rows else last[k]) for k,p in pos.items())
   allocated=sum(p['budget'] for p in pos.values());sector_value=sum(p['qty']*(rows[k].open if k in rows else last[k]) for k,p in pos.items() if p['group']==z['group'])
   q=quantity(eq,cash,fill,z,c,max(0,eq*c.total_risk-allocated),sector_value)
   if not q:audit['reject_quantity']+=1;continue
   tax=c.stock_tax if z['kind']=='stock' else 0;budget=q*(fill-z['stop']+fill*(2*c.fee+2*c.slip+tax));cost=q*fill*(1+c.fee);cash-=cost
   pos[s]={**z,'entry':fill,'qty':q,'cost':cost,'time':str(ts),'initial_stop':z['stop'],'high':fill,'age':0,'budget':budget,'forced':None};audit['entries']+=1
  orders=[]
  # Intraday stops and terminal close liquidation occur only AFTER all open entries.
  for s,p in list(pos.items()):
   if s not in rows:continue
   r=rows[s];last[s]=r.close
   price,reason=exit_quote(r,p,end=liquidate and ts==end)
   if price is not None:
    fill=price*(1-c.slip);tx=c.stock_tax if p['kind']=='stock' else 0;wh=max(0,p['qty']*(fill-p['entry']))*c.tax_stress if p['kind']=='derivative_etf' else 0;proceeds=p['qty']*fill*(1-c.fee-tx)-wh;pnl=proceeds-p['cost'];cash+=proceeds
    trades.append({'symbol':s,'leg':p['leg'],'kind':p['kind'],'entry_time':p['time'],'exit_time':str(ts),'entry':p['entry'],'exit':fill,'qty':p['qty'],'pnl':pnl,'R':pnl/(p['qty']*(p['entry']-p['initial_stop'])),'reason':reason,'holding_sessions':p['age'],'tax_stress':wh});del pos[s];continue
   p['high']=max(p['high'],r.high)
   if p['high']>=p['entry']+(p['entry']-p['initial_stop']):p['stop']=max(p['stop'],p['high']-2*r.atr)
   if p['age']+1>=p['hold']:p['forced']='time_exit'
   elif p['leg']=='rsi2_reversion' and r.close>r.ma5:p['forced']='mean_reversion_exit'
  for s,r in rows.items():last[s]=r.close
  eq=cash+sum(p['qty']*last[s]*(1-c.slip)*(1-c.fee-(c.stock_tax if p['kind']=='stock' else 0)) for s,p in pos.items());peak=max(peak,eq)
  if eq<=peak*(1-c.drawdown_halt) or eq<=previous_eq*(1-c.daily_loss):halt=True;orders=[]
  curve.append({'timestamp':str(ts),'equity':eq,'positions':len(pos),'halt':halt,'regime':regime(m)});previous_eq=eq
  if not halt and (ts<end or not liquidate):
   candidates=[]
   for s,r in rows.items():
    if s in pos:continue
    z=make_signal(r,m,c.model,c)
    if z:candidates.append(z)
   candidates.sort(key=lambda z:(-z['rank'],z['symbol']));orders=candidates[:max(0,c.max_positions-len(pos))];audit['signals']+=len(candidates)
  last_market=m
 if not curve:raise ValueError('No data in evaluation window')
 t=pd.DataFrame(trades,columns=['symbol','leg','kind','entry_time','exit_time','entry','exit','qty','pnl','R','reason','holding_sessions','tax_stress']);e=pd.DataFrame(curve);v=np.r_[c.capital,e.equity];dd=v/np.maximum.accumulate(v)-1;win=t.loc[t.pnl>0,'pnl'].sum();loss=-t.loc[t.pnl<0,'pnl'].sum()
 report={'initial':c.capital,'final':float(e.equity.iloc[-1]),'return_pct':float((e.equity.iloc[-1]/c.capital-1)*100),'MDD_pct':float(dd.min()*100),'trades':len(t),'win_rate_pct':float((t.pnl>0).mean()*100) if len(t) else None,'profit_factor':float(win/loss) if loss else None,'mean_R':float(t.R.mean()) if len(t) else None,'average_holding_sessions':float(t.holding_sessions.mean()) if len(t) else None,'exposure_bar_pct':float((e.positions>0).mean()*100),'open_positions':len(pos),'config':asdict(c),'audit':dict(audit),'limitations':['Current stock listing survivorship bias; historical alerts and sectors unavailable','Daily-bar approximation; gap/VI/orderbook risks; missing held bars marked at last known price','Raw prices, cash dividends not credited; no independently cross-checked data','ETF derivative withholding stress not actual NAV-based tax','Stock sell tax fixed 0.20% assumption, not historical rate schedule','Permanent drawdown/daily-loss lock requires manual review; no real orders']}
 if not liquidate:
  fields=['qty','entry','stop','initial_stop','time','high','age','budget','kind','group','hold','forced','leg']
  report['paper_positions']={s:{k:p[k] for k in fields} for s,p in pos.items()}
  report['paper_next_orders']=[{**z,'signal_time':str(z['signal_time'])} for z in orders]
  report['paper_cash']=cash
  report['paper_halt']=halt
 return report,t,e
