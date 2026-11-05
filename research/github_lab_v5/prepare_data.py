"""Collect independent Korean price-only snapshots and retain prior Yahoo controls."""
from pathlib import Path
import concurrent.futures,gzip,hashlib,json,urllib.request,xml.etree.ElementTree as ET
import pandas as pd
ROOT=Path(__file__).resolve().parent;REPO=ROOT.parents[1]
STOCK_US='AAPL MSFT AMZN GOOGL META NVDA AMD INTC CSCO ORCL IBM JPM BAC XOM CVX WMT KO PEP JNJ PFE'.split()
STOCK_KR='005930.KS 000660.KS 005380.KS 035420.KS 005490.KS 051910.KS 068270.KS 006400.KS 012330.KS 055550.KS'.split()
def copy_old(s,market):
    old=REPO/'research'/'stock_lab_v4'/'input'/market/f'{s}_1d.csv.gz'
    if not old.exists():old=REPO/'research'/'index_challenge_v3'/'input'/market/f'{s}.csv.gz'
    dest=ROOT/'input'/('us' if market=='us' else 'kr_yahoo')/f'{s}.csv.gz';dest.write_bytes(old.read_bytes())
    return dict(symbol=s,market=market,provider='Yahoo previously frozen',source_file=str(old.relative_to(REPO)),csv_sha256=hashlib.sha256(gzip.decompress(old.read_bytes())).hexdigest())
def naver(s):
    u=f'https://fchart.stock.naver.com/sise.nhn?symbol={s.split(".")[0]}&timeframe=day&count=3000&requestType=0'
    b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=30).read();root=ET.fromstring(b.decode('euc-kr').split('?>',1)[1])
    rows=[x.attrib['data'].split('|') for x in root.iter('item')];d=pd.DataFrame(rows,columns=['date','open','high','low','close','volume'])
    d['date']=pd.to_datetime(d.date,format='%Y%m%d');d=d.set_index('date').astype(float).sort_index().loc['2017-01-01':'2026-10-16']
    out=d.to_csv().encode();(ROOT/'input'/'kr'/f'{s}.csv.gz').write_bytes(gzip.compress(out,mtime=0))
    return dict(symbol=s,provider='Naver fchart',market='kr',url=u,raw_sha256=hashlib.sha256(b).hexdigest(),csv_sha256=hashlib.sha256(out).hexdigest(),rows=len(d),first=str(d.index[0].date()),last=str(d.index[-1].date()),return_basis='provider historical prices; no cash distributions; not guaranteed total return')
def main():
    meta=[copy_old(s,'us') for s in STOCK_US+['SPY','QQQ','SSO','QLD','SHY']]
    kr=STOCK_KR+['069500.KS','122630.KS'];meta += [copy_old(s,'kr') for s in kr]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:meta+=list(ex.map(naver,kr))
    (ROOT/'input'/'manifest.json').write_text(json.dumps(meta,indent=2));print(json.dumps({'snapshots':len(meta),'naver_rows':[(x['symbol'],x['rows']) for x in meta if x['provider']=='Naver fchart']}))
if __name__=='__main__':main()
