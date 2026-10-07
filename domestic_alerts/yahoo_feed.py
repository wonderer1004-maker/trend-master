from urllib.request import Request,urlopen
from urllib.parse import urlencode
from datetime import datetime
from zoneinfo import ZoneInfo
import json,time
import pandas as pd

def parse_chart(payload,symbol):
 chart=payload.get('chart',{})
 if chart.get('error') or not chart.get('result'):raise ValueError('Yahoo chart error: '+symbol)
 r=chart['result'][0]
 if r['meta'].get('currency')!='KRW':raise ValueError('Not KRW: '+symbol)
 q=r['indicators']['quote'][0];rows=[]
 for i,t in enumerate(r.get('timestamp',[])):
  vals=[q[k][i] for k in ['open','high','low','close','volume']]
  if any(v is None for v in vals):continue
  day=datetime.fromtimestamp(t,ZoneInfo('Asia/Seoul')).date()
  rows.append([str(day),symbol,*vals])
 if not rows:raise ValueError('No Yahoo bars: '+symbol)
 return pd.DataFrame(rows,columns=['timestamp','symbol','open','high','low','close','volume'])

def download(symbols):
 frames=[]
 for symbol in symbols:
  error=None
  for attempt in range(3):
   try:
    url='https://query1.finance.yahoo.com/v8/finance/chart/'+symbol+'.KS?'+urlencode({'range':'2y','interval':'1d'})
    req=Request(url,headers={'User-Agent':'Mozilla/5.0'})
    with urlopen(req,timeout=20) as r:payload=json.load(r)
    frames.append(parse_chart(payload,symbol));break
   except Exception as e:
    error=e
    if attempt==2:raise RuntimeError('Yahoo download failed '+symbol+': '+str(error)) from e
    time.sleep(attempt+1)
  time.sleep(.4)
 return pd.concat(frames,ignore_index=True)
