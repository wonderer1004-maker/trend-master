from test_trend_rotation_v3 import prepared
import trend_balanced_v6 as e
import unittest
class Tests(unittest.TestCase):
    def data(self):
        d=prepared();d[e.LEVER]=d[e.ETF].copy()*2;return d
    def test_weak_cash(self):
        d=self.data();day=d[e.ETF].index[-1];d[e.ETF].loc[day,'close']=1
        for model in e.MODELS:self.assertEqual(e.target(d,day,model),{})
    def test_weight_budget(self):
        d=self.data();day=d[e.ETF].index[-1]
        for model in e.MODELS:
            w=e.target(d,day,model);self.assertLessEqual(sum(w.values()),1.00001)
            self.assertTrue(all(v>=0 for v in w.values()))
    def test_next_open_defense(self):
        d=self.data();days=d[e.ETF].index[-40:];day=days[10]
        d[e.ETF].loc[day,'ma200']=1e10
        _,_,orders,state=e.simulate(d,str(days[0].date()),str(days[-1].date()),'CASH100')
        sells=orders[(orders.side=='SELL')&(orders.symbol==e.LEVER)]
        self.assertEqual(sells.iloc[0].date,str(days[11].date()));self.assertGreaterEqual(state['cash'],0)
    def test_future_does_not_change_target(self):
        d=self.data();day=d[e.ETF].index[-10];a=e.target(d,day,'VOL25')
        for frame in d.values():frame.loc[frame.index>day,'close']=1
        self.assertEqual(a,e.target(d,day,'VOL25'))
if __name__=='__main__':unittest.main()
