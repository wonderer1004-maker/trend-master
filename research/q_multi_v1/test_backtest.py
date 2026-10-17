import unittest
import numpy as np
import pandas as pd
from research.q_multi_v1.backtest import ETF,SECTORS,prepare,simulate


def fixture():
    days=pd.bdate_range('2018-01-01',periods=720)
    raw={}
    for i,s in enumerate([ETF,*SECTORS]):
        t=np.arange(len(days))
        c=20000*np.exp(.001*t+.035*np.sin(t/7+i*.1))
        raw[s]=pd.DataFrame({'open':c*1.001,'high':c*1.02,'low':c*.98,'close':c,'volume':2e7},index=days)
    return raw


class TestQMultiPilot(unittest.TestCase):
    def test_indicators_do_not_use_future(self):
        raw=fixture(); full=prepare(raw)
        cut={s:d.iloc[:550] for s,d in raw.items()}
        prefix=prepare(cut)
        for s in raw:
            pd.testing.assert_frame_equal(full[s].iloc[:550],prefix[s])

    def test_replay_prefix_and_next_session_fills(self):
        data=prepare(fixture()); dates=data[ETF].index
        _,long,orders=simulate(data,str(dates[300].date()),str(dates[-1].date()),'PRICE_PILOT')
        _,short,_=simulate(data,str(dates[300].date()),str(dates[550].date()),'PRICE_PILOT')
        self.assertGreater(len(orders),0)
        pd.testing.assert_frame_equal(long.loc[:dates[550]],short)
        lookup={d:i for i,d in enumerate(dates)}
        for r in orders.itertuples():
            self.assertEqual(lookup[pd.Timestamp(r.fill_date)],lookup[pd.Timestamp(r.signal_date)]+1)
        self.assertTrue((long.cash>=0).all())
        self.assertTrue((long.positions<=10).all())

    def test_market_confirmation_and_benchmark_costs(self):
        raw=fixture(); days=raw[ETF].index
        for s in raw:
            raw[s].loc[days[500]:,['open','high','low','close']]*=.5
        data=prepare(raw)
        self.assertEqual(data[ETF].budget.iloc[502],.3)
        self.assertEqual(data[ETF].budget.iloc[499],1.)
        lo,_,_=simulate(data,str(days[300].date()),str(days[-1].date()),'BASKET_HOLD',1)
        hi,_,_=simulate(data,str(days[300].date()),str(days[-1].date()),'BASKET_HOLD',2)
        self.assertLess(hi['end_value'],lo['end_value'])

    def test_duplicate_dates_rejected(self):
        raw=fixture();raw[ETF]=pd.concat([raw[ETF],raw[ETF].iloc[-1:]])
        with self.assertRaises(ValueError):prepare(raw)

if __name__=='__main__':unittest.main()
