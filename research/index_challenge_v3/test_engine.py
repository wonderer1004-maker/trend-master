import unittest
import numpy as np
import pandas as pd
from research.index_challenge_v3.engine import prepare,replay,weights,money_irr


def fixture():
    idx=pd.bdate_range('2007-01-01',periods=1800);raw={}
    for j,s in enumerate(['SPY','SSO','SHY']):
        t=np.arange(len(idx));c=100*np.exp((.0003 if s!='SHY' else .00002)*t+.03*np.sin(t/27+j))
        raw[s]=pd.DataFrame({'open':c*1.001,'high':c*1.01,'low':c*.99,'close':c,'volume':1e7},index=idx)
    return raw,dict(base='SPY',lever='SSO',market='us')


class TestIndexChallenge(unittest.TestCase):
    def test_exposure_allocation(self):
        for e in [0,.5,1,1.25,1.5,2]:
            w=weights(e,3);self.assertAlmostEqual(w.sum(),1);self.assertAlmostEqual(w[0]+2*w[1],e)
            self.assertTrue((w>=0).all())
        with self.assertRaises(ValueError):weights(2.1,3)

    def test_future_prices_do_not_change_past_targets(self):
        raw,spec=fixture();a=prepare(raw,spec)
        for x in raw.values():x.iloc[1400:,:4]*=2
        b=prepare(raw,spec)
        for k in a['target']:np.testing.assert_allclose(a['target'][k][:1398],b['target'][k][:1398],equal_nan=True,err_msg=k)

    def test_cashflows_same_across_models_and_no_same_day_signal(self):
        raw,spec=fixture();d=prepare(raw,spec);start=str(d['idx'][500].date());end=str(d['idx'][700].date())
        a,ea,oa=replay(d,'INDEX_HOLD',start,end,'DCA')
        b,eb,ob=replay(d,'MA200_150',start,end,'DCA')
        pd.testing.assert_series_equal(ea.contribution,eb.contribution)
        self.assertEqual(a['contributed'],b['contributed'])
        positions={day:i for i,day in enumerate(d['idx'])}
        for r in ob.itertuples():self.assertEqual(positions[r.fill_date]-positions[r.signal_date],1)
        self.assertTrue((eb.cash>=-.001).all())

    def test_flat_market_deposits_do_not_create_returns(self):
        raw,spec=fixture();d=prepare(raw,spec);d['open'][:]=100;d['close'][:]=100
        start=str(d['idx'][500].date());end=str(d['idx'][760].date())
        stat,eq,_=replay(d,'INDEX_HOLD',start,end,'DCA',cost=0)
        np.testing.assert_allclose(eq.unit_price,1)
        self.assertAlmostEqual(stat['final_value'],stat['contributed'])
        self.assertAlmostEqual(stat['twr_mdd_pct'],0)
        self.assertAlmostEqual(stat['money_irr_pct'],0,places=7)

    def test_one_cashflow_irr_matches_growth(self):
        days=[pd.Timestamp('2020-01-01'),pd.Timestamp('2021-01-01')]
        r=money_irr([(days[0],100),(days[1],0)],110)
        self.assertAlmostEqual((1+r)**((days[1]-days[0]).days/365.25),1.1,places=10)

    def test_prefix_and_fee_accounting(self):
        raw,spec=fixture();d=prepare(raw,spec);short=prepare({s:x.iloc[:1400] for s,x in raw.items()},spec)
        for k in d['target']:np.testing.assert_allclose(d['target'][k][:1398],short['target'][k][:1398],equal_nan=True)
        d['open'][:]=100;d['close'][:]=100
        start=str(d['idx'][500].date());end=str(d['idx'][510].date())
        m,_,_=replay(d,'INDEX_HOLD',start,end,'LUMP')
        self.assertAlmostEqual(m['final_value'],10000/((1+.0002)*(1+.0005)),places=7)

    def test_bad_input_rejected(self):
        raw,spec=fixture();raw['SPY'].iloc[5,0]=-1
        with self.assertRaises(ValueError):prepare(raw,spec)

if __name__=='__main__':unittest.main()
