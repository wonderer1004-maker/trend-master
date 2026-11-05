"""Causal close-time allocations. No strategy selection inside signal generation."""
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parent
RULES={
 'HOLD':'100% base; buy-and-hold, new deposits buy base',
 'LEV2_HOLD':'100% actual daily 2x ETF, risky reference',
 'STATIC125':'75% base +25% actual 2x ETF, monthly',
 'OLD_HYST150':'200MA +/-1%, 3 closes; exposure1.5 /0.5',
 'OLD_VOL20':'min(1.5,20%/20-day annualized vol); 5pp band',
 'NEW_TREND_ENSEMBLE':'mean(MA50/100/200 trend votes); exposure0.5+votes, cap by22% vol20',
 'NEW_MOM12_1':'monthly top5 positive 12-1 momentum stocks above MA200, equal weights; market MA200 filter',
 'OLD_MOM60_PORT':'20-session rotation, top5 positive60d momentum above MA200, 0.25%/2ATR risk weights',
 'OLD_BREAK20_CLOSE_PORT':'20d breakout, 2ATR close trailing stop/20-session hold, risk0.25%; close-only adaptation',
 'IMPROVED_MOM_CORE':'monthly top5 mean rank of 60d/126d/252d(skip21) momentum; 50% stock +50% base, cash substitutes missing stocks; bear:50% base',
 'IMPROVED_BREAK55_CORE':'55d breakout, 20d low or3ATR trailing close exits; max20-session hold; 50% base + up to50% stocks, residual in base',
 'NEW_CORE_ENSEMBLE':'equal average OLD_VOL20, IMPROVED_MOM_CORE, IMPROVED_BREAK55_CORE',
 'V8_HYST45_PORT':'existing scripts/trend_refined_v8.py HYST45 target; weekly plus regime changes; execution/risk wrapper replaced',
}
BENCHMARKS={'HOLD','LEV2_HOLD','STATIC125'}

def invalid(d):
    return d.isna().any(axis=1)|(d[['open','high','low','close']]<=0).any(axis=1)|(d.volume<=0)|(d.high+1e-7<d[['open','close']].max(axis=1))|(d.low-1e-7>d[['open','close']].min(axis=1))

def load(market,provider=None):
    folder=ROOT/'input'/('kr_yahoo' if provider=='yahoo' and market=='kr' else market)
    raw={};audit={}
    for p in sorted(folder.glob('*.csv.gz')):
      d=pd.read_csv(p,index_col=0,parse_dates=True);bad=invalid(d)
      audit[p.stem]=dict(invalid_removed=[str(x.date()) for x in d.index[bad]])
      raw[p.name.split('.')[0]+('.KS' if '.KS.' in p.name else '')]=d.loc[~bad]
    names=list(raw);calendar=raw[names[0]].index
    for d in raw.values():calendar=calendar.intersection(d.index)
    for s,d in raw.items():audit.setdefault(s,{})['not_in_common_calendar']=[str(x.date()) for x in d.index.difference(calendar)]
    return {s:d.loc[calendar] for s,d in raw.items()},audit

def features(data):
    f={}
    for s,d in data.items():
      x=d.copy();c=x.close
      for n in [5,20,50,100,150,200]:x[f'ma{n}']=c.rolling(n).mean()
      for n in [60,126,252]:x[f'm{n}']=c.shift(21)/c.shift(n)-1
      x['mom60']=c/c.shift(60)-1;x['vol20']=c.pct_change().rolling(20).std()*np.sqrt(252)
      tr=pd.concat([x.high-x.low,(x.high-c.shift()).abs(),(x.low-c.shift()).abs()],axis=1).max(axis=1)
      x['atr']=tr.rolling(14).mean()
      for n in [10,20,55]:x[f'h{n}']=x.high.shift().rolling(n).max();x[f'l{n}']=x.low.shift().rolling(n).min()
      f[s]=x
    return f

def exposure_weights(e,columns,base,lever,safe):
    w=np.zeros(len(columns));j=columns.index(base);k=columns.index(lever)
    if e<=1:
      w[j]=e
      if safe is not None:w[columns.index(safe)]=1-e
    else:w[j]=2-e;w[k]=e-1
    return w

def build(data,market,include_v8=True,base_override=None):
    names=list(data);ix=next(iter(data.values())).index;base='SPY' if market=='us' else '069500.KS';lever='SSO' if market=='us' else '122630.KS';safe='SHY' if market=='us' else None
    if base_override=='QQQ':base='QQQ';lever='QLD'
    # NASDAQ gets an independent base/lever index case in run.py.
    excluded={base,lever,'SHY','QQQ','QLD','SPY','SSO'};stocks=[s for s in names if s not in excluded];f=features(data);basef=f[base]
    out={m:np.zeros((len(ix),len(names))) for m in RULES if m!='V8_HYST45_PORT'}
    j=names.index(base);k=names.index(lever);out['HOLD'][:,j]=1;out['LEV2_HOLD'][:,k]=1;out['STATIC125'][:,j]=.75;out['STATIC125'][:,k]=.25
    lastvol=None;hyst=.5;oldmom=np.zeros(len(names));newmom=oldmom.copy();impmom=oldmom.copy();book_old={};book_new={}
    frames={s:list(x.itertuples()) for s,x in f.items()};nstock=min(5,len(stocks));counter=0;prior_month=None
    for i,date in enumerate(ix):
      r=frames[base][i]
      if not np.isfinite(r.ma200) or not np.isfinite(r.vol20):continue
      if i>=2:
        z=basef.iloc[i-2:i+1]
        if (z.close>z.ma200*1.01).all():hyst=1.5
        elif (z.close<z.ma200*.99).all():hyst=.5
      e=min(1.5,.20/r.vol20) if r.vol20>0 else 1.5
      if lastvol is None or abs(e-lastvol)>=.05:lastvol=e
      out['OLD_HYST150'][i]=exposure_weights(hyst,names,base,lever,safe)
      out['OLD_VOL20'][i]=exposure_weights(lastvol,names,base,lever,safe)
      votes=np.mean([r.close>r.ma50,r.close>r.ma100,r.close>r.ma200]);ee=min(.5+votes,.22/r.vol20) if r.vol20>0 else .5+votes
      out['NEW_TREND_ENSEMBLE'][i]=exposure_weights(ee,names,base,lever,safe)
      month=(date.year,date.month);monthly=month!=prior_month;prior_month=month
      bull=r.close>r.ma200
      sr={s:frames[s][i] for s in stocks}
      if counter%20==0:
        oldmom=np.zeros(len(names));rank=sorted([(rr.mom60,s) for s,rr in sr.items() if rr.close>rr.ma200 and rr.mom60>0 and rr.atr>0],reverse=True)[:nstock]
        for _,s in rank:oldmom[names.index(s)]=min(.2,.0025/(2*sr[s].atr/sr[s].close))
      if monthly:
        newmom=np.zeros(len(names));impmom=np.zeros(len(names));impmom[j]=.5
        ranks=sorted([(rr.m252,s) for s,rr in sr.items() if rr.close>rr.ma200 and rr.m252>0],reverse=True)[:nstock]
        if bull:
          for _,s in ranks:newmom[names.index(s)]=1/nstock
          vals=pd.DataFrame({s:[rr.m60,rr.m126,rr.m252] for s,rr in sr.items()}).T
          score=vals.rank(pct=True).mean(axis=1)
          eligible=[s for s,rr in sr.items() if rr.close>rr.ma200 and rr.m252>0 and rr.mom60>0]
          top=sorted(eligible,key=lambda s:(score[s],s),reverse=True)[:nstock]
          for s in top:impmom[names.index(s)]=.5/nstock
          # Explicit core fill: avoid cash drag from unused stock slots in bull regime.
          impmom[j]=1-impmom.sum()+impmom[j]
      # Exits on prior-close information, not an assumed intrabar stop.
      for model,book,window,atrmult,risk in [('OLD_BREAK20_CLOSE_PORT',book_old,20,2,.0025),('IMPROVED_BREAK55_CORE',book_new,55,3,.0075)]:
        removed=set()
        for s,p in list(book.items()):
          rr=sr[s];p['age']+=1;p['trail']=max(p['trail'],rr.close-atrmult*rr.atr)
          if rr.close<p['trail'] or rr.close<rr.l20 or rr.close<rr.ma200 or p['age']>=20:
            del book[s];removed.add(s)
        candidates=sorted([(rr.mom60,s) for s,rr in sr.items() if s not in book and s not in removed and rr.close>getattr(rr,'h'+str(window)) and rr.close>rr.ma200 and rr.atr>0],reverse=True)
        for _,s in candidates:
          if len(book)>=5:break
          rr=sr[s];book[s]=dict(age=0,trail=rr.close-atrmult*rr.atr,weight=min(.2,risk/(atrmult*rr.atr/rr.close)))
        w=np.zeros(len(names))
        for s,p in book.items():w[names.index(s)]=p['weight']
        if model.startswith('IMPROVED'):
          if w.sum()>.5:w*=.5/w.sum()
          w[j]=1-w.sum() if bull else .5
          if not bull:w[[names.index(s) for s in stocks]]=0
        out[model][i]=w
      out['OLD_MOM60_PORT'][i]=oldmom;out['NEW_MOM12_1'][i]=newmom;out['IMPROVED_MOM_CORE'][i]=impmom
      out['NEW_CORE_ENSEMBLE'][i]=(out['OLD_VOL20'][i]+out['IMPROVED_MOM_CORE'][i]+out['IMPROVED_BREAK55_CORE'][i])/3
      counter+=1
    if market=='kr' and include_v8:
      sys.path.insert(0,str(ROOT.parents[1]/'scripts'))
      import trend_refined_v8 as v8
      enriched=v8.enrich(data);w=np.zeros_like(out['HOLD']);current={};prior_regime=None
      for i,date in enumerate(ix):
        if date not in enriched[base].index:continue
        regime=v8.regime(enriched,date,'HYST45')
        # Existing target function reused directly; original simulator's stops/cooldowns
        # are intentionally not claimed as identical in this target-only port.
        if date.weekday()==4 or regime!=prior_regime or i==0:current=v8.target(enriched,date,'HYST45')
        for s,q in current.items():w[i,names.index(s)]=q
        prior_regime=regime
      out['V8_HYST45_PORT']=w
    for model,w in out.items():
      if not np.isfinite(w).all() or (w<0).any() or (w.sum(axis=1)>1.00000001).any():raise AssertionError('invalid allocation '+model)
      out[model]=pd.DataFrame(w,index=ix,columns=names)
    return out
