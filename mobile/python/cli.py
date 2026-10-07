import argparse,json
from pathlib import Path
from engine import Config,load,backtest,save
p=argparse.ArgumentParser(); p.add_argument('--bars',required=True); p.add_argument('--index',required=True); p.add_argument('--daily',required=True); p.add_argument('--config',default='config.json'); p.add_argument('--out',default='reports/user'); p.add_argument('--baseline',action='store_true'); p.add_argument('--synthetic',action='store_true')
a=p.parse_args(); cfg=Config(**json.loads(Path(a.config).read_text(encoding='utf8'))); b=load(a.bars); b.attrs['data_kind']='SYNTHETIC_SOFTWARE_TEST' if a.synthetic else 'USER_SUPPLIED_NOT_VERIFIED'
r=backtest(b,load(a.index),load(a.daily,daily=True),cfg,adaptive=not a.baseline); save(r,a.out); print(json.dumps(r[0],ensure_ascii=False,indent=2))
