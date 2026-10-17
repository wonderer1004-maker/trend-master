import unittest
import numpy as np
import pandas as pd
from research.quant_survey_v2.engine import prepare,schedules,replay,exposure_control


def fixture():
    idx=pd.bdate_range('2007-01-01',periods=950)
    out={}
    for j,s in enumerate(['SPY','QQQ','IWM','IEF','GLD','SHY']):
        t=np.arange(len(idx));c=(100+j*2)*np.exp((.0004 if s!='SHY' else .00005)*t+.06*np.sin(t/23+j))
        out[s]=pd.DataFrame({'open':c*1.002,'high':c*1.01,'low':c*.99,'close':c,'volume':1e7},index=idx)
    return out


class TestSurvey(unittest.TestCase):
    def test_prefix_has_no_future_information(self):
        raw=fixture();full=prepare(raw,'us');cut=prepare({s:x.iloc[:750] for s,x in raw.items()},'us')
        start=str(full['idx'][300].date());a=schedules(full,start);b=schedules(cut,start)
        for k in a:np.testing.assert_allclose(a[k][:748],b[k][:748],equal_nan=True,err_msg=k)

    def test_all_targets_long_only_unlevered(self):
        d=prepare(fixture(),'us')
        for model,target in schedules(d,str(d['idx'][300].date())).items():
            rows=target[np.isfinite(target).all(axis=1)]
            self.assertGreater(len(rows),0,model)
            self.assertTrue((rows>=0).all(),model);self.assertTrue((rows.sum(axis=1)<=1+1e-9).all(),model)

    def test_round_trip_accounting_and_delay(self):
        d=prepare(fixture(),'us');d['open'][:]=100.;d['close'][:]=100.
        n,p=d['close'].shape;t=np.full((n,p),np.nan);t[300]=0;t[300,0]=1;t[302]=0
        start=str(d['idx'][300].date());end=str(d['idx'][306].date())
        stats,eq,orders=replay(d,t,start,end)
        expected=100000*(1-.0005)*(1-.0002)/((1+.0005)*(1+.0002))
        self.assertAlmostEqual(stats['final_value'],expected,places=7)
        self.assertEqual(orders.fill_date.iloc[0],str(d['idx'][301].date()))
        self.assertEqual(orders.fill_date.iloc[-1],str(d['idx'][303].date()))
        _,_,later=replay(d,t,start,end,delay=2)
        self.assertEqual(later.fill_date.iloc[0],str(d['idx'][302].date()))
        self.assertEqual(eq.equity.iloc[0],100000)

    def test_future_price_changes_cannot_change_prior_replay(self):
        raw=fixture();a=prepare(raw,'us');change={s:x.copy() for s,x in raw.items()}
        for d in change.values():d.iloc[750:,:4]*=2
        b=prepare(change,'us');start=str(a['idx'][300].date());end=str(a['idx'][740].date())
        ta=schedules(a,start);tb=schedules(b,start)
        for k in ('CSM12_1','MA10M','VOL15','R2','ENSEMBLE'):
            _,ea,oa=replay(a,ta[k],start,end);_,eb,ob=replay(b,tb[k],start,end)
            pd.testing.assert_frame_equal(ea,eb);pd.testing.assert_frame_equal(oa,ob)

    def test_exposure_control_preserves_risky_budget(self):
        d=prepare(fixture(),'us');t=schedules(d,str(d['idx'][300].date()))['DUAL12'];ct=exposure_control(d,t)
        rows=np.isfinite(t).all(axis=1)
        np.testing.assert_allclose(t[rows].sum(axis=1)-t[rows,d['defense']],ct[rows,d['b']])

    def test_invalid_prices_and_dates_rejected(self):
        raw=fixture();raw['SPY'].iloc[5,0]=-1
        with self.assertRaises(ValueError):prepare(raw,'us')
        raw=fixture();raw['SPY']=pd.concat([raw['SPY'],raw['SPY'].iloc[-1:]])
        with self.assertRaises(ValueError):prepare(raw,'us')

if __name__=='__main__':unittest.main()
