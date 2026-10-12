import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import trend_rotation_v3 as e
import numpy as np
import pandas as pd

def prepared():
    idx=pd.bdate_range('2018-01-01',periods=600);c=np.linspace(10000,50000,len(idx))
    d=pd.DataFrame(dict(open=c,high=c*1.01,low=c*.99,close=c,volume=np.full(len(c),1e7)),index=idx)
    return e.prepare({e.ETF:d,'A':d*1.1,'B':d*1.2,'C':d*1.3})
class Tests(unittest.TestCase):
    def test_cap(self):
        d=prepared();w,_=e.allocation(d,d[e.ETF].index[-1],'MOM3')
        self.assertLessEqual(sum(w.values()),1);self.assertTrue(all(x<=.35 for x in w.values()))
    def test_next_open(self):
        d=prepared();days=d[e.ETF].index[-50:]
        _,_,orders,state=e.replay(d,str(days[0].date()),str(days[-1].date()),'BUY_HOLD')
        self.assertEqual(orders.iloc[0].date,str(days[1].date()));self.assertGreaterEqual(state['cash'],0)
    def test_future_independence(self):
        d=prepared();day=d[e.ETF].index[-10];a=e.allocation(d,day,'MOM3')
        for frame in d.values():frame.loc[frame.index>day,'close']=1
        self.assertEqual(a,e.allocation(d,day,'MOM3'))
    def test_idempotent(self):
        with tempfile.TemporaryDirectory() as t:
            db=str(Path(t)/'orders.sqlite')
            a=e.record_intent(db,'2026-10-12','MOM3',{'A':.3})
            self.assertEqual(a,e.record_intent(db,'2026-10-12','MOM3',{'A':.3}))
            with self.assertRaises(ValueError):e.record_intent(db,'2026-10-12','MOM3',{'A':.2})
    def test_bad_weights(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):e.record_intent(str(Path(t)/'d'),'x','MOM3',{'A':1.1})
    def test_cost_stress(self):
        d=prepared();start=str(d[e.ETF].index[-50].date());end=str(d[e.ETF].index[-1].date())
        a=e.replay(d,start,end,'BUY_HOLD',fee=.0005)[0]
        b=e.replay(d,start,end,'BUY_HOLD',fee=.005)[0]
        self.assertLess(b['total_return'],a['total_return'])
if __name__=='__main__':unittest.main()
