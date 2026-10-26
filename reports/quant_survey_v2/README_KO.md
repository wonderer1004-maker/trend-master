# 공개 연구 기반 퀀트 전략 비교 — V2

2026-10-17 수집. 미국 11 ETF, 국내 10개 생존 대형주와 KODEX200. 실제 종가 기준 2026-10-16까지.
논문 원형의 수익률을 재현한 것이 아니라, 명시한 매수 전용 적용 변형의 연구 결과입니다.
미국 수익률은 달러 기준이며 원화 환율·개인 세금은 제외합니다. 국내는 전 종목 검증이 아닙니다.
14개 후보 규칙을 결과 확인 전에 고정했습니다. 개발기간 선택 모델과 전체기간 사후 최고 모델을 구분합니다.
거래비용1·2배와 체결1·2거래일 지연을 모두 공개합니다. 조정 단위의 소수 수량을 사용합니다.
누락 거래일·투자 대상 선택 편향·논문 규칙과 차이는 protocol.json, calendar_audit.json, sources.json에서 확인하세요.

## US 전체기간

개발기간만으로 선택한 모델: **VOL15**

|전략|연복리|총수익률|최대낙폭|평균 위험자산 비중|
|---|---:|---:|---:|---:|
|GROWTH_HOLD|18.66%|1665.37%|-35.12%|100.0%|
|BENCH_HOLD|14.02%|804.58%|-33.72%|100.0%|
|VOL15|11.88%|557.33%|-20.94%|89.9%|
|CORE50|10.48%|432.84%|-22.66%|98.4%|
|CSM12_1|10.31%|418.92%|-24.95%|100.0%|
|BASKET_HOLD|9.94%|390.13%|-27.26%|100.0%|
|MOM_VOL18|9.91%|388.56%|-25.05%|98.3%|
|EW_MONTHLY|8.50%|292.97%|-23.24%|100.0%|
|MA200|8.15%|272.21%|-25.33%|84.3%|
|HIGH52|7.93%|259.95%|-24.90%|100.0%|
|MA10M|7.34%|228.38%|-27.88%|84.6%|
|INVVOL|7.10%|216.00%|-21.77%|100.0%|
|ENSEMBLE|6.70%|196.78%|-17.39%|82.9%|
|DUAL12|6.65%|194.59%|-24.54%|96.8%|
|LOWVOL|6.51%|188.33%|-22.52%|100.0%|
|TSM12|5.68%|152.86%|-12.66%|67.2%|
|BREAKOUT55|3.43%|76.15%|-26.45%|53.7%|
|R2|2.45%|50.07%|-30.98%|17.1%|

### 개발기간 선택 모델의 기간·비용별 결과

|기간|비용|지연|연복리|최대낙폭|지수보다 수익·낙폭 모두 개선|
|---|---:|---:|---:|---:|---|
|full|1배|1일|11.88%|-20.94%|False|
|full|1배|2일|11.59%|-21.18%|False|
|full|2배|1일|11.63%|-21.25%|False|
|full|2배|2일|11.34%|-21.48%|False|
|development|1배|1일|10.26%|-15.67%|False|
|development|1배|2일|10.21%|-16.22%|False|
|development|2배|1일|10.04%|-15.81%|False|
|development|2배|2일|9.99%|-16.36%|False|
|validation|1배|1일|12.86%|-20.94%|False|
|validation|1배|2일|12.16%|-21.18%|False|
|validation|2배|1일|12.52%|-21.25%|False|
|validation|2배|2일|11.82%|-21.48%|False|
|recent|1배|1일|16.12%|-15.11%|False|
|recent|1배|2일|16.13%|-14.92%|False|
|recent|2배|1일|15.88%|-15.17%|False|
|recent|2배|2일|15.89%|-14.98%|False|
|since2020|1배|1일|12.27%|-20.94%|False|
|since2020|1배|2일|11.70%|-21.18%|False|
|since2020|2배|1일|11.97%|-21.25%|False|
|since2020|2배|2일|11.40%|-21.48%|False|

## KR 전체기간

개발기간만으로 선택한 모델: **LOWVOL**

|전략|연복리|총수익률|최대낙폭|평균 위험자산 비중|
|---|---:|---:|---:|---:|
|LOWVOL|26.94%|404.74%|-38.05%|99.9%|
|HIGH52|26.90%|403.65%|-36.57%|99.9%|
|DUAL12|25.40%|364.79%|-43.18%|90.8%|
|CORE50|22.99%|307.25%|-41.99%|95.4%|
|INVVOL|21.17%|268.05%|-37.41%|99.9%|
|MA10M|21.08%|266.28%|-41.22%|66.6%|
|ENSEMBLE|20.69%|258.30%|-35.67%|72.9%|
|BENCH_HOLD|19.83%|241.35%|-41.22%|99.9%|
|CSM12_1|19.58%|236.53%|-53.20%|99.9%|
|BASKET_HOLD|19.45%|234.15%|-44.18%|99.9%|
|EW_MONTHLY|19.34%|231.95%|-37.82%|99.9%|
|MA200|18.80%|221.87%|-40.81%|65.3%|
|BREAKOUT55|15.39%|164.13%|-26.83%|36.0%|
|TSM12|13.98%|143.00%|-30.19%|60.9%|
|VOL15|12.01%|115.88%|-32.57%|74.7%|
|MOM_VOL18|8.65%|75.60%|-42.71%|62.4%|
|R2|0.65%|4.50%|-25.53%|14.8%|

### 개발기간 선택 모델의 기간·비용별 결과

|기간|비용|지연|연복리|최대낙폭|지수보다 수익·낙폭 모두 개선|
|---|---:|---:|---:|---:|---|
|full|1배|1일|26.94%|-38.05%|True|
|full|1배|2일|27.28%|-37.41%|True|
|full|2배|1일|25.35%|-38.28%|True|
|full|2배|2일|25.68%|-37.64%|True|
|development|1배|1일|23.54%|-38.05%|False|
|development|1배|2일|24.86%|-37.41%|False|
|development|2배|1일|21.93%|-38.28%|False|
|development|2배|2일|23.22%|-37.64%|False|
|recent_reused|1배|1일|32.96%|-19.94%|False|
|recent_reused|1배|2일|33.20%|-20.98%|False|
|recent_reused|2배|1일|31.32%|-20.00%|False|
|recent_reused|2배|2일|31.57%|-21.16%|False|

## 해석과 엄격한 통과 여부

국내 전체기간 기본비용 결과에서는 HIGH52, LOWVOL, INVVOL, ENSEMBLE이 지수보다 높은 연복리와 작은 최대낙폭을 보였습니다.
하지만 전체기간과 최근기간의 비용·지연 모든 조합에서 수익률과 낙폭을 동시에 개선한 능동 전략은 두 시장 모두 없었습니다.
LOWVOL은 국내 개발기간만으로 선택되었지만 최근기간에는 KODEX200보다 수익률이 낮았습니다. HIGH52의 최근 초과수익은 비용·지연에 민감합니다.
미국 장기 구간에서 이번 능동 후보는 SPY 단순 보유 수익률을 넘지 못했습니다. VOL15는 수익 일부를 포기하며 낙폭을 줄였습니다.
LOWVOL과 HIGH52는 각 3자산에 약 1/3씩 투자하는 집중 전략이며, 낮은 이름의 위험을 보장하지 않습니다.

## 조사한 원자료

- [시계열 모멘텀](https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum): TSM12: 현물 ETF/국내주식 매수만 허용한 변형; 원 논문의 롱숏·변동성 가중 미복제
- [상대 모멘텀](https://www.aqr.com/insights/research/journal-article/value-and-momentum-everywhere): CSM12_1, MOM_VOL18; 상위3·롱온리·월간은 본 연구의 고정 적용안
- [듀얼 모멘텀](https://www.optimalmomentum.com/research-papers/): DUAL12, CORE50: 기존 GEM 자산·규칙을 그대로 복제하지 않은 상위3 변형
- [10개월 이동평균](https://mebfaber.com/2017/12/13/episode-86-quantitative-approach-tactical-asset-allocation/): MA10M은 단일 주가지수 ETF에 적용; 미국 방어 자산 SHY, 국내 현금
- [장기 이동평균](https://mebfaber.com/2016/09/14/episode-20-listener-qa/): MA200은 일간 판단·다음 시가 체결 변형
- [변동성 관리](https://law.yale.edu/sites/default/files/area/workshop/leo/leo17_moreira.pdf): VOL15는 변동성 목표 15%·비차입·5%p 밴드의 별도 변형; 원 논문 역분산 전략 복제 아님
- [52주 고점](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.2004.00695.x): HIGH52: 종가/조정 고가252일 최고값 상위3, 월간, 매수만
- [저위험·저베타](https://www.aqr.com/insights/research/journal-article/betting-against-beta): LOWVOL은 60일 저변동성 상위3의 간접 시험; BAB의 베타 추정·공매도·레버리지 미복제
- [역변동성·위험분산](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1977577): INVVOL은 단순 역변동성 가중; 상관관계까지 고려한 정확한 위험균형 아님
- [단기 RSI 역추세](https://tradingmarkets.com/recent/the_improved_r2_strategy_84_correct_with_just_6_rules_-674361): R2: 당일 종가 체결 대신 다음 시가, 지수 ETF에만 적용
- [가격 돌파](https://www.turtletrader.com/rules/): BREAKOUT55는 지수ETF 매수 전용·종가 확인·20일 저가 청산 변형; 터틀 원형 재현 아님
- [가치](https://www.aqr.com/insights/research/journal-article/value-and-momentum-everywhere): 미검증: 공시 당시 장부가치·시총 데이터 부족
- [품질·수익성](https://www.aqr.com/Insights/Research/Working-paper/Quality-minus-Junk): 미검증: 시점별 재무와 공시 일시 부족; 현재 재무로 과거를 채우지 않음
- [페어 트레이딩](https://www.nber.org/papers/w7032): 미검증: 대차 가능 종목·비용·공매도 제약 이력 부재
- [장중 모멘텀](https://concretumgroup.com/beat-the-market-an-effective-intraday-momentum-strategy-for-sp500-etf-spy/): 미검증: 분봉·체결 자료 없음; 일봉으로 장중 성과를 만들지 않음
- [거래비용](https://www.aqr.com/insights/research/working-paper/trading-costs-of-asset-pricing-anomalies): 모든 후보에 비용1·2배와 1·2거래일 지연을 동일 적용
- [다중시험·과최적화](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf): 후보14개 사전고정·실패 포함 전부 공개·개발기간만으로 모델 선택; PBO 수치 자체를 계산한 것은 아님
- [단순 분산 기준선](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1376199): 동일비중 보유와 월간 리밸런싱을 기준선으로 포함
- [캐리](https://www.aqr.com/Insights/Research/Journal-Article/Carry): 미검증: 선물 만기구조·현선물 가격·통화 금리 차 자료 부족
- [실적발표 후 추세 PEAD](https://www.nber.org/papers/w11683): 미검증: 시점별 실적 예상치·서프라이즈·공시 일시 부재
- [머신러닝 팩터](https://www.nber.org/papers/w25398): 미검증: 당시 기업 특성 패널과 별도 학습·검증 데이터 부재; 가격 몇 개로 논문 수익을 재현하지 않음
- [옵션 변동성 프리미엄](https://www.nber.org/papers/w10912): 미검증: 당시 옵션 체인·스프레드·증거금·롤오버 자료 없음; ETF 배당률을 옵션 초과수익으로 간주하지 않음

## 고정 규칙

- **BENCH_HOLD**: SPY / KODEX200 buy and hold
- **GROWTH_HOLD**: QQQ buy and hold (US only)
- **BASKET_HOLD**: equal-weight initial basket; no rebalancing
- **EW_MONTHLY**: equal-weight basket; monthly rebalance
- **MA200**: benchmark above 200-day mean; daily state changes
- **MA10M**: benchmark above 10 completed month-end mean; monthly
- **TSM12**: each asset positive 252-session return versus defensive hurdle; 1/N slots
- **CSM12_1**: top 3 by return from 252 sessions ago to 21 sessions ago; monthly
- **DUAL12**: top 3 by 252-session return, each must beat SHY (US) or zero (KR); monthly
- **HIGH52**: top 3 by close / 252-session high; monthly
- **LOWVOL**: lowest 60-session volatility top 3; monthly; not BAB replication
- **INVVOL**: all assets weighted by inverse 60-session volatility; monthly; not exact risk parity
- **VOL15**: benchmark weight min(1, 15%/20-session annual volatility); daily with 5pp target band
- **BREAKOUT55**: benchmark close breaks prior 55-session high; exit below prior 20-session low; daily
- **R2**: benchmark above MA200, RSI2 falls 3 days with first below65; exit RSI2>75; daily next open
- **ENSEMBLE**: equal 1/3 blend of MA10M, TSM12 and DUAL12; monthly
- **CORE50**: 50% benchmark + 50% DUAL12; monthly
- **MOM_VOL18**: CSM12_1 weights scaled by min(1,18%/60-session portfolio volatility); monthly

## 확인 범위

과거 양의 수익과 향후 수익 보장은 다릅니다. 사후 최고 전략은 탐색 결과이며 새 검증이 필요합니다.
국내 데이터 날짜 누락은 같은 제공자에서 재수집해도 남아 공통 날짜만 사용했습니다. 실제 거래정지 처리의 대체가 아닙니다.
일별 자산·연도별 수익률·거래내역은 Actions 다운로드 자료의 details/에 있습니다. 실주문은 실행하지 않습니다.
