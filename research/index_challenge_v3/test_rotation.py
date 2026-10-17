import unittest
import numpy as np
from research.index_challenge_v3.test_engine import fixture
from research.index_challenge_v3.rotation import prepare_rotation,REGIONS
from research.index_challenge_v3.engine import replay


class TestRotation(unittest.TestCase):
    def raw(self):
        raw,_=fixture()
        for dest,src in [('QQQ','SPY'),('QLD','SSO')]:
            raw[dest]=raw[src].copy();raw[dest].iloc[:,:4]*=2
        return raw

    def test_causal_monthly_targets(self):
        raw=self.raw();a=prepare_rotation(raw,REGIONS['US'])
        for x in raw.values():x.iloc[1400:,:4]*=3
        b=prepare_rotation(raw,REGIONS['US'])
        for m in a['target']:np.testing.assert_allclose(a['target'][m][:1398],b['target'][m][:1398],equal_nan=True)

    def test_both_benchmarks_use_identical_cashflows(self):
        d=prepare_rotation(self.raw(),REGIONS['US']);start=str(d['idx'][500].date());end=str(d['idx'][1100].date())
        a,ea,_=replay(d,'BENCH_A',start,end,'DCA',custom_target=d['target']['BENCH_A'])
        b,eb,_=replay(d,'BENCH_B',start,end,'DCA',custom_target=d['target']['BENCH_B'])
        self.assertAlmostEqual(a['final_value'],b['final_value'],places=6)
        np.testing.assert_allclose(ea.contribution,eb.contribution)
        self.assertAlmostEqual(a['avg_exposure'],1.,places=7)
        self.assertAlmostEqual(b['avg_exposure'],1.,places=7)

if __name__=='__main__':unittest.main()
