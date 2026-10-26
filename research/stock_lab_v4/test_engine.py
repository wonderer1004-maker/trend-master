import unittest
import numpy as np
import pandas as pd
from engine import features,daily,stop_fill,xirr,Rules,metrics,invalid_bars
from intraday import sessions,run

def sample(n=330):
    ix=pd.bdate_range('2020-01-01',periods=n);c=100*np.exp(np.arange(n)*.002)
    return pd.DataFrame(dict(open=c,high=c*1.001,low=c*.999,close=c,volume=np.full(n,1000000)),index=ix)
class Tests(unittest.TestCase):
    def test_impossible_ohlc_rejected_without_repair(self):
      d=sample(3);d.loc[d.index[1],'close']=d.high.iloc[1]*2
      self.assertEqual(list(invalid_bars(d)),[False,True,False])
      self.assertEqual(len(d.loc[~invalid_bars(d)]),2)
    def test_gap_stop_does_not_cap_loss(self):
      self.assertEqual(stop_fill(80,75,95),80);self.assertEqual(stop_fill(100,94,95),95);self.assertIsNone(stop_fill(100,96,95))
    def test_features_and_orders_ignore_future(self):
      a=sample();b=a.copy();cut=a.index[290];b.loc[b.index>cut,['open','high','low','close']]*=3
      fa,fb=features(a),features(b);pd.testing.assert_frame_equal(fa.loc[:cut],fb.loc[:cut])
      _,ea,_,oa=daily({'A':a},a,'BREAK20',str(a.index[210].date()),str(a.index[-1].date()),.001,.001)
      _,eb,_,ob=daily({'A':b},b,'BREAK20',str(b.index[210].date()),str(b.index[-1].date()),.001,.001)
      pd.testing.assert_frame_equal(ea.loc[:cut],eb.loc[:cut]);self.assertEqual([o for o in oa if o['date']<=cut],[o for o in ob if o['date']<=cut])
    def test_entry_after_completed_signal(self):
      a=sample();_,_,_,orders=daily({'A':a},a,'BREAK20',str(a.index[199].date()),str(a.index[210].date()),0,0)
      buy=next(o for o in orders if o['side']=='BUY');self.assertEqual(buy['date'],a.index[200])
    def test_cash_and_position_caps(self):
      a=sample();_,e,_,orders=daily({s:a.copy() for s in 'ABCDEFGH'},a,'BREAK20',str(a.index[210].date()),str(a.index[215].date()),.001,.001,rules=Rules(risk=.5))
      buys=[o for o in orders if o['side']=='BUY'];self.assertEqual(len(buys),5);self.assertTrue(all(o['qty']*o['price']<=20000.0001 for o in buys));self.assertLessEqual(sum(o['qty']*o['price']*1.001 for o in buys),100000.0001)
    def test_intraday_stop_proceeds_cannot_fund_open_entry(self):
      a=sample();a.loc[a.index[212],'low']=1
      _,_,_,orders=daily({'A':a,'B':a.copy()},a,'BREAK20',str(a.index[210].date()),str(a.index[214].date()),0,0,initial=100000,rules=Rules(risk=.5,max_positions=1,cap=1))
      same_day=[o for o in orders if o['date']==a.index[212] and o['side']=='BUY'];self.assertFalse(same_day)
    def test_missing_benchmark_bar_does_not_skip_stock_stop(self):
      a=sample();a.loc[a.index[212],'low']=1;b=a.drop(a.index[212])
      _,e,t,_=daily({'A':a},b,'BREAK20',str(a.index[210].date()),str(a.index[215].date()),0,0)
      self.assertIn(a.index[212],e.index);self.assertTrue(any(x['exit']==a.index[212] for x in t))
    def test_intraday_net_costs_and_integer_cap(self):
      d=pd.Timestamp('2026-10-01');ev={d:[dict(symbol='A',time=d+pd.Timedelta(hours=10),exit_time=d+pd.Timedelta(hours=16),price=100.,exit_price=100.,stop=99.,rvol=2.,volume=100000.,reason='session_close')]}
      m,e,t,o=run(ev,[d,d+pd.Timedelta(days=1)],.001,.002)
      self.assertAlmostEqual(t[0]['pnl'],-60);self.assertEqual(o[0]['qty'],200);self.assertLess(m['total_return'],0)
    def test_incomplete_intraday_session_rejected(self):
      a=sample(1);a.index=pd.DatetimeIndex(['2026-10-01 09:30']);ev,audit=sessions({'A':a},'us',1)
      self.assertFalse(ev);self.assertEqual(audit['A']['complete_sessions'],0)
    def test_xirr_known_cashflows(self):
      dates=[pd.Timestamp('2020-01-01'),pd.Timestamp('2021-01-01')]
      self.assertAlmostEqual(xirr(dates,[-100,0],110),1.1**(365.25/366)-1)
if __name__=='__main__':unittest.main()
