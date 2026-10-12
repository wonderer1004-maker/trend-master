import importlib.util
from pathlib import Path
import unittest
import pandas as pd
spec=importlib.util.spec_from_file_location('engine',Path(__file__).resolve().parents[1]/'scripts/trend_guard_v2.py')
e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)

def frame():
    idx=pd.date_range('2025-01-01',periods=4,freq='B')
    return pd.DataFrame(dict(open=[100]*4,high=[101]*4,low=[99]*4,close=[100]*4,
        atr=[2]*4,ma50=[90]*4,signal=[True,False,False,False],rank=[.2]*4,state=['BULL']*4),index=idx)

class EngineTests(unittest.TestCase):
    def test_next_open_and_risk_cap(self):
        d=frame();m,t,q,orders,p=e.simulate({'A':d},str(d.index[0].date()),str(d.index[-1].date()))
        self.assertEqual(orders[0]['date'],str(d.index[1].date()))
        self.assertLessEqual(orders[0]['quantity']*4.004,50000)
        self.assertGreaterEqual(m['end_cash'],0)
    def test_gap_stop(self):
        d=frame();d.loc[d.index[2],['open','high','low','close']]=[80,81,79,80]
        m,t,_,_,_=e.simulate({'A':d},'2025-01-01','2025-01-10')
        self.assertEqual(t.iloc[0].reason,'gap_stop');self.assertEqual(t.iloc[0]['exit'],80)
    def test_close_exit_next_open(self):
        d=frame();d.loc[d.index[1],'ma50']=101
        d.loc[d.index[2],['open','high','low','close']]=[105,106,104,105]
        _,t,_,_,_=e.simulate({'A':d},'2025-01-01','2025-01-10')
        self.assertEqual(t.iloc[0].exit_date,str(d.index[2].date()));self.assertEqual(t.iloc[0]['exit'],105)
    def test_high_does_not_raise_same_day_stop(self):
        d=frame();d.loc[d.index[1],'high']=120
        _,t,_,_,_=e.simulate({'A':d},'2025-01-01','2025-01-10')
        self.assertEqual(t.iloc[0].exit_date,str(d.index[2].date()))
    def test_open_gap_skips_entry(self):
        d=frame();d.loc[d.index[1],'open']=104
        _,_,_,orders,_=e.simulate({'A':d},'2025-01-01','2025-01-10');self.assertEqual(orders,[])
    def test_future_changes_do_not_change_past_signals(self):
        import numpy as np
        idx=pd.date_range('2020-01-01',periods=320,freq='B');c=np.linspace(100,300,320)
        d=pd.DataFrame(dict(open=c,high=c+1,low=c-1,close=c,volume=np.full(320,1e8)),index=idx)
        a=e.prepare({'A':d},d)['A'];changed=d.copy();changed.iloc[-1]=[1000,1001,999,1000,1e9]
        b=e.prepare({'A':changed},changed)['A']
        pd.testing.assert_series_equal(a.signal.iloc[:-1],b.signal.iloc[:-1])

if __name__=='__main__':unittest.main()
