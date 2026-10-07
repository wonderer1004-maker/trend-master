import unittest,tempfile
from pathlib import Path
import pandas as pd
from unittest.mock import patch
from engine import Config,load,backtest

class TestEngine(unittest.TestCase):
    def fixture(self):
        ts=pd.date_range('2026-01-05 09:00',periods=76,freq='5min'); rows=[]
        for i,t in enumerate(ts):
            rows.append(dict(timestamp=t,day=t.normalize(),symbol='S',open=100,high=101,low=99,close=100,volume=100000,atr=1,vwap=99,ema20=100,ema50=99,rsi=60,pivot=99.9,vr=2,signal=i==10,ret=0,ready=True))
        b=pd.DataFrame(rows); ix=b.copy(); ix.symbol='INDEX'
        context={'S':pd.DataFrame({'day':[pd.Timestamp('2026-01-02')],'eligible':[True]})}
        return b,ix,context
    def run_case(self,mutate=None,**kw):
        b,ix,ctx=self.fixture()
        if mutate: mutate(b)
        with patch('engine.features',side_effect=lambda x:x),patch('engine.daily_context',return_value=ctx):
            return backtest(b,ix,b,Config(**kw))
    def test_next_bar_execution(self):
        r,t,e=self.run_case(); self.assertEqual(len(t),1); self.assertEqual(t.iloc[0].entry_time,'2026-01-05 09:55:00'); self.assertEqual(t.iloc[0].reason,'day_exit'); self.assertLess(r['final'],r['initial'])
    def test_stop_and_one_trade_per_day(self):
        def mutate(b): b.loc[11,'low']=97; b.loc[20,'signal']=True
        r,t,e=self.run_case(mutate); self.assertEqual(len(t),1); self.assertEqual(t.iloc[0].reason,'stop'); self.assertLess(t.iloc[0].R,0)
    def test_gap_stop(self):
        def mutate(b): b.loc[12,'open']=97; b.loc[12,'low']=96
        r,t,e=self.run_case(mutate); self.assertEqual(t.iloc[0].reason,'gap_stop'); self.assertLess(t.iloc[0]['exit'],97)
    def test_prefix_causality(self):
        a=self.run_case()[2]
        def mutate(b): b.loc[60:,'close']=150
        b=self.run_case(mutate)[2]; pd.testing.assert_frame_equal(a.iloc[:60],b.iloc[:60])
    def test_larger_costs_reduce_equity(self):
        a=self.run_case()[0]; b=self.run_case(slip=.002,sell_tax=.003)[0]; self.assertLess(b['final'],a['final'])
    def test_missing_session_rejected(self):
        b,ix,ctx=self.fixture()
        with self.assertRaises(ValueError): backtest(b.iloc[:-1],ix,b)
    def test_invalid_ohlc_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.csv'; pd.DataFrame([{'timestamp':'2026-01-05 09:00','symbol':'S','open':100,'high':90,'low':99,'close':100,'volume':1}]).to_csv(p,index=False)
            with self.assertRaises(ValueError): load(p)
if __name__=='__main__': unittest.main()
