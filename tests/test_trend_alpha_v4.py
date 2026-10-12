from test_trend_rotation_v3 import prepared
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import trend_alpha_v4 as e
class Tests(unittest.TestCase):
    def test_total_allocation(self):
        d=prepared();day=d[e.ETF].index[-1]
        for model in e.MODELS:self.assertAlmostEqual(sum(e.target(d,day,model).values()),1)
    def test_fallback(self):
        d=prepared();day=d[e.ETF].index[-1]
        for s in d:
            if s!=e.ETF:d[s].loc[day,'r120']=-1
        self.assertEqual(e.target(d,day,'LEADER1'),{e.ETF:1.})
    def test_next_open_cash(self):
        d=prepared();days=d[e.ETF].index[-50:]
        _,_,orders,state=e.simulate(d,str(days[0].date()),str(days[-1].date()),'BUY_HOLD')
        self.assertEqual(orders.iloc[0].date,str(days[1].date()));self.assertGreaterEqual(state['cash'],0)
if __name__=='__main__':unittest.main()
