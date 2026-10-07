"""Automated historical paper replay, persistent idempotent trade journal. No brokerage orders."""
import argparse,json,sqlite3
from pathlib import Path
from engine import load,Config,backtest
p=argparse.ArgumentParser(); p.add_argument('--bars',required=True); p.add_argument('--index',required=True); p.add_argument('--daily',required=True); p.add_argument('--config',default='config.json'); p.add_argument('--db',default='reports/paper.sqlite'); a=p.parse_args()
c=Config(**json.loads(Path(a.config).read_text(encoding='utf8'))); report,trades,e=backtest(load(a.bars),load(a.index),load(a.daily,True),c)
Path(a.db).parent.mkdir(parents=True,exist_ok=True)
with sqlite3.connect(a.db) as db:
    db.execute('CREATE TABLE IF NOT EXISTS trades (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
    for r in trades.to_dict('records'):
        key=r['symbol']+'|'+r['entry_time']
        old=db.execute('SELECT payload FROM trades WHERE id=?',(key,)).fetchone(); payload=json.dumps(r,sort_keys=True)
        if old and old[0]!=payload: raise ValueError('Replay conflict: use new DB for changed strategy/data')
        db.execute('INSERT OR IGNORE INTO trades VALUES (?,?)',(key,payload))
    print('Paper journal trades:',db.execute('SELECT COUNT(*) FROM trades').fetchone()[0])
print('No brokerage orders sent. Historical replay only.')
