import unittest
import numpy as np
import pandas as pd
import publish
import engine

class ModelTests(unittest.TestCase):
    def synthetic(self,market='KR'):
        idx=pd.bdate_range('2014-01-01',periods=370);rng=np.random.default_rng(312)
        ds={}
        for s in publish.MARKETS[market]['symbols']:
            c=100*np.exp(np.cumsum(rng.normal(.001,.013,len(idx))))
            d=pd.DataFrame(dict(open=c,close=c,high=c*1.003,low=c*.997,volume=1000.),index=idx)
            ds[s]=(d,1.,float(c[-1]),0)
        return ds

    def test_snapshot_matches_backtest_targets(self):
        data=self.synthetic();nextday=str((next(iter(data.values()))[0].index[-1]+pd.offsets.BDay()).date())
        rows=publish.model_rows(data,'KR',nextday)
        extended={}
        for s,(d,_,_,_) in data.items():
            cp=d.copy();cp.loc[pd.Timestamp(nextday)]=cp.iloc[-1];extended[s]=cp
        f=engine.features(extended)
        _,frame,orders=engine.simulate(f,'BLEND','2015-01-01',nextday,0.)
        self.assertAlmostEqual(sum(r['target_weight'] for r in rows),frame.target_sum.iloc[-1],12)
        # Last rebalance's stored per-symbol weights equal the signal snapshot.
        for row in rows:
            obs=[o for o in orders if o['symbol']==row['symbol'] and o['side']!='SELL_END']
            if obs:self.assertAlmostEqual(obs[-1]['target_weight'],row['target_weight'],12)

    def test_threshold_includes_latest_for_next_signal(self):
        data=self.synthetic();day=str((next(iter(data.values()))[0].index[-1]+pd.offsets.BDay()).date())
        rows=publish.model_rows(data,'KR',day)
        for row in rows:
            self.assertAlmostEqual(row['entry120'],data[row['symbol']][0].high.tail(120).max())
            self.assertLessEqual(row['target_weight'],.2+1e-10)

    def test_completed_session_blocks_intraday(self):
        last,nxt=publish.completed_session('US',pd.Timestamp('2026-10-14T18:00:00Z'))
        self.assertEqual(last,'2026-10-13');self.assertEqual(nxt,'2026-10-14')

    def test_missing_calendar_date_rejected(self):
        data=self.synthetic();s=next(iter(data));d,f,c,n=data[s];data[s]=(d.drop(d.index[-10]),f,c,n)
        with self.assertRaisesRegex(ValueError,'dates differ'):publish.model_rows(data,'KR','2015-06-04')

if __name__=='__main__':unittest.main()
