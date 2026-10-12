import unittest
from test_trend_rotation_v3 import prepared
import trend_fast_v7 as e
class Tests(unittest.TestCase):
    def data(self):
        d=prepared();d[e.LEVER]=d[e.ETF].copy();return e.enrich({s:f[['open','high','low','close','volume']] for s,f in d.items()})
    def test_confirmed_and_budget(self):
        d=self.data();day=d[e.ETF].index[-1];self.assertTrue(e.strong(d,day))
        for m in e.MODELS:self.assertLessEqual(sum(e.target(d,day,m).values()),1.00001)
    def test_bad_trend_cash(self):
        d=self.data();day=d[e.ETF].index[-1];d[e.ETF].loc[day,'confirmed']=False
        for m in e.MODELS:self.assertEqual(e.target(d,day,m),{})
    def test_future_independence(self):
        d=self.data();day=d[e.ETF].index[-10];a=e.target(d,day,'MIX45')
        for f in d.values():f.loc[f.index>day,'close']=1
        self.assertEqual(a,e.target(d,day,'MIX45'))
if __name__=='__main__':unittest.main()
