"""Download adjusted daily OHLC with raw response hashes; never synthesize missing data."""
import concurrent.futures
import hashlib
import gzip
import json
import time
import urllib.request
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd

US=['SPY','QQQ','SHY','SSO','QLD']
KR=['069500.KS','122630.KS','229200.KS','233740.KS']
ROOT=Path(__file__).resolve().parent

def fetch(symbol,market):
    start='2007-01-01'
    p1=int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp())
    p2=int(datetime(2026,10,17,tzinfo=timezone.utc).timestamp())
    errors=[]
    for host in ['query2.finance.yahoo.com','query1.finance.yahoo.com']:
        try:
            url=f'https://{host}/v8/finance/chart/{symbol}?period1={p1}&period2={p2}&interval=1d&events=div%2Csplits'
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
            with urllib.request.urlopen(req,timeout=20) as r: blob=r.read()
            j=json.loads(blob)['chart']['result'][0]
            q=j['indicators']['quote'][0];adj=j['indicators']['adjclose'][0]['adjclose']
            tz=j['meta']['exchangeTimezoneName']
            idx=pd.to_datetime(j['timestamp'],unit='s',utc=True).tz_convert(tz).tz_localize(None).normalize()
            d=pd.DataFrame(q,index=idx)[['open','high','low','close','volume']]
            ratio=pd.Series(adj,index=idx)/d.close
            d.loc[:,['open','high','low','close']]=d[['open','high','low','close']].mul(ratio,axis=0)
            bad=d.isna().any(axis=1)|(d[['open','high','low','close']]<=0).any(axis=1)
            omitted=[str(z.date()) for z in d.index[bad]];d=d.loc[~bad].sort_index()
            d=d.loc[:'2026-10-16']
            if d.index.has_duplicates or len(d)<500:raise ValueError('invalid or insufficient history')
            target=ROOT/'input'/market/(symbol+'.csv');d.to_csv(target,index_label='date')
            target.with_suffix('.csv.gz').write_bytes(gzip.compress(target.read_bytes(),mtime=0))
            meta=dict(symbol=symbol,market=market,source=url,retrieved_at=datetime.now(timezone.utc).isoformat(),
              raw_response_sha256=hashlib.sha256(blob).hexdigest(),csv_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
              first=str(d.index[0].date()),last=str(d.index[-1].date()),rows=len(d),omitted_nan_sessions=omitted,
              adjustment='Yahoo adjclose/close ratio applied to OHLC; volume unchanged; cash dividends not separately reinvested')
            return meta
        except Exception as e: errors.append(f'{host}: {type(e).__name__}: {e}')
    return dict(symbol=symbol,market=market,error=errors)

def main():
    (ROOT/'input'/'us').mkdir(exist_ok=True);(ROOT/'input'/'kr').mkdir(exist_ok=True)
    jobs=[(s,'us') for s in US]+[(s,'kr') for s in KR]
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        futures=[ex.submit(fetch,s,m) for s,m in jobs]
        for f in concurrent.futures.as_completed(futures):
            r=f.result();results.append(r);print(json.dumps(r,ensure_ascii=False),flush=True)
    (ROOT/'input'/'provenance.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    if any('error' in x for x in results):raise RuntimeError('download failures recorded; do not substitute data')
if __name__=='__main__':main()
