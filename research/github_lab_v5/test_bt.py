import unittest
import gzip,hashlib,json
from unittest.mock import patch
import numpy as np
import pandas as pd
from bt_engine import execute,reference,schedule
from models import build,invalid,ROOT
from assess import xirr

def toy(n=330):
    ix=pd.bdate_range('2020-01-01',periods=n);c=100*np.exp(np.arange(n)*.001)
    d=pd.DataFrame({'open':c,'high':c*1.01,'low':c*.99,'close':c*1.002,'volume':1000000.},index=ix)
    return d
class Tests(unittest.TestCase):
    def test_frozen_snapshot_hashes(self):
      manifest=json.loads((ROOT/'input'/'manifest.json').read_text());self.assertEqual(len(manifest),49)
      for r in manifest:
        folder='us' if r['market']=='us' else ('kr' if r['provider']=='Naver fchart' else 'kr_yahoo')
        b=gzip.decompress((ROOT/'input'/folder/(r['symbol']+'.csv.gz')).read_bytes())
        self.assertEqual(hashlib.sha256(b).hexdigest(),r['csv_sha256'])
    def test_irr_calendar_days(self):
      dates=[pd.Timestamp('2020-01-01'),pd.Timestamp('2021-01-01')]
      self.assertAlmostEqual(xirr(dates,[100,0],110),1.1**(365.25/366)-1)
    def test_manual_one_trade_fee(self):
      d=toy(5);d.loc[:,['open','high','low','close']]=100.;w=pd.DataFrame({'A':1.},index=d.index)
      e,o,_=execute({'A':d},w,str(d.index[1].date()),str(d.index[-1].date()),'us',initial=10000.,benchmark=True)
      self.assertAlmostEqual(e.equity.iloc[-1],10000/1.001,places=3);self.assertEqual(len(o),1);self.assertEqual(o.date.iloc[0],d.index[1])
    def test_deposit_at_open_does_not_dilute_overnight_return(self):
      a=toy(5);a.index=pd.bdate_range('2020-01-29',periods=5);a.loc[:,['open','high','low','close']]=100.;a.loc[a.index[3]:,['open','high','low','close']]=200.
      w=pd.DataFrame({'A':1.},index=a.index)
      with patch('bt_engine.rate',return_value=(0.,0.)):
        e,o,_=execute({'A':a},w,'2020-01-30','2020-02-04','us',flow=1000,initial=10000.)
        ref=reference({'A':a},w,'2020-01-30','2020-02-04','us',flow=1000,initial=10000.)
      self.assertAlmostEqual(e.loc['2020-02-03','unit_nav'],2.,places=6)
      np.testing.assert_allclose(e.unit_nav,ref.unit_nav,rtol=1e-12)
    def test_rotation_funding_reference_and_cash(self):
      a=toy(45);b=a.copy();b['open']*=np.linspace(1,1.2,len(b));b['close']*=np.linspace(1,1.2,len(b));b['high']=b[['open','close']].max(axis=1)*1.01
      w=pd.DataFrame({'A':1.,'B':0.},index=a.index);w.iloc[20:]=[0,1]
      args=({'A':a,'B':b},w,str(a.index[2].date()),str(a.index[-1].date()),'us')
      e,o,_=execute(*args,flow=1000);r=reference(*args,flow=1000)
      np.testing.assert_allclose(e.equity,r.equity,rtol=1e-10);self.assertGreaterEqual(e.cash.min(),-1e-7);self.assertEqual(e.contribution.sum(),2000)
    def test_signal_executes_next_observation(self):
      a=toy(9);w=pd.DataFrame({'A':0.},index=a.index);w.iloc[4:]=1.
      _,o,_=execute({'A':a},w,str(a.index[1].date()),str(a.index[-1].date()),'us')
      self.assertEqual(o.date.iloc[0],a.index[5])
    def test_delay_two(self):
      a=toy(9);w=pd.DataFrame({'A':0.},index=a.index);w.iloc[4:]=1.
      _,o,_=execute({'A':a},w,str(a.index[2].date()),str(a.index[-1].date()),'us',delay=2)
      self.assertEqual(o.date.iloc[0],a.index[6])
    def test_current_close_not_used_for_open_sizing(self):
      a=toy(10);b=a.copy();b.loc[b.index[4],'close']*=5;w=pd.DataFrame({'A':.8},index=a.index);w.iloc[:3]=0
      _,oa,_=execute({'A':a},w,str(a.index[2].date()),str(a.index[-1].date()),'us');_,ob,_=execute({'A':b},w,str(b.index[2].date()),str(b.index[-1].date()),'us')
      self.assertEqual(oa.iloc[0].qty,ob.iloc[0].qty)
    def test_invalid_bar_and_weights(self):
      a=toy(3);a.iloc[1,a.columns.get_loc('low')]=500;self.assertEqual(list(invalid(a)),[False,True,False])
    def test_models_causal_prefix_and_leverage_bounds(self):
      a=toy();raw={s:a.copy() for s in ['SPY','SSO','QQQ','QLD','SHY','A','B']};changed={s:d.copy() for s,d in raw.items()}
      for d in changed.values():d.loc[d.index[300]:,['open','high','low','close']]*=2
      x=build(raw,'us');y=build(changed,'us')
      for m in x:
        pd.testing.assert_frame_equal(x[m].iloc[:300],y[m].iloc[:300]);self.assertLessEqual(x[m].sum(axis=1).max(),1.00000001)
    def test_kr_sell_cost_higher(self):
      a=toy(9);a.loc[:,['open','high','low','close']]=100.;w=pd.DataFrame({'A':1.},index=a.index);w.iloc[5:]=0.
      e,o,_=execute({'A':a},w,str(a.index[1].date()),str(a.index[-1].date()),'kr')
      buy=o[o.side=='BUY'].iloc[0];sell=o[o.side=='SELL'].iloc[0];self.assertAlmostEqual(buy.commission/(buy.qty*100),.0015);self.assertAlmostEqual(sell.commission/(sell.qty*100),.0035)
if __name__=='__main__':unittest.main()
