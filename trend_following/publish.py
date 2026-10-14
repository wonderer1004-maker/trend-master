"""Completed-session model states, never brokerage orders."""
import argparse, datetime as dt, json, time, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd
import exchange_calendars as xc

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/trend-following/data/latest.json'
MARKETS={
 'KR':dict(calendar='XKRX',currency='KRW',start='2015-01-01',strategy='BLEND',symbols={'069500':'KODEX 200','091160':'KODEX 반도체','139260':'TIGER 200 IT','091170':'KODEX 은행','102970':'KODEX 증권','091180':'KODEX 자동차'}),
 'US':dict(calendar='XNYS',currency='USD',start='2002-01-01',strategy='BREAK120',symbols={'SPY':'S&P 500','IWM':'미국 소형주','XLK':'기술','XLF':'금융','XLE':'에너지','XLV':'헬스케어'})}

def get(url):
    for attempt in range(3):
        try:
            return urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=35).read()
        except Exception:
            if attempt==2:raise
            time.sleep(attempt+1)

def completed_session(market,now):
    # Calendar determines holidays and half days; allow 20 min for vendor publication.
    cal=xc.get_calendar(MARKETS[market]['calendar'],start=str(now.date()-dt.timedelta(days=40)),end=str(now.date()+dt.timedelta(days=20)))
    sessions=cal.sessions
    done=[s for s in sessions if cal.session_close(s)+pd.Timedelta(minutes=20)<=now]
    if not done:raise ValueError('No completed market session')
    last=done[-1];nxt=cal.next_session(last)
    return str(last.date()),str(nxt.date())

def fetch_symbol(market,symbol,cutoff):
    if market=='KR':
        raw=get(f'https://fchart.stock.naver.com/sise.nhn?symbol={symbol}&timeframe=day&count=4000&requestType=0')
        rows=[x.attrib['data'].split('|') for x in ET.fromstring(raw.decode('euc-kr')).iter('item')]
        d=pd.DataFrame(rows,columns=['date','open','high','low','close','volume']);d.index=pd.to_datetime(d.pop('date'),format='%Y%m%d');d=d.astype(float)
        factor=pd.Series(1.,index=d.index)
    else:
        end=int((pd.Timestamp(cutoff,tz='UTC')+pd.Timedelta(days=2)).timestamp())
        z=json.loads(get(f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1=915148800&period2={end}&interval=1d&events=div%2Csplits'))['chart']['result'][0]
        idx=pd.to_datetime(z['timestamp'],unit='s',utc=True).tz_convert('America/New_York').tz_localize(None).normalize()
        d=pd.DataFrame(z['indicators']['quote'][0],index=idx)[['open','high','low','close','volume']]
        factor=pd.Series(z['indicators']['adjclose'][0]['adjclose'],index=idx)/d.close
    d=d.loc[:cutoff].copy();factor=factor.reindex(d.index)
    if len(d)<260 or d.index.has_duplicates or d.isna().any().any() or not (d>0).all().all() or not np.isfinite(factor).all() or not (factor>0).all():raise ValueError(f'{symbol}: invalid/incomplete history')
    if str(d.index[-1].date())!=cutoff:raise ValueError(f'{symbol}: latest bar not available ({d.index[-1].date()} != {cutoff})')
    top=d[['open','close']].max(axis=1);bottom=d[['open','close']].min(axis=1)
    repairs=(top>d.high+1e-5)|(bottom<d.low-1e-5)
    if market=='KR':
        if ((top-d.high)/d.close>=.001).any() or ((d.low-bottom)/d.close>=.001).any():raise ValueError(f'{symbol}: OHLC inconsistency')
        d.high=np.maximum(d.high,top);d.low=np.minimum(d.low,bottom)
    elif repairs.any():raise ValueError(f'{symbol}: OHLC inconsistency')
    current_factor=float(factor.iloc[-1]);rawclose=float(d.close.iloc[-1])
    d.loc[:,['open','high','low','close']]=d[['open','high','low','close']].mul(factor,axis=0)
    return symbol,d,current_factor,rawclose,int(repairs.sum())

def model_rows(data,market,next_session):
    cfg=MARKETS[market];symbols=list(cfg['symbols']);idx=data[symbols[0]][0].index
    # Allow different inception dates, but never silently remove internal missing days.
    first=max(data[s][0].index[0] for s in symbols)
    ds={s:data[s][0].loc[first:] for s in symbols};idx=ds[symbols[0]].index
    if not all(d.index.equals(idx) for d in ds.values()):raise ValueError('ETF trading dates differ')
    c=pd.DataFrame({s:d.close for s,d in ds.items()});h=pd.DataFrame({s:d.high for s,d in ds.items()});l=pd.DataFrame({s:d.low for s,d in ds.items()})
    vol=c.pct_change().rolling(60).std(ddof=1)*np.sqrt(252)
    up=[c>h.rolling(60).max().shift(),c>h.rolling(120).max().shift(),c.rolling(50).mean()>c.rolling(200).mean()]
    dn=[c<l.rolling(20).min().shift(),c<l.rolling(60).min().shift(),c.rolling(50).mean()<c.rolling(200).mean()]
    state=np.zeros((3,len(symbols)),bool);cap=np.zeros(len(symbols));target=np.zeros(len(symbols));oldscore=np.zeros(len(symbols))
    ids=np.flatnonzero(idx>=cfg['start']);begin=max(0,ids[0]-1);before=np.zeros(len(symbols));prevstate=state.copy()
    for i in range(begin,len(idx)):
        before=target.copy();prevstate=state.copy()
        for j in range(3):state[j]=np.where(dn[j].iloc[i],False,np.where(up[j].iloc[i],True,state[j]))
        score=state.mean(axis=0) if cfg['strategy']=='BLEND' else state[1].astype(float)
        following=idx[i+1] if i+1<len(idx) else pd.Timestamp(next_session)
        weekly=idx[i].to_period('W-FRI')!=following.to_period('W-FRI')
        if i==begin or weekly:
            v=vol.iloc[i].to_numpy();inv=1/v
            if not np.isfinite(inv).all():raise ValueError('Insufficient volatility warm-up')
            cap=np.minimum(.2,inv/inv.sum());target=cap*score
        else:
            changed=np.abs(score-oldscore)>1e-12;target[changed]=cap[changed]*score[changed]
        oldscore=score.copy()
    rows=[]
    for j,s in enumerate(symbols):
        d=ds[s];factor,rawclose,repairs=data[s][1:]
        delta=float(target[j]-before[j]);action='INCREASE' if delta>1e-8 else 'DECREASE' if delta<-1e-8 else 'HOLD' if target[j]>0 else 'CASH'
        rows.append(dict(symbol=s,name=cfg['symbols'][s],close=rawclose,date=str(idx[-1].date()),target_weight=float(target[j]),previous_weight=float(before[j]),allocation_cap=float(cap[j]),action=action,active=state[:,j].tolist(),previous_active=prevstate[:,j].tolist(),volatility=float(vol.iloc[-1,j]),entry60=float(d.high.tail(60).max()/factor),exit20=float(d.low.tail(20).min()/factor),entry120=float(d.high.tail(120).max()/factor),exit60=float(d.low.tail(60).min()/factor),ma50=float(d.close.tail(50).mean()/factor),ma200=float(d.close.tail(200).mean()/factor),repairs=repairs,history=[dict(date=str(k.date()),close=float(v/factor)) for k,v in d.close.tail(120).items()]))
    return rows

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--now');args=parser.parse_args();now=pd.Timestamp(args.now) if args.now else pd.Timestamp.now(tz='UTC')
    if now.tzinfo is None:raise ValueError('--now requires timezone')
    old=json.loads(OUT.read_text()) if OUT.exists() else {'markets':{}}
    result={'schema':1,'generated_at':now.isoformat(),'order_execution':False,'markets':{}}
    for market,cfg in MARKETS.items():
        try:
            cutoff,nxt=completed_session(market,now)
            with ThreadPoolExecutor(max_workers=3) as pool:items=list(pool.map(lambda s:fetch_symbol(market,s,cutoff),cfg['symbols']))
            data={s:(d,f,raw,repairs) for s,d,f,raw,repairs in items}
            rows=model_rows(data,market,nxt)
            result['markets'][market]=dict(status='ok',asof=cutoff,next_session=nxt,currency=cfg['currency'],strategy=cfg['strategy'],rows=rows,source='Naver 가격수익' if market=='KR' else 'Yahoo 분배금 반영 근사',cash_target=1-sum(r['target_weight'] for r in rows),checked_at=now.isoformat())
        except Exception as ex:
            entry=old.get('markets',{}).get(market,{}).copy();entry.update(status='error',error=str(ex)[:240],checked_at=now.isoformat());result['markets'][market]=entry
            print(f'{market}: refresh blocked: {ex}',flush=True)
    OUT.parent.mkdir(parents=True,exist_ok=True);tmp=OUT.with_suffix('.tmp');tmp.write_text(json.dumps(result,ensure_ascii=False,allow_nan=False));tmp.replace(OUT)
    for m,x in result['markets'].items():print(m,x.get('status'),x.get('asof'))

if __name__=='__main__':main()
