from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import sys,json,argparse
import pandas as pd
P=Path(__file__).resolve().parent;sys.path.insert(0,str(P/'engine'))
import quant_portfolio as strategy
from yahoo_feed import download

def build(d,now=None):
 now=now or datetime.now(ZoneInfo('Asia/Seoul'));today=pd.Timestamp(now.date());meta=json.loads((P/'metadata.json').read_text());d=d.copy();d['timestamp']=pd.to_datetime(d.timestamp);d.symbol=d.symbol.astype(str).str.zfill(6)
 d=d[d.timestamp<=today] if (now.hour,now.minute)>=(16,10) else d[d.timestamp<today]
 if d.duplicated(['timestamp','symbol']).any():raise ValueError('duplicate bars')
 ix=d[d.symbol=='069500'];end=ix.timestamp.max()
 if pd.isna(end) or (today-end).days>7:raise ValueError('missing/stale index')
 for s in meta:
  g=d[d.symbol==s]
  if len(g)<60 or set(g.timestamp)!=set(ix.timestamp):raise ValueError('missing ETF/date '+s)
  if g[['open','high','low','close','volume']].isna().any().any() or (g[['open','high','low','close']]<=0).any().any() or (g.volume<0).any() or (g.high<g[['open','low','close']].max(axis=1)).any() or (g.low>g[['open','high','close']].min(axis=1)).any():raise ValueError('invalid bars')
 f=strategy.prepare(d,meta);market=f[f.symbol=='069500'].set_index('timestamp');cfg=strategy.QuantConfig(model='etf_rotation');events=[];data={}
 for s in meta:
  g=f[f.symbol==s];bars=[]
  for r in g.itertuples():
   if pd.isna(r.atr) or pd.isna(market.loc[r.timestamp].ma60):continue
   bars.append({'date':str(r.timestamp.date()),'o':float(r.open),'h':float(r.high),'l':float(r.low),'c':float(r.close),'atr':float(r.atr),'regime':strategy.regime(market.loc[r.timestamp])})
  r=g.iloc[-1];z=strategy.make_signal(r,market.loc[end],'etf_rotation',cfg)
  if z:events.append({'symbol':s,'stop':z['stop'],'ceiling':z['ceiling'],'rank':z['rank'],'volume':float(z['volume'])})
  data[s]={'name':meta[s]['name'],'group':meta[s]['group'],'bars':bars,'metrics':{'close':float(r.close),'ma20':float(r.ma20),'ma60':float(r.ma60),'return20_pct':float(r.r20*100),'turnover20':float(r.turnover20),'atr14':float(r.atr),'volume':float(r.volume),'signal_stop':float(r.close-2*r.atr),'entry_ceiling':float(r.close+.5*r.atr)}}
 return {'schema':1,'source':'Yahoo Finance daily chart / unadjusted OHLC','generated_at':now.isoformat(),'as_of':str(end.date()),'regime':strategy.regime(market.loc[end]),'candidates':sorted(events,key=lambda z:(-z['rank'],z['symbol'])),'instruments':data}

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--csv');a=p.parse_args();meta=json.loads((P/'metadata.json').read_text());d=pd.read_csv(a.csv,dtype={'symbol':str}) if a.csv else download(sorted(meta));result=build(d);target=P.parent/'docs/domestic-alerts/market.json';target.write_text(json.dumps(result,ensure_ascii=False,allow_nan=False,separators=(',',':')));print('Published data',result['as_of'],result['regime'],len(result['candidates']))
