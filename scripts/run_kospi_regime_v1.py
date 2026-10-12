"""KOSPI three-regime strategy research; Yahoo Finance, no profit guarantee.

Market regime is calculated on each day's close; trade signals execute next open.
Bull: breakout / pullback; Sideways: range rebound; Bear: no new longs.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from run_kospi_strategy import download,features,backtest,SYMBOLS,END,INITIAL

OUT=Path(__file__).resolve().parents[1]/"reports"/"kospi_regime_v1"
OUT.mkdir(parents=True,exist_ok=True)

def regime(k):
    """Use only contemporaneously observable KOSPI daily data."""
    d=k.copy()
    ma20=d.close.rolling(20).mean()
    ma60=d.close.rolling(60).mean()
    ma200=d.close.rolling(200).mean()
    momentum60=d.close.pct_change(60)
    # avoid fast flipping around 200-day line using a 2% deadband
    bull=(d.close>ma200*1.02)&(ma20>ma60)&(momentum60>0.03)
    bear=(d.close<ma200*0.98)&(ma20<ma60)&(momentum60< -0.03)
    label=pd.Series("SIDEWAYS",index=d.index,dtype=object)
    label.loc[bull]="BULL"
    label.loc[bear]="BEAR"
    return label

def entries(d,r,kind):
    r=r.reindex(d.index).ffill().fillna("BEAR")
    liquid=(d.close*d.volume).rolling(20).mean()>=5_000_000_000
    trend=(d.close>d.ma120)&(d.ma50>d.ma120)&(d.ma120>d.ma200)
    # Every entry is determined at close, then filled at next session's open.
    breakout=trend&(d.close>d.high60)&(d.volume>=1.5*d.vol20)&d.rsi.between(50,75)
    pullback=trend&(d.close>d.ma20)&(d.close.shift(1)<=d.ma20.shift(1))&d.rsi.between(45,70)
    # Sideways: rising from short-term oversold, not chasing a breakout.
    range_trade=(d.close>d.ma20)&(d.close.shift(1)<=d.ma20.shift(1))&(d.rsi.shift(1)<45)&d.rsi.between(40,60)&(d.close>d.ma200)
    if kind=="R1_강세돌파_보합현금":
        sig=(r=="BULL")&breakout
    elif kind=="R2_강세눌림_보합반등":
        sig=((r=="BULL")&pullback)|((r=="SIDEWAYS")&range_trade)
    elif kind=="R3_강세혼합_보합반등":
        sig=((r=="BULL")&(breakout|pullback))|((r=="SIDEWAYS")&range_trade)
    else:raise ValueError(kind)
    return (liquid&sig).fillna(False)

def main():
    errors={};raw={}
    for symbol in ["^KS11",*SYMBOLS]:
        try:
            raw[symbol]=features(download(symbol))
            print("downloaded",symbol,flush=True)
        except Exception as e:
            errors[symbol]=str(e);print("FAILED",symbol,str(e),flush=True)
    if "^KS11" not in raw:raise RuntimeError("KOSPI index download failed: cannot evaluate market regime")
    if len(raw)<3:raise RuntimeError("Insufficient stock history")
    market=raw.pop("^KS11")
    states=regime(market)
    states.rename("market_regime").to_csv(OUT/"daily_market_regime.csv",encoding="utf-8-sig")
    kinds=["R1_강세돌파_보합현금","R2_강세눌림_보합반등","R3_강세혼합_보합반등"]
    rows=[]
    for kind in kinds:
        dataset={}
        for ticker,d in raw.items():
            d=d.copy();d["signal"]=entries(d,states,kind);dataset[ticker]=d
        for label,start,end in [("train","2020-01-01","2023-12-29"),
                                 ("holdout","2024-01-02",END)]:
            m,trades,equity=backtest(dataset,start,end,kind)
            m["구간"]=label
            m["매수신호수"]=sum(int(d.loc[start:end,"signal"].sum()) for d in dataset.values())
            rows.append(m)
            key=kind+"_"+label
            trades.to_csv(OUT/f"trades_{key}.csv",index=False,encoding="utf-8-sig")
            equity.rename("equity").to_csv(OUT/f"equity_{key}.csv",encoding="utf-8-sig")
            for freq,title in [("ME","monthly"),("YE","annual")]:
                x=equity.resample(freq).last()
                p=x.shift(1)
                if len(p):p.iloc[0]=INITIAL
                pd.DataFrame({"period":x.index.strftime("%Y-%m" if title=="monthly" else "%Y"),
                              "start_equity":p.values,"end_equity":x.values,
                              "pnl":(x-p).values,"return":(x/p-1).values}).to_csv(
                                  OUT/f"{title}_{key}.csv",index=False,encoding="utf-8-sig")
    pd.DataFrame(rows).to_csv(OUT/"comparison.csv",index=False,encoding="utf-8-sig")
    (OUT/"methodology.json").write_text(json.dumps({
        "status":"candidate strategy, not verified profitable",
        "regime":"bull above 200MA by 2%, 20MA>60MA, 60-day return>3%; bear below 200MA by 2%, 20MA<60MA, 60-day return<-3%; otherwise sideways",
        "strategies":kinds,"bear_policy":"no new buys; existing positions follow original stop/trend exits",
        "universe":"10 KOSPI survivors, not full KOSPI; survivorship bias",
        "trade_execution":"next session open; daily OHLC stop-first approximation",
        "fees":"0.1% fee plus 0.1% slippage each side",
        "split":"2020-2023 train; 2024-2026-09 holdout",
        "limitations":["not market-wide","no leverage or shorting","no regime-change forced liquidation",
                       "range strategy shares trend exit and 2R take profit from original simulator",
                       "backtest not independently verified","corporate actions and delistings may bias results"],
        "download_errors":errors},ensure_ascii=False,indent=2),encoding="utf-8")
    print(pd.DataFrame(rows).to_string(index=False),flush=True)
if __name__=="__main__":main()
