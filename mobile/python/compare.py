"""Fixed-rule quarterly evaluation and cost sensitivity; no parameter optimization."""
import argparse,json
from pathlib import Path
from dataclasses import replace
import pandas as pd
from engine import load,Config,backtest,save
p=argparse.ArgumentParser(); p.add_argument('--bars',required=True); p.add_argument('--index',required=True); p.add_argument('--daily',required=True); p.add_argument('--synthetic',action='store_true'); p.add_argument('--config',default='config.json'); p.add_argument('--out',default='reports/comparison'); a=p.parse_args()
b=load(a.bars); b.attrs['data_kind']='SYNTHETIC_SOFTWARE_TEST' if a.synthetic else 'USER_SUPPLIED_NOT_VERIFIED'; ix=load(a.index); d=load(a.daily,True); c=Config(**json.loads(Path(a.config).read_text(encoding='utf8'))); out=Path(a.out); rows=[]
for name,cfg,adaptive in [('adaptive',c,True),('without_market_filter',c,False),('double_slippage',replace(c,slip=c.slip*2),True),('tax_015',replace(c,sell_tax=.0015),True),('tax_020',replace(c,sell_tax=.002),True)]:
    result=backtest(b,ix,d,cfg,adaptive); save(result,out/name); rows.append({'variant':name,**{k:v for k,v in result[0].items() if k not in ['config','limitations']}})
for period,g in b.groupby(b.timestamp.dt.to_period('Q')):
    result=backtest(g,ix,d,c); save(result,out/str(period)); rows.append({'variant':str(period),**{k:v for k,v in result[0].items() if k not in ['config','limitations']}})
out.mkdir(parents=True,exist_ok=True); pd.DataFrame(rows).to_csv(out/'comparison.csv',index=False); print(out/'comparison.csv')
