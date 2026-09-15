import streamlit as st
import pandas as pd
from .providers import us_history, kr_history, benchmark_history
from .scoring import score_symbol
from .backtest import run_breakout_backtest

st.set_page_config(page_title='Trend Master', layout='wide')
st.title('TREND MASTER — Scanner + Backtest')
market = st.selectbox('Market', ['US','KR'])
raw = st.text_input('Symbols', 'AAPL,MSFT,NVDA,AMZN,META' if market=='US' else '005930,000660,373220')
symbols=[x.strip() for x in raw.split(',') if x.strip()]

st.sidebar.header('Backtest')
cash=st.sidebar.number_input('Initial cash', 1_000_000, 1_000_000_000, 10_000_000, step=1_000_000)
risk=st.sidebar.slider('Risk / trade', .002, .02, .01, .001)
breakout=st.sidebar.selectbox('Breakout', [20,55], index=1)
fee=st.sidebar.number_input('Fee rate', 0.0, .01, .00015, format='%.5f')
slippage=st.sidebar.number_input('Slippage', 0.0, .02, .0005, format='%.5f')

if st.button('Scan + Backtest'):
    bench=benchmark_history(market)
    rows=[]
    for s in symbols:
        df=us_history(s) if market=='US' else kr_history(s)
        sc=score_symbol(df,bench)
        bt=run_breakout_backtest(df,cash,risk,breakout,fee_rate=fee,slippage=slippage)
        rows.append({'symbol':s,**sc,'backtest_CAGR':bt['metrics'].get('CAGR'),'backtest_MDD':bt['metrics'].get('MDD'),'backtest_trades':bt['metrics'].get('trade_count')})
    result=pd.DataFrame(rows).sort_values('score',ascending=False)
    st.subheader('Scanner')
    st.dataframe(result,use_container_width=True)
    st.subheader('Backtest detail')
    for s in symbols:
        df=us_history(s) if market=='US' else kr_history(s)
        bt=run_breakout_backtest(df,cash,risk,breakout,fee_rate=fee,slippage=slippage)
        if bt['metrics']:
            st.markdown(f'### {s}')
            m=bt['metrics']; c1,c2,c3,c4=st.columns(4)
            c1.metric('CAGR',f"{m['CAGR']:.2%}"); c2.metric('MDD',f"{m['MDD']:.2%}"); c3.metric('Win rate',f"{m['win_rate']:.2%}"); c4.metric('Profit Factor',f"{m['profit_factor']:.2f}")
            if len(bt['equity']): st.line_chart(bt['equity'])
            if not bt['trades'].empty: st.dataframe(bt['trades'],use_container_width=True)
