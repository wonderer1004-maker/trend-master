"""Deliberately synthetic fixture: NEVER interpret as investment evidence."""
import numpy as np,pandas as pd,json
from pathlib import Path
from engine import Config,backtest,save
rng=np.random.default_rng(47); root=Path('data'); root.mkdir(exist_ok=True)
days=pd.bdate_range('2025-01-02',periods=270); daily=[]
for s in ['005930','000660','035420']:
    for i,d in enumerate(days):
        c=10000*(1.003**i); daily.append([d,s,c,c*1.005,c*.995,c,2_000_000])
cols=['timestamp','symbol','open','high','low','close','volume']; daily=pd.DataFrame(daily,columns=cols)
bars=[]; index=[]
for day in pd.bdate_range(days[-1]+pd.Timedelta(days=1),periods=12):
    for s in ['005930','000660','035420','INDEX']:
        c=22000.; hist=[]
        for n,ts in enumerate(pd.date_range(day+pd.Timedelta(hours=9),day+pd.Timedelta(hours=15,minutes=15),freq='5min')):
            o=c
            if s=='INDEX': change=.0004+rng.normal(0,.00015)
            else: change=.00045+rng.normal(0,.0016)
            if s!='INDEX' and n in [33,45,57]: change=.0025
            c=o*(1+change); spread=.0012
            v=800_000 if n in [33,45,57] else 150_000
            row=[ts,s,o,max(o,c)*(1+spread),min(o,c)*(1-spread),c,v]
            (index if s=='INDEX' else bars).append(row)
b=pd.DataFrame(bars,columns=cols); ix=pd.DataFrame(index,columns=cols)
for name,d in [('synthetic_bars',b),('synthetic_index',ix),('synthetic_daily',daily)]: d.to_csv(root/(name+'.csv'),index=False); d['day']=d.timestamp.dt.normalize()
b.attrs['data_kind']='SYNTHETIC_SOFTWARE_TEST'
for name,adaptive in [('synthetic_adaptive',True),('synthetic_no_market_filter',False)]:
    result=backtest(b,ix,daily,Config(),adaptive); save(result,'reports/'+name); print(name,json.dumps({k:v for k,v in result[0].items() if k not in ['config','limitations']}))
