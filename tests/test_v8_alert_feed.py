import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import export_v8_alert_feed as e
import pandas as pd
import numpy as np
class FeedTests(unittest.TestCase):
 def raw(self):
  idx=pd.bdate_range('2020-01-01',periods=500);c=np.linspace(10000,50000,len(idx))
  d=pd.DataFrame(dict(open=c,high=c*1.01,low=c*.99,close=c,volume=np.full(len(c),1e7)),index=idx)
  return {s:d.copy() for s in e.NAMES}
 def state(self,decision):
  raw=self.raw();return raw,dict(strategy='DUAL_BAND45',data_asof=str(next(iter(raw.values())).index[-1].date()),cash=10000000,holdings={'005930.KS':10},next_target=decision,action='HOLD' if decision is None else 'REBALANCE_NEXT_OPEN')
 def test_hold_is_not_sell_all(self):
  raw,state=self.state(None);f=e.build(state,raw);self.assertEqual(f['alerts'],[])
 def test_empty_decision_sells_only_owned_asset(self):
  raw,state=self.state({});f=e.build(state,raw);self.assertEqual(len(f['alerts']),1);self.assertEqual(f['alerts'][0]['side'],'SELL')
 def test_date_mismatch_rejected(self):
  raw,state=self.state(None);state['data_asof']='2020-01-01'
  with self.assertRaises(ValueError):e.build(state,raw)
if __name__=='__main__':unittest.main()
