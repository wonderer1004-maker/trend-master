import ast
from pathlib import Path
import pandas as pd
import numpy as np

SOURCE=Path(__file__).resolve().parents[1]/"pages"/"1_신고가_4전략.py"
tree=ast.parse(SOURCE.read_text(encoding="utf-8"))
functions=ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ("prepare","simulate")],type_ignores=[])
ns={"pd":pd,"np":np}
exec(compile(functions,str(SOURCE),"exec"),ns)

def make_data():
    idx=pd.bdate_range("2025-01-01",periods=90)
    d=pd.DataFrame({"open":100.0,"high":101.0,"low":99.0,"close":100.0,
        "volume":1_100_000,"foreign":100,"institution":100},index=idx)
    d.loc[idx[60],"close"]=110.0
    d.loc[idx[60],"high"]=111.0
    d.loc[idx[60],"volume"]=6_000_000
    d.loc[idx[61],"open"]=112.0
    d.loc[idx[61],"close"]=114.0
    d.loc[idx[61],"high"]=115.0
    d.loc[idx[61],"low"]=111.0
    return ns["prepare"](d)

def test_signal_uses_previous_high():
    d=make_data()
    assert bool(d.signal.iloc[60])
    assert not bool(d.signal.iloc[59])

def test_all_modes_produce_finite_equity():
    d=make_data()
    for mode in ("당일","5일","20일","추세"):
        m,t,e=ns["simulate"]({"005930":d},mode,10_000_000,2_000_000,.001,.001)
        assert len(e)==90
        assert np.isfinite(e.to_numpy()).all()
        assert np.isfinite(m["총수익률"])
        assert m["거래수"]>=1
        assert len(t)==m["거래수"]

def test_no_signal_no_trade():
    d=make_data()
    d["signal"]=False
    m,t,e=ns["simulate"]({"005930":d},"5일",10_000_000,2_000_000,.001,.001)
    assert m["거래수"]==0
    assert m["누적손익"]==0
