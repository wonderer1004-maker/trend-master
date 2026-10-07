"""Completed-bar signals; next-bar fills; long-only, cash portfolio, KRX session."""
from dataclasses import dataclass, asdict
from pathlib import Path
import json
import numpy as np
import pandas as pd

@dataclass
class Config:
    capital: float = 1_000_000
    risk: float = .003
    neutral_risk: float = .0015
    max_weight: float = .20
    max_positions: int = 3
    daily_loss: float = .015
    fee: float = .00015
    sell_tax: float = .002  # scenario assumption, NOT verified current statutory rate
    slip: float = .001
    participation: float = .01
    min_daily_turnover: float = 5_000_000_000
    volume_ratio: float = 1.5
    atr_multiple: float = 1.5
    trail_multiple: float = 2.5
    entry_start: str = '09:30'
    entry_end: str = '14:00'
    flatten: str = '15:15'
    strict: bool = True


def load(path, daily=False):
    d = pd.read_csv(path, dtype={'symbol':str})
    req = ['timestamp','symbol','open','high','low','close','volume']
    if any(c not in d for c in req):
        raise ValueError('Required columns: '+','.join(req))
    d['timestamp'] = pd.to_datetime(d.timestamp)
    if d.timestamp.dt.tz is not None:
        d['timestamp'] = d.timestamp.dt.tz_convert('Asia/Seoul').dt.tz_localize(None)
    for c in req[2:]: d[c] = pd.to_numeric(d[c], errors='raise')
    if d[req].isna().any().any() or d.duplicated(['symbol','timestamp']).any():
        raise ValueError('Missing values or duplicate bars')
    if ((d.low > d[['open','close']].min(axis=1)) | (d.high < d[['open','close']].max(axis=1)) | (d.low<=0) | (d.volume<0)).any():
        raise ValueError('Invalid OHLCV')
    if not daily and ((d.timestamp.dt.minute%5 != 0) | (d.timestamp.dt.second!=0)).any():
        raise ValueError('Use 5-minute bar START timestamps')
    d['day'] = d.timestamp.dt.normalize()
    return d.sort_values(['symbol','timestamp']).reset_index(drop=True)


def daily_context(d, cfg):
    result = {}
    for s,g in d.groupby('symbol',sort=True):
        g=g.sort_values('timestamp').copy()
        if g.day.duplicated().any(): raise ValueError('Daily data contains duplicate session')
        c=g.close; ma50=c.rolling(50).mean(); ma150=c.rolling(150).mean(); ma200=c.rolling(200).mean()
        good=(c>ma50)&(ma50>ma150)&(ma150>ma200)&(ma200>ma200.shift(20))&(c>=c.rolling(252).max()*.75)
        liquid=(c*g.volume).rolling(20).mean()>=cfg.min_daily_turnover
        result[s]=pd.DataFrame({'day':g.day.values,'eligible':(good&liquid).values})
    return result


def features(d):
    out=[]
    for (s,day),g in d.groupby(['symbol','day'],sort=True):
        g=g.copy(); c=g.close; prev=c.shift()
        tr=pd.concat([g.high-g.low,(g.high-prev).abs(),(g.low-prev).abs()],axis=1).max(axis=1)
        g['atr']=tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
        typical=(g.high+g.low+c)/3
        g['vwap']=(typical*g.volume).cumsum()/g.volume.cumsum().replace(0,np.nan)
        g['ema20']=c.ewm(span=20,adjust=False,min_periods=20).mean()
        g['ema50']=c.ewm(span=50,adjust=False,min_periods=30).mean()
        delta=c.diff(); up=delta.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean(); down=(-delta.clip(upper=0)).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
        g['rsi']=100-100/(1+up/down.replace(0,np.nan)); g.loc[(down==0)&(up>0),'rsi']=100
        g['pivot']=g.high.shift().rolling(6).max()
        g['vr']=g.volume/g.volume.shift().rolling(20).mean().replace(0,np.nan)
        g['signal']=(c>g['pivot'])&(prev<=g['pivot'])&(c>g.vwap)&(g.ema20>g.ema50)&g.rsi.between(55,75)&((c-g['pivot'])<=.5*g.atr)
        g['ret']=c/c.iloc[0]-1
        g['ready']=g.atr.notna()&g.ema50.notna()
        out.append(g)
    return pd.concat(out).sort_values(['timestamp','symbol']).reset_index(drop=True)


def regime(r):
    if r is None or not r.ready: return 'BEAR'
    if r.close>r.vwap and r.ema20>r.ema50: return 'BULL'
    if r.close<r.vwap and r.ema20<r.ema50: return 'BEAR'
    return 'NEUTRAL'


def backtest(bars, index, daily, cfg=Config(), adaptive=True):
    if cfg.strict:
        for _,g in bars.groupby(['symbol','day']):
            expected=pd.date_range(g.day.iloc[0]+pd.Timedelta(hours=9),g.day.iloc[0]+pd.Timedelta(hours=15,minutes=15),freq='5min')
            if not expected.equals(pd.DatetimeIndex(g.timestamp)):
                raise ValueError('Strict mode requires complete KRX 09:00–15:15 bars per symbol/session')
    f=features(bars); ix=features(index)
    if ix.symbol.nunique()!=1: raise ValueError('Index input needs exactly one benchmark/proxy')
    ix=ix.set_index('timestamp'); ctx=daily_context(daily,cfg)
    cash=cfg.capital; pos={}; pending={}; trades=[]; curve=[]; last={}; current_day=None; halt=False
    for ts,g in f.groupby('timestamp',sort=True):
        if ts.normalize()!=current_day:
            if pos: raise ValueError('Overnight position: missing liquidation bar')
            current_day=ts.normalize(); day_start=cash; halt=False; pending={}; used=set()
        rows={r.symbol:r for r in g.itertuples()}; clock=ts.strftime('%H:%M')
        # Pending orders derive only from the immediately preceding COMPLETED bar.
        for s,p in list(pending.items()):
            del pending[s]
            if s not in rows or ts!=p['ts']+pd.Timedelta(minutes=5) or halt or clock>=cfg.flatten: continue
            r=rows[s]; fill=r.open*(1+cfg.slip)
            if fill>p['pivot']+.75*p['atr'] or fill<=p['stop']: continue
            distance=fill-p['stop']
            if not .003<=distance/fill<=.02: continue
            eq=cash+sum(x['qty']*last[k] for k,x in pos.items())
            risk=cfg.risk if p['regime']=='BULL' else cfg.neutral_risk
            # Participation uses PREVIOUS bar volume, avoiding current-bar volume lookahead.
            q=int(min(eq*risk/(distance+fill*(2*cfg.fee+cfg.sell_tax+cfg.slip)),eq*cfg.max_weight/fill,cash/(fill*(1+cfg.fee)),p['volume']*cfg.participation))
            if q<1 or len(pos)>=cfg.max_positions: continue
            cash-=q*fill*(1+cfg.fee)
            pos[s]={'qty':q,'entry':fill,'stop':p['stop'],'initial_stop':p['stop'],'high':fill,'time':str(ts),'cost':q*fill*(1+cfg.fee)}; used.add(s)
        for s,r in rows.items():
            last[s]=r.close
            if s not in pos: continue
            p=pos[s]; reason=None; price=None
            # Existing stop gets tested before this bar may raise it.
            if r.open<=p['stop']: price=r.open; reason='gap_stop'
            elif halt or clock>=cfg.flatten: price=r.open; reason='day_exit' if not halt else 'daily_loss_exit'
            elif r.low<=p['stop']: price=p['stop']; reason='stop'
            if price is not None:
                fill=price*(1-cfg.slip); proceeds=p['qty']*fill*(1-cfg.fee-cfg.sell_tax); pnl=proceeds-p['cost']; cash+=proceeds
                trades.append({'symbol':s,'entry_time':p['time'],'exit_time':str(ts),'entry':p['entry'],'exit':fill,'qty':p['qty'],'pnl':pnl,'R':pnl/(p['qty']*(p['entry']-p['initial_stop'])),'reason':reason}); del pos[s]
            elif pd.notna(r.atr):
                p['high']=max(p['high'],r.high); p['stop']=max(p['stop'],p['high']-cfg.trail_multiple*r.atr)
        eq=cash+sum(p['qty']*last[s]*(1-cfg.fee-cfg.sell_tax) for s,p in pos.items())
        if eq<=day_start*(1-cfg.daily_loss): halt=True; pending={}
        curve.append({'timestamp':str(ts),'equity':eq,'halt':halt})
        # Index state at this bar close is only used for next bar entry.
        reg=regime(ix.loc[ts]) if ts in ix.index else 'BEAR'
        if not adaptive: reg='BULL'
        if halt or reg=='BEAR' or not cfg.entry_start<=clock<cfg.entry_end: continue
        candidates=[]
        for s,r in rows.items():
            history=ctx.get(s)
            if history is None: continue
            past=history[history.day<current_day]
            if past.empty or not bool(past.eligible.iloc[-1]): continue
            if s in used or s in pos or not r.signal or r.vr<cfg.volume_ratio: continue
            if adaptive and reg=='NEUTRAL' and r.vr<2: continue
            candidates.append(r)
        candidates.sort(key=lambda r:(-r.vr,r.symbol))
        for r in candidates[:max(0,cfg.max_positions-len(pos))]:
            pending[r.symbol]={'ts':ts,'pivot':r.pivot,'atr':r.atr,'stop':r.close-cfg.atr_multiple*r.atr,'regime':reg,'volume':r.volume}
    if pos: raise ValueError('Incomplete data left open positions')
    t=pd.DataFrame(trades,columns=['symbol','entry_time','exit_time','entry','exit','qty','pnl','R','reason']); e=pd.DataFrame(curve)
    if e.empty: raise ValueError('No bars')
    vals=np.r_[cfg.capital,e.equity.to_numpy()]; dd=vals/np.maximum.accumulate(vals)-1
    gains=t.loc[t.pnl>0,'pnl'].sum(); losses=-t.loc[t.pnl<0,'pnl'].sum()
    report={'data_kind':bars.attrs.get('data_kind','USER_SUPPLIED_NOT_VERIFIED'),'initial':cfg.capital,'final':float(e.equity.iloc[-1]),'return_pct':float((e.equity.iloc[-1]/cfg.capital-1)*100),'MDD_pct':float(dd.min()*100),'trades':len(t),'win_rate_pct':float((t.pnl>0).mean()*100) if len(t) else None,'profit_factor':float(gains/losses) if losses else None,'mean_R':float(t.R.mean()) if len(t) else None,'config':asdict(cfg),'limitations':['Bar execution approximation; no orderbook, VI or partial fills','Fees/tax/slippage are configurable assumptions','No verified market-data or real-order performance']}
    return report,t,e


def save(result,folder):
    p=Path(folder); p.mkdir(parents=True,exist_ok=True); report,t,e=result
    (p/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8'); t.to_csv(p/'trades.csv',index=False); e.to_csv(p/'equity.csv',index=False)
