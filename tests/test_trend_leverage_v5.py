from test_trend_rotation_v3 import prepared
import trend_leverage_v5 as e
import unittest
class Tests(unittest.TestCase):
    def data(self):
        d=prepared();d[e.LEVER]=d[e.ETF].copy()*2;return d
    def test_strong_allocation(self):
        d=self.data();day=d[e.ETF].index[-1]
        self.assertEqual(e.target(d,day,'L50'),{e.ETF:.5,e.LEVER:.5})
    def test_weak_deleverage(self):
        d=self.data();day=d[e.ETF].index[-1];d[e.ETF].loc[day,'close']=1
        self.assertEqual(e.target(d,day,'L100'),{e.ETF:1.})
    def test_no_same_day_switch(self):
        d=self.data();days=d[e.ETF].index[-40:];day=days[10]
        d[e.ETF].loc[day,'ma200']=1e10
        _,_,orders,_=e.simulate(d,str(days[0].date()),str(days[-1].date()),'L100',target_fn=e.target,daily_target=True,tax_exempt=(e.LEVER,))
        sells=orders[(orders.side=='SELL')&(orders.symbol==e.LEVER)]
        self.assertEqual(sells.iloc[0].date,str(days[11].date()))
if __name__=='__main__':unittest.main()
