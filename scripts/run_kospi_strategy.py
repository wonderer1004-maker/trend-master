"""KOSPI-only, prespecified trend/pullback strategies; Yahoo daily OHLCV.

Research only: no profitability guarantee. Test period is never used to tune rules.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"reports"/"kospi_strategy"
OUT.mkdir(parents=True,exist_ok=True)
SYMBOLS={
 "005930.KS":"삼성전자","000660.KS":"SK하이닉스","005380.KS":"현대차",
 "035420.KS":"NAVER","005490.KS":"POSCO홀딩스","051910.KS":"LG화학",
 "068270.KS":"셀트리온","006400.KS":"삼성SDI","012330.KS":"현대모비스",
 "055550.KS":"신한지주"}
START="2020-01-01"; SPLIT="2024-01-01"; END="2026-09-30"
COST=0.001; SLIP=0.001; INITIAL=10_000_000
def download(symbol):
    x=yf.download(symbol,start="2018-12-01",end="2026-10-01",auto_adjust=True,
                  progress=False,threads=False,multi_level_index=False,timeout=30)
    if x.empty:raise ValueError("empty Yahoo response")
    if isinstance(x.columns,pd.MultiIndex):x.columns=x.columns.get_level_values(0)
    x=x[["Open","High","Low","Close","Volume"]].rename(columns=str.lower)
    x.index=pd.to_datetime(x.index).tz_localize(None)
    x=x.dropna()
    if len(x)<200:raise ValueError("insufficient history")
    return x
def features(x):
    d=x.copy()
    for n in (20,50,120,200):d[f"ma{n}"]=d.close.rolling(n).mean()
    d["high60"]=d.high.shift(1).rolling(60).max()
    d["low10"]=d.low.shift(1).rolling(10).min()
    d["vol20"]=d.volume.shift(1).rolling(20).mean()
    delta=d.close.diff()
    up=delta.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    down=(-delta.clip(upper=0)).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    d["rsi"]=100-100/(1+up/down.replace(0,np.nan))
    d["atr"]=(pd.concat([d.high-d.low,(d.high-d.close.shift()).abs(),
                           (d.low-d.close.shift()).abs()],axis=1).max(axis=1)
                .rolling(14).mean())
    return d
def signals(d,index,kind):
    market=(index.close>index.ma200)&(index.ma50>index.ma200)
    allowed=market.reindex(d.index).ffill().fillna(False).astype(bool)
    liquid=(d.close*d.volume>=5_000_000_000)
    trend=(d.close>d.ma120)&(d.ma50>d.ma120)&(d.ma120>d.ma200)
    if kind=="A_추세돌파":
        entry=(d.close>d.high60)&(d.volume>1.5*d.vol20)&d.rsi.between(50,75)
    elif kind=="B_눌림목회복":
        entry=(d.close>d.ma20)&(d.close.shift(1)<=d.ma20.shift(1))&(d.low10<=d.ma20*1.03)&d.rsi.between(45,70)
    elif kind=="C_강한돌파":
        entry=(d.close>d.high60)&(d.volume>2*d.vol20)&d.rsi.between(55,75)
    else:raise ValueError(kind)
    return (allowed&liquid&trend&entry).fillna(False)
def backtest(data,period_start,period_end,kind):
    # Signals computed using prior data; orders enter next session open.
    days=sorted(set().union(*(set(d.loc[period_start:period_end].index) for d in data.values())))
    cash=float(INITIAL);positions={};trades=[];equity=[]
    for day in days:
        # Exit existing positions first, then open new ones. Conservative stop-first.
        for symbol,p in list(positions.items()):
            d=data[symbol]
            if day not in d.index:continue
            row=d.loc[day]; age=p["age"]+1
            exit_px=None;reason=""
            if row.open<=p["stop"]:
                exit_px=float(row.open);reason="gap_stop"
            elif row.low<=p["stop"]:
                exit_px=p["stop"];reason="stop"
            elif row.open>=p["target"]:
                exit_px=float(row.open);reason="gap_target"
            elif row.high>=p["target"]:
                exit_px=p["target"];reason="target"
            elif age>=20 or (age>=1 and row.close<row.ma20):
                exit_px=float(row.close);reason="time_or_trend"
            if exit_px is not None:
                proceeds=p["qty"]*exit_px*(1-SLIP)*(1-COST)
                cash+=proceeds
                trades.append({"전략":kind,"종목":symbol,"매수일":p["date"].strftime("%Y-%m-%d"),
                               "매도일":day.strftime("%Y-%m-%d"),"매수가":p["buy"],
                               "매도가":exit_px,"수량":p["qty"],"실현손익":round(proceeds-p["cost"]),
                               "수익률":proceeds/p["cost"]-1,"청산사유":reason})
                del positions[symbol]
            else:p["age"]=age
        # Evaluate signals from previous trading session only.
        for symbol,d in data.items():
            if symbol in positions or len(positions)>=5 or day not in d.index:continue
            i=d.index.get_loc(day)
            if i==0 or not bool(d["signal"].iloc[i-1]):continue
            row=d.iloc[i];prev=d.iloc[i-1]
            buy=float(row.open)*(1+SLIP)
            stop=buy-max(0.05*buy,2*float(prev.atr))
            # Cap maximum initial loss at 8% and avoid zero/invalid stops.
            stop=max(stop,buy*0.92)
            risk_per_share=buy-stop
            if not np.isfinite(risk_per_share) or risk_per_share<=0:continue
            qty=int(min(2_000_000/(buy*(1+COST)),100_000/risk_per_share,
                        cash/(buy*(1+COST))))
            if qty<1:continue
            cost=qty*buy*(1+COST);cash-=cost
            positions[symbol]={"qty":qty,"buy":buy,"cost":cost,"date":day,
                               "stop":stop,"target":buy+2*risk_per_share,"age":0}
            # Entry-day OHLC is evaluated, stop-first if stop and target both hit.
            sell=None;reason=""
            if row.low<=stop:sell=stop;reason="entry_day_stop"
            elif row.high>=buy+2*risk_per_share:sell=buy+2*risk_per_share;reason="entry_day_target"
            if sell is not None:
                proceeds=qty*sell*(1-SLIP)*(1-COST);cash+=proceeds
                trades.append({"전략":kind,"종목":symbol,"매수일":day.strftime("%Y-%m-%d"),
                               "매도일":day.strftime("%Y-%m-%d"),"매수가":buy,
                               "매도가":sell,"수량":qty,"실현손익":round(proceeds-cost),
                               "수익률":proceeds/cost-1,"청산사유":reason})
                del positions[symbol]
        value=cash
        for symbol,p in positions.items():
            d=data[symbol].loc[:day]
            if not d.empty:value+=p["qty"]*float(d.close.iloc[-1])
        equity.append((day,value))
    # Liquidate at final close for accurate realized total.
    if days:
        for symbol,p in list(positions.items()):
            d=data[symbol].loc[:days[-1]]
            if d.empty:continue
            px=float(d.close.iloc[-1]);proceeds=p["qty"]*px*(1-SLIP)*(1-COST)
            cash+=proceeds
            trades.append({"전략":kind,"종목":symbol,"매수일":p["date"].strftime("%Y-%m-%d"),
                           "매도일":days[-1].strftime("%Y-%m-%d"),"매수가":p["buy"],
                           "매도가":px,"수량":p["qty"],"실현손익":round(proceeds-p["cost"]),
                           "수익률":proceeds/p["cost"]-1,"청산사유":"end_of_test"})
        equity[-1]=(days[-1],cash)
    eq=pd.Series(dict(equity),dtype=float).sort_index()
    trades=pd.DataFrame(trades)
    years=max((eq.index[-1]-eq.index[0]).days/365.25,1/365.25)
    return {"전략":kind,"기간":period_start[:4]+"-"+period_end[:4],
            "거래수":len(trades),"누적손익":round(cash-INITIAL),
            "총수익률":cash/INITIAL-1,"CAGR":(cash/INITIAL)**(1/years)-1,
            "MDD":float((eq/eq.cummax()-1).min()),
            "승률":float((trades["실현손익"]>0).mean()) if len(trades) else 0},trades,eq
def main():
    errors={};raw={}
    for symbol in ["^KS11",*SYMBOLS]:
        try:raw[symbol]=features(download(symbol));print("OK",symbol,flush=True)
        except Exception as e:errors[symbol]=str(e);print("FAILED",symbol,str(e),flush=True)
    if "^KS11" not in raw:raise RuntimeError("KOSPI market filter unavailable; abort")
    if len(raw)<3:raise RuntimeError("Insufficient KOSPI ticker coverage; abort")
    index=raw.pop("^KS11")
    metrics=[]
    for kind in ["A_추세돌파","B_눌림목회복","C_강한돌파"]:
        dataset={}
        for symbol,d in raw.items():
            d=d.copy();d["signal"]=signals(d,index,kind);dataset[symbol]=d
        for label,start,end in [("train","2020-01-01","2023-12-29"),
                                 ("holdout","2024-01-02",END)]:
            result,trades,eq=backtest(dataset,start,end,kind)
            result["구간"]=label;result["신호수"]=sum(int(d.loc[start:end,"signal"].sum()) for d in dataset.values())
            metrics.append(result)
            prefix=kind+"_"+label
            trades.to_csv(OUT/f"trades_{prefix}.csv",index=False,encoding="utf-8-sig")
            eq.rename("equity").to_csv(OUT/f"equity_{prefix}.csv",encoding="utf-8-sig")
            for freq,name in [("ME","monthly"),("YE","annual")]:
                e=eq.resample(freq).last();p=e.shift(1)
                if len(p):p.iloc[0]=INITIAL
                pd.DataFrame({"기간":e.index.strftime("%Y-%m" if name=="monthly" else "%Y"),
                              "기초자산":p.values,"기말자산":e.values,
                              "기간손익":(e-p).values,"기간수익률":(e/p-1).values}).to_csv(
                                  OUT/f"{name}_{prefix}.csv",index=False,encoding="utf-8-sig")
    pd.DataFrame(metrics).to_csv(OUT/"comparison.csv",index=False,encoding="utf-8-sig")
    (OUT/"methodology.json").write_text(json.dumps({
        "market":"KOSPI only; ^KS11 filter and .KS tickers",
        "universe":"10 selected KOSPI stocks, NOT the full historical KOSPI",
        "download_failures":errors,"price":"Yahoo auto-adjusted OHLCV",
        "initial_cash":INITIAL,"fee_each_side":COST,"slippage_each_side":SLIP,
        "risk_per_trade":100000,"max_positions":5,"max_holding_days":20,
        "test_rule":"predefined strategies, 2024+ holdout never used for parameter selection",
        "warnings":["No guaranteed profit","Survivorship bias","Not all KOSPI constituents",
                    "Daily OHLC does not reveal intraday sequence; stop-first conservative",
                    "Same-day entry stop approximation; open gaps and limits may worsen fills",
                    "No corporate action or delisting recovery validation"]},
        ensure_ascii=False,indent=2),encoding="utf-8")
    print(pd.DataFrame(metrics).to_string(index=False),flush=True)
if __name__=="__main__":main()
