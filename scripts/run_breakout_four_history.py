"""Run a reproducible real-market sample backtest. Never fabricate missing data."""
import ast
import json
from datetime import date, timedelta
from pathlib import Path
import numpy as np
import pandas as pd
from pykrx import stock

ROOT=Path(__file__).resolve().parents[1]
PAGE=ROOT/"pages"/"1_신고가_4전략.py"
tree=ast.parse(PAGE.read_text(encoding="utf-8"))
funcs=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ("prepare","simulate")]
scope={"pd":pd,"np":np}
exec(compile(ast.Module(body=funcs,type_ignores=[]),str(PAGE),"exec"),scope)
prepare,simulate=scope["prepare"],scope["simulate"]
start,end="20200101","20260930"
warmup="20190601"
symbols={"005930":"삼성전자","000660":"SK하이닉스","005380":"현대차"}
data={}
for code,name in symbols.items():
    prices=stock.get_market_ohlcv_by_date(warmup,end,code,adjusted=True)
    flows=stock.get_market_trading_volume_by_date(warmup,end,code)
    if prices is None or prices.empty or flows is None or flows.empty:
        raise RuntimeError(f"{name}: historical OHLCV or flows unavailable")
    needed=["외국인합계","기관합계"]
    if any(c not in flows for c in needed):
        raise RuntimeError(f"{name}: missing flow columns: {list(flows.columns)}")
    d=prices.join(flows[needed],how="left").rename(columns={
        "시가":"open","고가":"high","저가":"low","종가":"close",
        "거래량":"volume","외국인합계":"foreign","기관합계":"institution"})
    required=["open","high","low","close","volume","foreign","institution"]
    if d[required].isna().any().any():raise RuntimeError(f"{name}: incomplete rows")
    d=prepare(d)
    d=d.loc[start:end]
    if d.empty:raise RuntimeError(f"{name}: no test-period rows")
    data[code]=d
out=ROOT/"reports"/"breakout_four"
out.mkdir(parents=True,exist_ok=True)
rows=[]
for mode in ["당일","5일","20일","추세"]:
    metrics,trades,equity=simulate(data,mode,10_000_000,2_000_000,.001,.001)
    if not metrics:raise RuntimeError(f"{mode}: empty results")
    rows.append(metrics)
    trades.to_csv(out/f"trades_{mode}.csv",index=False,encoding="utf-8-sig")
    equity.rename("equity").to_csv(out/f"equity_{mode}.csv",encoding="utf-8-sig")
pd.DataFrame(rows).to_csv(out/"comparison.csv",index=False,encoding="utf-8-sig")
(out/"methodology.json").write_text(json.dumps({
    "universe":symbols,"start":start,"end":end,"initial_capital":10000000,
    "allocation":2000000,"fee_each_side":0.001,"slippage_each_side":0.001,
    "limitations":["Only 3 surviving stocks; not full KOSPI universe",
                   "OHLC daily bars cannot establish intraday fill order",
                   "Same-day stops after entry not modeled",
                   "pykrx availability and historical corrections may vary",
                   "60-day close breakout approximates intraday high condition"]},
    ensure_ascii=False,indent=2),encoding="utf-8")
print(pd.DataFrame(rows).to_string(index=False))
