"""Frozen-data PRICE-ONLY pilot; never represents the full Q-MULTI strategy."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

INITIAL = 10_000_000
ETF = '069500.KS'
SECTORS = {'000660.KS':'semiconductors','005930.KS':'semiconductors',
 '005380.KS':'autos','012330.KS':'autos','005490.KS':'materials',
 '006400.KS':'batteries','051910.KS':'chemicals','035420.KS':'internet',
 '055550.KS':'financials','068270.KS':'healthcare'}
MODELS = ('PRICE_PILOT','PRICE_NO_MARKET_FILTER','MOMENTUM_ONLY','BASKET_HOLD','KODEX200_HOLD')


def prepare(raw):
    calendar = raw[ETF].index
    for s,d in raw.items():
        if d.index.has_duplicates or not d.index.is_monotonic_increasing:
            raise ValueError(f'invalid dates: {s}')
        if not np.isfinite(d[['open','high','low','close','volume']]).all().all():
            raise ValueError(f'nonfinite input: {s}')
        if (d[['open','high','low','close']] <= 0).any().any():
            raise ValueError(f'invalid prices: {s}')
        calendar = calendar.intersection(d.index)
    # Intersect explicitly; every removed session is exported in calendar_audit.json.
    # This is a declared pilot limitation, not a repair of the source history.
    data = {}
    for s,x in raw.items():
        d = x.loc[calendar].copy()
        d['ma200'] = d.close.rolling(200).mean()
        d['ma60'] = d.close.rolling(60).mean()
        d['ma60_old'] = d.ma60.shift(20)
        d['mom'] = d.close.shift(21) / d.close.shift(126) - 1
        d['r5'] = d.close / d.close.shift(5) - 1
        d['turnover_proxy'] = (d.close*d.volume).rolling(20).mean()
        d['history'] = np.arange(len(d))+1
        data[s] = d
    m = data[ETF]
    above = m.close > m.ma200
    below = m.close < m.ma200
    states, cap = [], .3
    for i in range(len(m)):
        if i >= 2:
            if above.iloc[i-2:i+1].all(): cap = 1.
            elif below.iloc[i-2:i+1].all(): cap = .3
        states.append(cap)
    m['budget'] = states
    return data


def ranking(data, day, model):
    rows = pd.DataFrame({s:data[s].loc[day] for s in SECTORS}).T
    scores = rows.mom.rank(pct=True)
    if model != 'MOMENTUM_ONLY':
        scores = (2/3)*scores + (1/3)*(-rows.r5).rank(pct=True)
    return rows, sorted(scores.dropna().index, key=lambda s:(-scores[s],s))


def simulate(data, start, end, model, cost_multiplier=1):
    days = data[ETF].loc[start:end].index
    if len(days)<2: raise ValueError('not enough evaluation dates')
    # Start fully in cash: signals after the first evaluation close, fills next open.
    cash, holdings, peaks, pending = float(INITIAL), {}, {}, None
    orders, values = [], []
    last_budget = None
    for day in days:
        if pending is not None:
            target, signal_day, quantities = pending
            opens = {s:float(data[s].loc[day,'open']) for s in set(holdings)|set(target)}
            nav_open = cash+sum(q*opens[s] for s,q in holdings.items())
            desired = dict(target) if quantities else {s:int(nav_open*w/opens[s]) for s,w in target.items()}
            fee, slip = .0005*cost_multiplier, .001*cost_multiplier
            for side in ('SELL','BUY'):
                for s in sorted(set(holdings)|set(desired)):
                    current, goal = holdings.get(s,0), desired.get(s,0)
                    qty = current-goal if side=='SELL' else goal-current
                    if qty<=0: continue
                    if model not in ('BASKET_HOLD','KODEX200_HOLD'):
                        max_qty=int(float(data[s].loc[signal_day,'turnover_proxy'])*.001/opens[s])
                        qty=min(qty,max_qty)
                    if qty<=0: continue
                    px = opens[s]*(1-slip if side=='SELL' else 1+slip)
                    if side=='BUY' and model not in ('BASKET_HOLD','KODEX200_HOLD'):
                        if px > float(data[s].loc[signal_day,'close'])*1.03: continue
                    rate = fee + (.002*cost_multiplier if side=='SELL' and s!=ETF else 0)
                    if side=='BUY': qty = min(qty,int(cash/(px*(1+rate))))
                    if qty<=0: continue
                    if side=='SELL': cash += qty*px*(1-rate); holdings[s]=current-qty
                    else:
                        cash -= qty*px*(1+rate); holdings[s]=current+qty
                        if current==0: peaks[s]=px
                    orders.append(dict(signal_date=str(signal_day.date()),fill_date=str(day.date()),
                                       symbol=s,side=side,quantity=qty,price=px,cost_rate=rate))
                    if holdings[s]==0: del holdings[s]; peaks.pop(s,None)
        pending = None
        nav = cash+sum(q*float(data[s].loc[day,'close']) for s,q in holdings.items())
        if cash < -.01: raise AssertionError('negative cash')
        values.append(dict(date=day,equity=nav,cash=cash,positions=len(holdings)))
        if model in ('BASKET_HOLD','KODEX200_HOLD'):
            if day==days[0]:
                target = {ETF:1.} if model=='KODEX200_HOLD' else {s:.1 for s in SECTORS}
                pending = (target,day,False)
            continue
        budget = 1. if model=='PRICE_NO_MARKET_FILTER' else float(data[ETF].loc[day,'budget'])
        rows, ranks = ranking(data,day,model)
        stopped = set()
        for s in holdings:
            close = float(data[s].loc[day,'close'])
            peaks[s] = max(peaks.get(s,close),close)
            recent = data[s].loc[:day].tail(3)
            if close<=peaks[s]*.88 or (recent.close<recent.ma200).all(): stopped.add(s)
        # Exchange calendar is known; Friday close plans the next week's first session.
        pos = data[ETF].index.get_loc(day)
        following = data[ETF].index[pos+1] if pos+1<len(data[ETF]) else None
        weekly = day==days[0] or (following is not None and following.isocalendar()[:2]!=day.isocalendar()[:2])
        rebalance = weekly or budget!=last_budget
        if rebalance:
            chosen = [s for s in holdings if s not in stopped and s in ranks[:20]]
            for s in ranks[:10]:
                r=rows.loc[s]
                if s in chosen or s in stopped: continue
                eligible = (r.history>=252 and r.close>=3000 and r.turnover_proxy>=1e10
                            and r.close>r.ma200 and r.ma60>r.ma60_old)
                if model!='MOMENTUM_ONLY': eligible = eligible and -.08<=r.r5<=0
                if eligible and sum(SECTORS[x]==SECTORS[s] for x in chosen)<3:
                    chosen.append(s)
                if len(chosen)>=10: break
            pending = ({s:.1*budget for s in chosen},day,False)
        elif stopped:
            # Preserve quantities for other names; no incidental daily rebalancing.
            target = {s:holdings[s] for s in holdings if s not in stopped}
            pending = (target,day,True)
        last_budget = budget
    eq = pd.DataFrame(values).set_index('date')
    returns = eq.equity.pct_change().dropna()
    years=(days[-1]-days[0]).days/365.25
    path=np.r_[INITIAL,eq.equity.to_numpy()]
    stats=dict(initial_cash=INITIAL,end_value=float(path[-1]),
               total_return_pct=float((path[-1]/INITIAL-1)*100),
               cagr_pct=float(((path[-1]/INITIAL)**(1/years)-1)*100),
               mdd_pct=float((path/np.maximum.accumulate(path)-1).min()*100),
               sharpe_zero_rf=float(returns.mean()/returns.std()*np.sqrt(252)) if returns.std()>0 else 0.,
               order_count=len(orders),average_invested_pct=float(((eq.equity-eq.cash)/eq.equity).mean()*100),
               actual_start=str(days[0].date()),actual_end=str(days[-1].date()))
    return stats, eq, pd.DataFrame(orders)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--data-dir',default='reports/v8_20200101_20261012/input')
    ap.add_argument('--output',default='reports/q_multi_v1')
    a=ap.parse_args(); out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    raw={s:pd.read_csv(Path(a.data_dir)/(s+'.csv'),index_col=0,parse_dates=True) for s in [ETF,*SECTORS]}
    data=prepare(raw); end=str(data[ETF].index[-1].date()); summaries=[]
    calendar=data[ETF].index
    audit={s:[str(d.date()) for d in x.index.difference(calendar)] for s,x in raw.items()}
    (out/'calendar_audit.json').write_text(json.dumps(audit,indent=2))
    for period,start,finish in [('full','2020-01-01',end),('early','2020-01-01','2023-12-31'),('later_reused','2024-01-01',end)]:
        for model in MODELS:
            for cost in (1,2):
                met,eq,orders=simulate(data,start,finish,model,cost)
                key=f'{period}_{model}_{cost}x'
                eq.to_csv(out/(key+'_equity.csv'));orders.to_csv(out/(key+'_orders.csv'),index=False)
                summaries.append(dict(period=period,model=model,cost_multiplier=cost,**met))
    table=pd.DataFrame(summaries);table.to_csv(out/'comparison.csv',index=False)
    meta=dict(status='PARTIAL_PRICE_ONLY_PILOT_FULL_STRATEGY_BLOCKED',
        source_repo_commit='139950ab855f79f455eeb4bc7a01cef5688e2ad7',
        actual_last_date=end,original_weights=dict(momentum=.4,reversal=.2,quality=.4),
        pilot_weights=dict(momentum=2/3,reversal=1/3,quality=0),
        full_strategy_missing=['point-in-time ROE, operating cashflow, assets, operating profit and publication timestamps',
          'historical all-stock membership, delistings and trading/risk status',
          'KOSPI index (pilot substitutes KODEX200)', '09:05 quotes and 09:15 fill/cancel history'],
        execution='prior close signals, following session daily open proxy, integer shares, buy gap ceiling 3%',
        costs=dict(fee_each_side=.0005,slippage_each_side=.001,stock_sell_tax=.002,etf_sell_tax=0,
                   note='fixed research assumptions, NOT historical date-specific actual taxes; all doubled in 2x'),
        limitations=['10 surviving stocks only; NOT Korea full market',
          'source calendar discrepancies: explicit common-session intersection; see calendar_audit.json; missing sessions are not reconstructed',
          'frozen Yahoo adjusted OHLC from existing repo, not independently re-downloaded or verified',
          'adjusted close*volume turnover proxy and adjusted 3000KRW cutoff are not raw historical traded values',
          'KODEX200 adjusted prices used as market and investable benchmark, not exact KOSPI200 total-return index',
          'no explicit tax-adjusted cash dividends; provider adjustment relied upon',
          'daily open is NOT 09:05 execution, no intraday liquidity simulation',
          'all periods previously inspected; later period is NOT independent out-of-sample',
          '20-rank retention rarely binds with only 10 stocks',
          'baseline baskets exempt from entry gap ceiling; comparisons are illustrative',
          'no live brokerage orders, no parameters optimized, cash interest zero'],
        input_sha256={s:hashlib.sha256((Path(a.data_dir)/(s+'.csv')).read_bytes()).hexdigest() for s in raw})
    (out/'methodology.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    print(table[['period','model','cost_multiplier','total_return_pct','cagr_pct','mdd_pct','order_count']].to_string(index=False))
    lines=['# Q-MULTI V1: 가격 신호 부분시험', '',
      '**원안 전체는 검증되지 않았습니다.** 과거 공시 시점별 재무 데이터와 전 종목 이력이 없어 원안 검증은 차단했습니다.',
      f'실제 데이터 마지막 날짜: {end}. 현재 시점까지의 결과로 표시하지 않습니다.', '',
      '가격 부분시험은 모멘텀 2/3 + 단기 눌림 1/3이며, 원안의 재무품질 40%를 포함하지 않습니다.',
      '기존 저장소의 생존 대형주 10개와 KODEX200만 사용했습니다. 코스피 지수 대신 KODEX200을 시장 필터에 사용합니다.',
      '전일 종가 판단 → 다음 거래일 시가 체결 가정. 09:05 실제 체결 검증이 아닙니다.',
      '비용 1배: 편도 수수료 0.05%, 슬리피지 0.10%, 개별주 매도세금 0.20% 고정 가정. 2배도 비교합니다.',
      '조정주가×거래량은 실제 과거 거래대금과 다르며, 당시 상장폐지·관리종목도 반영하지 못했습니다.',
      '원본 종목·ETF 간 날짜 불일치가 있어 공통 날짜만 시험했습니다. 제외 날짜는 calendar_audit.json에 공개하며, 누락 거래일을 복원한 완전한 이력이 아닙니다.',
      '과거에 이미 살펴본 기간이므로 독립적인 표본 외 성과가 아닙니다. 최적화는 하지 않았습니다.', '',
      '|기간|전략|비용|총수익률|연복리|최대낙폭|주문수|',
      '|---|---|---:|---:|---:|---:|---:|']
    for r in summaries:
        lines.append(f"|{r['period']}|{r['model']}|{r['cost_multiplier']}배|{r['total_return_pct']:.2f}%|{r['cagr_pct']:.2f}%|{r['mdd_pct']:.2f}%|{r['order_count']}|")
    lines += ['', 'PRICE_PILOT=가격 부분시험, PRICE_NO_MARKET_FILTER=시장필터 제외, MOMENTUM_ONLY=눌림 제외, BASKET_HOLD=같은 10종목 동일비중 보유, KODEX200_HOLD=KODEX200 보유.',
      '', '원안 전체의 수익률을 얻으려면 공시 공개일이 포함된 재무 데이터, 당시 투자 가능 종목·업종·규제 상태, 실제 거래대금, 코스피 지수와 분봉 체결 자료를 확보해야 합니다.',
      '이 결과만으로 원안의 우수성이나 세계대회 수상자의 성과를 주장할 수 없습니다.']
    (out/'README_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')

if __name__=='__main__': main()
