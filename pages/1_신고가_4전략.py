"""신고가 4전략 비교: 기존 Trend Master Streamlit 멀티페이지 확장."""
import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, timedelta

st.set_page_config(page_title="신고가 4전략 백테스트",layout="wide")
st.title("신고가 조건식 — 4전략 백테스트")
st.caption("키움 조건식의 일봉 근사 재현. 실제 투자자별 수급 데이터 조회 실패 시 결과를 만들지 않습니다.")

@st.cache_data(ttl=86400,show_spinner=False)
def fetch(code,start,end):
    from pykrx import stock
    a,b=start.strftime("%Y%m%d"),end.strftime("%Y%m%d")
    o=stock.get_market_ohlcv_by_date(a,b,code,adjusted=True)
    v=stock.get_market_trading_volume_by_date(a,b,code)
    if o is None or o.empty or v is None or v.empty: raise ValueError("가격 또는 투자자 수급 데이터 없음")
    for col in ["외국인합계","기관합계"]:
        if col not in v.columns: raise ValueError("수급 컬럼 누락: "+col)
    d=o.join(v[["외국인합계","기관합계"]],how="left")
    if d[["외국인합계","기관합계"]].isna().any().any():
        raise ValueError("외국인/기관 수급 데이터 누락: 정확한 조건 검증 불가")
    d=d.rename(columns={"시가":"open","고가":"high","저가":"low","종가":"close","거래량":"volume","외국인합계":"foreign","기관합계":"institution"})
    return d.sort_index()

def prepare(d,vol_multiple=5):
    d=d.copy()
    # 신고가: 종가가 이전 60봉 최고가를 상향 돌파. 장중 신고가와 구분됨.
    d["high60"]=d.high.shift(1).rolling(60).max()
    d["v60"]=d.volume.shift(1).rolling(60).mean()
    d["ma20"]=d.close.rolling(20).mean()
    d["signal"]=(d.volume>=1_000_000)&(d.close>d.high60)&(d.volume>=d.v60*vol_multiple)&(d.foreign.gt(0).rolling(60).max().eq(1))&(d.institution.gt(0).rolling(60).max().eq(1))&(d.close*d.volume>=2_000_000_000)
    return d

def simulate(data,mode,capital,allocation,fee,slip):
    # 다종목 공유 현금·동시보유 제한·종가 평가를 반영.
    dates=sorted(set().union(*(set(d.index) for d in data.values())))
    cash=float(capital); positions={}; trades=[]; curve=[]
    maxdays={"당일":0,"5일":5,"20일":20,"추세":60}[mode]
    for day in dates:
        # 기존 포지션의 손절/익절/기간 종료. 시가 갭을 고려하고 같은 날 충돌 시 손절 우선.
        for code,p in list(positions.items()):
            d=data[code]
            if day not in d.index:continue
            row=d.loc[day]; age=p["age"]
            sell=None;reason=""
            if float(row.open)<=p["entry"]*.95:
                sell=float(row.open);reason="갭 손절"
            elif float(row.low)<=p["entry"]*.95:
                sell=p["entry"]*.95;reason="손절"
            elif float(row.open)>=p["entry"]*1.2:
                sell=float(row.open);reason="갭 익절"
            elif float(row.high)>=p["entry"]*1.2:
                sell=p["entry"]*1.2;reason="익절"
            elif mode=="추세" and age>=1 and float(row.close)<float(row.ma20):
                sell=float(row.close);reason="20일선 이탈"
            elif age>=maxdays-1 and mode!="당일":
                sell=float(row.close);reason="기간 종료"
            if sell is not None:
                net=p["qty"]*sell*(1-slip)*(1-fee)
                cash+=net
                pnl=net-p["cost"]
                trades.append({"전략":mode,"종목":code,"매수일":p["date"].date(),"매도일":day.date(),"손익":round(pnl),"수익률":pnl/p["cost"],"사유":reason})
                del positions[code]
            else:p["age"]+=1
        # 전일 확정 신호만 사용하고 오늘 시가에 진입
        for code,d in data.items():
            if code in positions or len(positions)>=5 or day not in d.index:continue
            i=d.index.get_loc(day)
            if i==0 or not bool(d.signal.iloc[i-1]):continue
            px=float(d.open.iloc[i])*(1+slip)
            if px<=0:continue
            qty=int(min(allocation,cash)/(px*(1+fee)))
            if qty<=0:continue
            cost=qty*px*(1+fee)
            cash-=cost
            positions[code]={"entry":px,"qty":qty,"cost":cost,"date":day,"age":0}
        if mode=="당일":
            for code,p in list(positions.items()):
                d=data[code]
                if day not in d.index:continue
                px=float(d.loc[day,"close"])
                net=p["qty"]*px*(1-slip)*(1-fee);cash+=net
                pnl=net-p["cost"]
                trades.append({"전략":mode,"종목":code,"매수일":day.date(),"매도일":day.date(),"손익":round(pnl),"수익률":pnl/p["cost"],"사유":"당일 종가"})
                del positions[code]
        value=cash
        for code,p in positions.items():
            d=data[code]
            hist=d.loc[:day]
            if not hist.empty:value+=p["qty"]*float(hist.close.iloc[-1])
        curve.append((day,value))
    if dates:
        for code,p in positions.items():
            hist=data[code].loc[:dates[-1]]
            px=float(hist.close.iloc[-1]);net=p["qty"]*px*(1-slip)*(1-fee)
            pnl=net-p["cost"];cash+=net
            trades.append({"전략":mode,"종목":code,"매수일":p["date"].date(),"매도일":dates[-1].date(),"손익":round(pnl),"수익률":pnl/p["cost"],"사유":"테스트 종료"})
        if curve:curve[-1]=(dates[-1],cash)
    eq=pd.Series(dict(curve),dtype=float)
    t=pd.DataFrame(trades)
    if eq.empty:return {},t,eq
    yrs=max((eq.index[-1]-eq.index[0]).days/365.25,1/365.25)
    m={"전략":mode,"거래수":len(t),"누적손익":round(cash-capital),"총수익률":cash/capital-1,
       "CAGR":(cash/capital)**(1/yrs)-1 if cash>0 else -1,
       "MDD":(eq/eq.cummax()-1).min(),
       "승률":float((t["손익"]>0).mean()) if len(t) else 0}
    return m,t,eq

st.warning("전체 코스피 백테스트가 아니라 입력한 종목만 검증합니다. 상장폐지 종목 누락 시 생존편향이 발생합니다. 60봉 신고가는 '종가가 이전 60일 최고가 돌파'로 근사했습니다.")
codes=st.text_input("코스피 종목코드 (쉼표 구분)","005930,000660,005380")
start=st.date_input("시작일",date(2020,1,1))
end=st.date_input("종료일",date(2026,9,30))
capital=st.number_input("초기 투자금(원)",min_value=1_000_000,value=10_000_000,step=1_000_000)
allocation=st.number_input("종목당 최대 투자금(원)",min_value=100_000,value=2_000_000,step=100_000)
fee=st.number_input("편도 수수료+세금 가정(비율)",min_value=0.0,max_value=0.02,value=0.001,format="%.4f")
slip=st.number_input("편도 슬리피지(비율)",min_value=0.0,max_value=0.02,value=0.001,format="%.4f")
if st.button("4전략 백테스트 실행",type="primary"):
    if start>=end:st.error("종료일은 시작일 이후여야 합니다.");st.stop()
    symbols=list(dict.fromkeys(x.strip() for x in codes.split(",") if x.strip()))
    if not symbols:st.error("종목코드를 입력하세요.");st.stop()
    data={};errors=[]
    with st.spinner("과거 가격 및 외국인·기관 수급 조회 중..."):
        for code in symbols:
            try:
                d=prepare(fetch(code,start-timedelta(days=180),end))
                d=d.loc[(d.index>=pd.Timestamp(start))&(d.index<=pd.Timestamp(end))]
                if not d.empty:data[code]=d
                else:errors.append(code+": 유효한 데이터 없음")
            except Exception as e:errors.append(code+": "+str(e))
    if errors:st.error("일부 종목 조회 실패: "+" / ".join(errors))
    if not data:st.stop()
    metrics=[];all_trades=[]
    for mode in ["당일","5일","20일","추세"]:
        m,t,eq=simulate(data,mode,capital,allocation,fee,slip)
        metrics.append(m)
        if not t.empty:all_trades.append(t)
        with st.expander(mode+" 자산곡선"):
            st.line_chart(eq)
    st.subheader("4전략 비교")
    st.dataframe(pd.DataFrame(metrics),use_container_width=True)
    if all_trades:
        trades=pd.concat(all_trades,ignore_index=True)
        st.download_button("거래내역 CSV 다운로드",trades.to_csv(index=False).encode("utf-8-sig"),"신고가_4전략_거래내역.csv","text/csv")
        st.dataframe(trades,use_container_width=True)
    st.caption("일봉 고가·저가의 발생 순서를 알 수 없어 장중 손절/익절 체결은 근사치입니다. 진입 당일 손절·익절 미반영, 편도 거래비용은 가정치입니다. 결과는 실거래 보장이 아닙니다.")
