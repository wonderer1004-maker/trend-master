"""Current KRX company universe + Yahoo 1mo/5m; conservative 14:55 liquidation variant."""
from pathlib import Path
from urllib.request import Request,urlopen
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime
import sys,json,time,re,traceback
import pandas as pd
sys.path.insert(0,str(Path('trend_master_daytrade').resolve()))
from engine import Config,daily_context,backtest,save
ROOT=Path('yahoo_kospi');CACHE=ROOT/'raw';CACHE.mkdir(parents=True,exist_ok=True)

if not Path('kospi_listing.csv').exists():
 from io import StringIO
 u='https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&marketType=stockMkt'
 with urlopen(Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=20) as r: html=r.read().decode('euc-kr',errors='replace')
 pd.read_html(StringIO(html))[0].to_csv('kospi_listing.csv',index=False)
listing=pd.read_csv('kospi_listing.csv',dtype={'종목코드':str});listing['symbol']=listing['종목코드'].str.zfill(6)
listing=listing[~listing['회사명'].str.contains('리츠|스팩|기업인수목적',regex=True)].copy();listing.to_csv(ROOT/'universe.csv',index=False)
log=[]
def fetch(ticker,interval):
 p=CACHE/(ticker.replace('^','INDEX_')+'_'+interval+'.json')
 if p.exists(): return json.loads(p.read_text())
 period='2y' if interval=='1d' else '1mo'
 error=None
 for trial in range(2):
  try:
   u=f'https://query2.finance.yahoo.com/v8/finance/chart/{ticker}?range={period}&interval={interval}&events=splits'
   with urlopen(Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=15) as r: data=json.load(r)
   if not data['chart'].get('result'): raise ValueError(str(data['chart'].get('error')))
   p.write_text(json.dumps(data)); return data
  except Exception as e: error=e;time.sleep(1+trial)
 raise RuntimeError(str(error))
def frame(data,symbol,daily=False):
 r=data['chart']['result'][0];q=r['indicators']['quote'][0];t=pd.to_datetime(r.get('timestamp',[]),unit='s',utc=True).tz_convert('Asia/Seoul').tz_localize(None)
 d=pd.DataFrame({k:q[k] for k in ['open','high','low','close','volume']});d['timestamp']=t;d['symbol']=symbol;d=d.dropna();d=d[(d.low>0)&(d.high>=d[['open','close']].max(axis=1))&(d.low<=d[['open','close']].min(axis=1))&(d.volume>=0)]
 if daily:d['timestamp']=d.timestamp.dt.normalize()
 d['day']=d.timestamp.dt.normalize();return d[['timestamp','symbol','open','high','low','close','volume','day']].drop_duplicates(['symbol','timestamp']).sort_values('timestamp')
def get_daily(row):
 s=row.symbol
 try:
  data=fetch(s+'.KS','1d');d=frame(data,s,True)
  if data['chart']['result'][0].get('events',{}).get('splits'):return s,None,'split_in_daily_history_excluded'
  return s,d,None
 except Exception as e:return s,None,str(e)
rows=list(listing.itertuples());daily=[];count=0
with ThreadPoolExecutor(max_workers=8) as ex:
 for fut in as_completed([ex.submit(get_daily,r) for r in rows]):
  s,d,error=fut.result();count+=1
  if d is not None:daily.append(d)
  log.append({'phase':'daily','symbol':s,'error':error,'bars':len(d) if d is not None else 0})
  if count%50==0: print(json.dumps({'daily_completed':count,'total':len(rows),'usable':len(daily)}),flush=True)
if not daily:raise RuntimeError('No Yahoo daily data')
daily=pd.concat(daily,ignore_index=True);daily.to_csv(ROOT/'daily.csv',index=False)
# Build candidate superset from any eligible day during recent evaluation horizon; not only latest day.
cfg=Config(flatten='14:55',strict=False)
ctx=daily_context(daily,cfg);cut=daily.day.max()-pd.Timedelta(days=45)
candidates=[s for s,h in ctx.items() if h.loc[h.day>=cut,'eligible'].any()]
print(json.dumps({'daily_symbols':daily.symbol.nunique(),'candidate_superset':len(candidates)}),flush=True)
index=frame(fetch('069500.KS','5m'),'069500')
now=pd.Timestamp.now(tz='Asia/Seoul').tz_localize(None)
def complete_sessions(d):
 groups=[];discard=[]
 for (s,day),g in d.groupby(['symbol','day']):
  g=g[(g.timestamp.dt.strftime('%H:%M')>='09:00')&(g.timestamp.dt.strftime('%H:%M')<='14:55')].sort_values('timestamp')
  expected=pd.date_range(day+pd.Timedelta(hours=9),day+pd.Timedelta(hours=14,minutes=55),freq='5min')
  if len(g)==72 and pd.DatetimeIndex(g.timestamp).equals(expected) and g.timestamp.iloc[-1]+pd.Timedelta(minutes=5)<=now:groups.append(g)
  else:discard.append({'symbol':s,'day':str(day.date()),'reason':'incomplete_09_00_to_14_55','bars':len(g)})
 return pd.concat(groups,ignore_index=True) if groups else pd.DataFrame(columns=d.columns),discard
index,discard=complete_sessions(index);log+=discard
if index.empty:raise RuntimeError('No complete benchmark sessions')
ixdays=set(index.day);bars=[]
def get_minute(s):
 try:return s,frame(fetch(s+'.KS','5m'),s),None
 except Exception as e:return s,None,str(e)
count=0
with ThreadPoolExecutor(max_workers=8) as ex:
 for fut in as_completed([ex.submit(get_minute,s) for s in candidates]):
  s,d,error=fut.result();count+=1
  if d is not None:
   d,discard=complete_sessions(d);log+=discard;d=d[d.day.isin(ixdays)]
   if not d.empty:bars.append(d)
  log.append({'phase':'minute','symbol':s,'error':error,'bars':len(d) if d is not None else 0})
  if count%20==0:print(json.dumps({'minute_completed':count,'total':len(candidates),'usable':len(bars)}),flush=True)
if not bars:raise RuntimeError('No complete candidate sessions')
bars=pd.concat(bars,ignore_index=True).sort_values(['symbol','timestamp']);bars.attrs['data_kind']='YAHOO_REAL_5M_CURRENT_KRX_COMPANY_UNIVERSE_14_55_EXIT_VARIANT'
bars.to_csv(ROOT/'bars.csv',index=False);index.to_csv(ROOT/'index.csv',index=False)
coverage={'source':'Yahoo Finance chart + KRX KIND corporate list','retrieved_at_kst':str(now),'listing_companies':846,'after_name_exclusions':len(listing),'daily_symbols':int(daily.symbol.nunique()),'candidate_superset':len(candidates),'minute_symbols':int(bars.symbol.nunique()),'start':str(bars.timestamp.min()),'end':str(bars.timestamp.max()),'sessions':int(bars.day.nunique()),'market_proxy':'069500.KS ETF; not KOSPI index','variant':'14:55 liquidation; original 15:15 data missing in Yahoo','limitations':['Current company listing, not all listed securities and not historical point-in-time universe','Survivorship bias; current listing only','Preferred shares/ETF/ETN mostly not in corporate listing, historical alerts/status not available','Split-history stocks excluded; data quality not independently cross-verified','Missing sessions dropped without imputation','Fee/tax constant scenario assumptions; no verified current statutory rates','No orderbook/VI/partial fills; 1% previous bar participation assumption']}
(ROOT/'coverage.json').write_text(json.dumps(coverage,ensure_ascii=False,indent=2));(ROOT/'download_log.json').write_text(json.dumps(log,ensure_ascii=False,indent=2))
from dataclasses import replace
results=[]
for name,c,adaptive in [('adaptive',cfg,True),('without_market_filter',cfg,False),('double_slippage',replace(cfg,slip=cfg.slip*2),True),('tax_015',replace(cfg,sell_tax=.0015),True)]:
 result=backtest(bars,index,daily,c,adaptive);save(result,ROOT/'reports'/name);results.append({'variant':name,**{k:v for k,v in result[0].items() if k not in ['config','limitations']}})
pd.DataFrame(results).to_csv(ROOT/'comparison.csv',index=False)
print(json.dumps({'coverage':coverage,'results':results},ensure_ascii=False),flush=True)
