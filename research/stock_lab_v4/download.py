"""Frozen Yahoo snapshots. Daily adjusted OHLC; intraday raw OHLC, regular sessions only."""
import concurrent.futures,gzip,hashlib,json,time,urllib.request
from pathlib import Path
from datetime import datetime,timezone
import pandas as pd
ROOT=Path(__file__).resolve().parent
US='AAPL MSFT AMZN GOOGL META NVDA AMD INTC CSCO ORCL IBM JPM BAC XOM CVX WMT KO PEP JNJ PFE'.split()
KR='005930.KS 000660.KS 005380.KS 035420.KS 005490.KS 051910.KS 068270.KS 006400.KS 012330.KS 055550.KS'.split()
def fetch(s,m,kind):
    query='range=60d&interval=5m&includePrePost=false' if kind=='5m' else 'period1=1483228800&period2=1792195200&interval=1d&events=div%2Csplits'
    url=f'https://query2.finance.yahoo.com/v8/finance/chart/{s}?{query}'
    for attempt in range(3):
      try:
        raw=urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=25).read()
        j=json.loads(raw)['chart']['result'][0];q=j['indicators']['quote'][0]
        ix=pd.to_datetime(j['timestamp'],unit='s',utc=True).tz_convert(j['meta']['exchangeTimezoneName']).tz_localize(None)
        if kind=='1d':ix=ix.normalize()
        d=pd.DataFrame(q,index=ix)[['open','high','low','close','volume']]
        if kind=='1d':
          ratio=pd.Series(j['indicators']['adjclose'][0]['adjclose'],index=ix)/d.close
          d.loc[:,['open','high','low','close']]=d[['open','high','low','close']].mul(ratio,axis=0)
        bad=d.isna().any(axis=1)|(d[['open','high','low','close']]<=0).any(axis=1)
        omitted=[str(x) for x in ix[bad]];d=d.loc[~bad];d=d[~d.index.duplicated()].sort_index();d=d.loc[:'2026-10-16 23:59:59']
        if d.empty:raise ValueError('empty')
        b=d.to_csv(index_label='date').encode();p=ROOT/'input'/m/f'{s}_{kind}.csv.gz';p.write_bytes(gzip.compress(b,mtime=0))
        return dict(symbol=s,market=m,kind=kind,rows=len(d),first=str(d.index[0]),last=str(d.index[-1]),url=url,omitted=omitted,sha256=hashlib.sha256(b).hexdigest(),raw_sha256=hashlib.sha256(raw).hexdigest(),retrieved=datetime.now(timezone.utc).isoformat())
      except Exception as e:
        error=str(e);time.sleep(.3)
    return dict(symbol=s,market=m,kind=kind,error=error)
def main():
    jobs=[(s,m,'1d') for m,ss in [('us',US+['SPY','QQQ']),('kr',KR+['069500.KS'])] for s in ss]+[(s,m,'5m') for m,ss in [('us',US[:10]),('kr',KR)] for s in ss]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
      out=list(ex.map(lambda x:fetch(*x),jobs))
    (ROOT/'input'/'provenance.json').write_text(json.dumps(out,indent=2))
    print(json.dumps([{k:v for k,v in x.items() if k in ['symbol','market','kind','rows','first','last','error']} for x in out]))
if __name__=='__main__':main()
