import unittest
import test_trend_fast_v7 as fixture
import trend_refined_v8 as e
class Tests(unittest.TestCase):
    def data(self):
        d=fixture.Tests().data();return e.enrich({s:f[['open','high','low','close','volume']] for s,f in d.items()})
    def test_budget_and_dual_vol(self):
        d=self.data();day=d[e.ETF].index[-1]
        a=e.target(d,day,'HYST45');b=e.target(d,day,'HYST_DUAL45')
        self.assertLessEqual(sum(a.values()),1.00001);self.assertLessEqual(sum(b.values()),sum(a.values())+.00001)
    def test_future_independence(self):
        d=self.data();day=d[e.ETF].index[-10];a=e.target(d,day,'HYST_DUAL45')
        for f in d.values():f.loc[f.index>day,'close']=1
        self.assertEqual(a,e.target(d,day,'HYST_DUAL45'))
    def test_hard_trend_break_exits(self):
        d=fixture.Tests().data();raw={s:f[['open','high','low','close','volume']].copy() for s,f in d.items()}
        raw[e.ETF].iloc[-1,raw[e.ETF].columns.get_loc('close')]=1
        fresh=e.enrich(raw);self.assertFalse(e.strong(fresh,fresh[e.ETF].index[-1]))
if __name__=='__main__':unittest.main()
