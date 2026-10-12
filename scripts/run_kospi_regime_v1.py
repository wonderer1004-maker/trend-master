"""KOSPI three-regime strategy research; Yahoo Finance, no profit guarantee.

Market regime is calculated on each day's close; trade signals execute next open.
Bull: breakout / pullback; Sideways: range rebound; Bear: no new longs.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from run_kospi_strategy import download,features,SYMBOLS,END,INITIAL,COST,SLIP

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

def backtest(data,period_start,period_end,kind):
    # Signals computed using prior data; orders enter next session open.
    days=sorted(set().union(*(set(d.loc[period_start:period_end].index) for d in data.values())))
    cash=float(INITIAL);positions={};trades=[];equity=[]
    for day in days:
        # Evaluate signals from previous trading session only.\n        opened_today=set()
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
            opened_today.add(symbol)\n            # Entry-day OHLC is evaluated, stop-first if stop and target both hit.
            sell=None;reason=""
            if row.open<=stop:sell=float(row.open);reason="entry_day_gap_stop"\n            elif row.low<=stop:sell=stop;reason="entry_day_stop"
            elif row.high>=buy+2*risk_per_share:sell=buy+2*risk_per_share;reason="entry_day_target"
            if sell is not None:
                proceeds=qty*sell*(1-SLIP)*(1-COST);cash+=proceeds
                trades.append({"전략":kind,"종목":symbol,"매수일":day.strftime("%Y-%m-%d"),
                               "매도일":day.strftime("%Y-%m-%d"),"매수가":buy,
                               "매도가":sell,"수량":qty,"실현손익":round(proceeds-cost),
                               "수익률":proceeds/cost-1,"청산사유":reason})
                del positions[symbol]
        # Existing positions exit AFTER today's open purchases. Conservative cash sequencing.
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
        # Existing positions sold at today's close cannot finance today's open buys.
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
        "trade_execution":"next session open; new purchases funded only by start-of-day cash; stop-first daily OHLC approximation",
        "fees":"0.1% fee plus 0.1% slippage each side",
        "split":"2020-2023 train; 2024-2026-09 holdout",
        "limitations":["not market-wide","no leverage or shorting","no regime-change forced liquidation",
                       "range strategy shares trend exit and 2R take profit from original simulator",
                       "backtest not independently verified","corporate actions and delistings may bias results"],
        "download_errors":errors},ensure_ascii=False,indent=2),encoding="utf-8")
    print(pd.DataFrame(rows).to_string(index=False),flush=True)
if __name__=="__main__":main()
