"""Out-of-sample Yahoo breakout strategy comparison; never promise profit."""
import ast
import json
from pathlib import Path
import numpy as np
import pandas as pd
from run_yahoo_breakout import get_history, SYMBOLS, REPORT
PAGE=Path(__file__).resolve().parents[1]/"pages"/"1_신고가_4전략.py"
tree=ast.parse(PAGE.read_text(encoding="utf-8"))
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="simulate"]
scope={"pd":pd,"np":np}
exec(compile(ast.Module(body=nodes,type_ignores=[]),str(PAGE),"exec"),scope)
simulate=scope["simulate"]
OUT=REPORT/"improved"
OUT.mkdir(parents=True,exist_ok=True)
TRAIN_END="2023-12-29"
TEST_START="2024-01-02"
TEST_END="2026-09-30"
# Three PRE-DECLARED candidates. No parameter sweep or look-ahead optimization.
CANDIDATES={
 "A_기본_5배":dict(high=60,volume=5.0,trend=False,rsi=False),
 "B_완화_2배_추세":dict(high=60,volume=2.0,trend=True,rsi=False),
 "C_완화_1.5배_RSI":dict(high=60,volume=1.5,trend=True,rsi=True),
}
def rsi14(close):
    change=close.diff()
    gain=change.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    loss=(-change.clip(upper=0)).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    rs=gain/loss.replace(0,np.nan)
    return 100-100/(1+rs)
def prepare(d,p):
    d=d.copy()
    d["ma20"]=d.close.rolling(20).mean()
    d["ma60"]=d.close.rolling(60).mean()
    d["ma120"]=d.close.rolling(120).mean()
    d["high60"]=d.high.shift(1).rolling(p["high"]).max()
    vol=d.volume.shift(1).rolling(60).mean()
    signal=(d.close>d.high60)&(d.volume>=1_000_000)&(d.volume>=p["volume"]*vol)&(d.close*d.volume>=2_000_000_000)
    if p["trend"]:
        signal &= (d.close>d.ma120)&(d.ma60>d.ma120)&(d.ma20>d.ma60)
    if p["rsi"]:
        strength=rsi14(d.close)
        signal &= strength.between(50,75)
    d["signal"]=signal.fillna(False)
    return d
raw={};errors={}
for ticker in SYMBOLS:
    try:
        raw[ticker]=get_history(ticker)
        print(f"Fetched {ticker}: {len(raw[ticker])} bars",flush=True)
    except Exception as exc:
        errors[ticker]=str(exc)
        print(f"ERROR {ticker}: {exc}",flush=True)
if not raw:raise RuntimeError("No Yahoo history available; refusing fabricated metrics")
results=[]
for candidate,params in CANDIDATES.items():
    all_data={ticker:prepare(df,params) for ticker,df in raw.items()}
    for period,start,end in [("train","2020-01-01",TRAIN_END),("test",TEST_START,TEST_END)]:
        # Indicator warmup calculated on pre-period data; trading restricted to period.
        data={ticker:d.loc[start:end] for ticker,d in all_data.items()}
        data={ticker:d for ticker,d in data.items() if not d.empty}
        for mode in ["당일","5일","20일","추세"]:
            metrics,trades,eq=simulate(data,mode,10_000_000,2_000_000,.001,.001)
            if not metrics:continue
            results.append({"후보":candidate,"구간":period,**metrics,"신호수":sum(int(d.signal.sum()) for d in data.values())})
            prefix=f"{candidate}_{period}_{mode}"
            trades.to_csv(OUT/f"trades_{prefix}.csv",index=False,encoding="utf-8-sig")
            eq.rename("equity").to_csv(OUT/f"equity_{prefix}.csv",encoding="utf-8-sig")
            for freq,label in [("ME","monthly"),("YE","annual")]:
                ending=eq.resample(freq).last().dropna()
                before=ending.shift(1)
                if len(before):before.iloc[0]=10_000_000
                pd.DataFrame({"기간":ending.index.strftime("%Y-%m" if label=="monthly" else "%Y"),
                              "기초자산":before.values,"기말자산":ending.values,
                              "기간손익":(ending-before).values,
                              "기간수익률":(ending/before-1).values}).to_csv(
                                  OUT/f"{label}_{prefix}.csv",index=False,encoding="utf-8-sig")
summary=pd.DataFrame(results)
summary.to_csv(OUT/"comparison_train_test.csv",index=False,encoding="utf-8-sig")
(OUT/"methodology.json").write_text(json.dumps({
 "source":"Yahoo Finance unadjusted daily OHLCV","candidates":CANDIDATES,
 "train":"2020-01-01 to 2023-12-29","holdout":"2024-01-02 to 2026-09-30",
 "fees_each_side":0.001,"slippage_each_side":0.001,
 "download_failures":errors,
 "limitations":["Historical universe of 10 surviving tickers; survivorship bias",
 "No investor net buying data","Corporate actions in unadjusted prices may distort backtest",
 "Stop and take profit on entry day not simulated","Same-day intrabar stop/take order unknown",
 "Train/test periods use independent starting capital, not continuous compounding",
 "Profitable results not guaranteed; no candidate chosen based on test performance"]},
 ensure_ascii=False,indent=2),encoding="utf-8")
print(summary.to_string(index=False),flush=True)
