"""Offline smoke tests for the existing four-strategy Streamlit page."""
import ast
import pathlib
import unittest
import pandas as pd
import numpy as np

PAGE=pathlib.Path(__file__).resolve().parents[1]/"pages"/"1_신고가_4전략.py"
tree=ast.parse(PAGE.read_text(encoding="utf-8"))
names={"prepare","simulate"}
funcs=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
scope={"pd":pd,"np":np}
exec(compile(ast.Module(body=funcs,type_ignores=[]),str(PAGE),"exec"),scope)
prepare,simulate=scope["prepare"],scope["simulate"]

class SmokeTest(unittest.TestCase):
    def sample(self):
        idx=pd.bdate_range("2024-01-01",periods=100)
        d=pd.DataFrame({"open":100.0,"high":101.0,"low":99.0,"close":100.0,
            "volume":1_100_000,"foreign":100,"institution":100},index=idx)
        d.loc[idx[65],["open","high","low","close","volume"]]=[105,112,104,110,20_000_000]
        d.loc[idx[66]:,["open","high","low","close"]]=[110,112,109,110]
        return d
    def test_signal(self):
        d=prepare(self.sample())
        self.assertTrue(bool(d.signal.iloc[65]))
        self.assertFalse(bool(d.signal.iloc[64]))
    def test_all_strategies(self):
        d=prepare(self.sample())
        for mode in ["당일","5일","20일","추세"]:
            m,t,eq=simulate({"TEST":d},mode,10_000_000,2_000_000,.001,.001)
            self.assertGreaterEqual(len(t),1,mode)
            self.assertTrue(np.isfinite(m["총수익률"]))
            self.assertTrue(np.isfinite(m["MDD"]))
            self.assertGreater(len(eq),0)
    def test_no_signal(self):
        d=prepare(self.sample().assign(volume=100))
        m,t,eq=simulate({"TEST":d},"당일",10_000_000,2_000_000,.001,.001)
        self.assertEqual(len(t),0)
        self.assertEqual(m["누적손익"],0)

if __name__=="__main__":unittest.main()
