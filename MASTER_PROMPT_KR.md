# Claude Code / Codex 붙여넣기용 MASTER PROMPT

너는 시니어 퀀트 개발자이자 시스템 트레이더다.

아래 사양으로 국내·미국 주식 통합 추세추종 종목검색 시스템을 완성하라.

## 1. 핵심 전략

다음 대가들의 공통 원칙만 결합한다.

1. Jesse Livermore — 강한 종목 추종, 신고가/피벗 돌파
2. Stan Weinstein — Stage 1~4, Stage 2 우선
3. Turtle Trading — 20일/55일 돌파, ATR 기반 위험관리
4. William O'Neil — 성장성, 상대강도, 거래량, 돌파
5. Mark Minervini — 50/150/200일 추세 정렬, 고점 근접, VCP
6. Darvas — 박스권 돌파
7. Buffett/Dalio — 펀더멘털 품질과 시장 국면은 보조 필터로만 사용

## 2. 절대 원칙

- 가격이 하락한다고 싸다고 판단하지 말 것.
- Stage 4 종목은 매수 후보에서 제외.
- 시장 추세가 나쁘면 신규 매수 신호를 강하게 제한.
- 단일 지표 하나만으로 BUY를 만들지 말 것.
- 미래 데이터를 사용하지 않는 백테스트(no look-ahead)를 보장할 것.
- 분할/배당/상장폐지 종목을 고려한 데이터 정합성 검사를 구현할 것.
- 실제 주문 실행은 기본 OFF.
- 투자금의 1회 거래 위험은 기본 1% 이하로 제한.
- ATR 기반 손절과 포지션 사이징을 제공.
- 신호 발생 시 근거를 사람이 읽을 수 있게 출력.

## 3. 100점 스코어

시장 20:
- 시장 지수 > 150일선
- 150일선 상승
- 시장 breadth/신고가 비율
- 변동성/리스크오프 필터

Weinstein 20:
- 30주선 위
- 30주선 상승
- Stage 2

Livermore/Turtle 20:
- 20일 신고가 돌파
- 55일 신고가 돌파
- 52주 고점 5% 이내
- 돌파 후 유지

O'Neil/Minervini 20:
- 50일선 > 150일선
- 150일선 상승
- 50일선 위
- 상대강도 상위

Volume/RS/Industry 20:
- 거래량 1.5배/2배
- 상대강도
- 업종 강도
- 수급/기관·외국인(국내에서 데이터 제공 시)

점수:
90+ STRONG_BUY_CANDIDATE
80~89 BUY_CANDIDATE
70~79 READY
60~69 WATCH
<60 AVOID

## 4. 진입

신호는 세 가지로 분리한다.

A. Breakout Entry
- 20일 또는 55일 고점 돌파
- 거래량 확인
- 시장/업종 필터 통과

B. Pullback Entry
- 돌파가격/20일선/50일선 지지
- 거래량 감소 후 반등
- 이전 돌파 레벨 회복

C. VCP Entry
- 변동성 수축
- 거래량 수축
- pivot 돌파

각 신호에 대해:
- entry zone
- invalidation
- initial stop
- ATR
- risk/reward
를 계산한다.

## 5. 리스크 관리

사용자 계좌를 입력받는다.

risk_amount = account_equity * 0.01
stop_distance = entry - stop
shares = floor(risk_amount / stop_distance)

추가 제한:
- 한 종목 최대 계좌의 20%
- 동일 업종 합산 최대 35%
- 시장 위험도가 높으면 신규 포지션 축소
- 레버리지 ETF/인버스는 장기 핵심자산과 분리

## 6. 결과 화면

국내 TOP 20 / 미국 TOP 20을 각각 출력한다.

컬럼:
순위
종목
점수
신호
Stage
20D breakout
55D breakout
RS
Volume Ratio
50DMA
150DMA
52W High Distance
ATR
Entry Zone
Stop
Risk/Reward
핵심 근거
경고

그리고 다음 목록을 별도로 만든다.

- 오늘 매수 후보
- 돌파 임박
- 눌림목 후보
- 관찰
- 매도/추세붕괴 후보

## 7. 시장 국면

시장 상태를:
BULL / NEUTRAL / BEAR
로 분류한다.

BULL:
신규 매수 정상

NEUTRAL:
신규 매수 50% 축소

BEAR:
신규 매수 금지 또는 매우 엄격한 예외만 허용

## 8. 백테스트

다음 결과를 제공한다.

- CAGR
- MDD
- 승률
- Profit Factor
- 평균 이익
- 평균 손실
- Sharpe
- 연도별 수익률
- 거래횟수
- 최대 연속손실
- 시장 Buy & Hold 비교

반드시 수수료/슬리피지 옵션을 제공하고 look-ahead bias를 방지한다.

## 9. 자동화

매일:
1. 데이터 업데이트
2. 시장 국면 계산
3. 국내 전체 유니버스 스캔
4. 미국 전체 유니버스 스캔
5. 점수 계산
6. 신호 생성
7. CSV/SQLite 저장
8. 대시보드 업데이트
9. 알림 메시지 생성

실제 주문은 별도 승인 단계 없이는 절대 실행하지 않는다.

## 10. 품질검증

다음 테스트를 반드시 만든다.

- 지표 계산 테스트
- Stage 분류 테스트
- 돌파 테스트
- ATR 테스트
- 포지션 사이징 테스트
- look-ahead 테스트
- 결측치 테스트
- 분할/배당 조정 테스트
- 한국/미국 ticker 처리 테스트

## 11. 개발 순서

1. 데이터 계층
2. 지표
3. 점수 엔진
4. 시장 국면
5. 리스크 엔진
6. 백테스트
7. DB
8. 대시보드
9. 스케줄러
10. 알림
11. 테스트
12. 문서

각 단계마다 실행 가능한 상태를 유지하고, 실패하면 원인을 찾아 수정하라.
기존 기능을 깨뜨리지 말고 테스트를 통과한 후 다음 단계로 넘어가라.

## 12. 백테스트 엔진 상세 구현

기존 프로젝트에 백테스트 모듈을 추가하라.

### 반드시 지킬 것
- 신호는 t일 종가까지 사용하고 체결은 t+1 시가부터 가능하게 한다.
- look-ahead bias를 금지한다.
- 수수료, 세금(시장별 옵션), 슬리피지를 파라미터화한다.
- ATR 기반 초기 손절을 사용한다.
- 50일선 이탈 등 추세 훼손 청산을 지원한다.
- 거래내역을 모두 저장한다.

### 백테스트 모드
1. 20일 Turtle breakout
2. 55일 Turtle breakout
3. Weinstein Stage 2 + breakout
4. Minervini trend template + breakout
5. 통합 MASTER score 진입
6. Buy & Hold benchmark

### 출력
CAGR, 총수익률, MDD, Sharpe, Sortino, 승률, Profit Factor, 평균 이익/손실, 기대값, 거래횟수, 최대 연속손실, 연도별 수익률, 월별 수익률, Equity Curve, Drawdown Curve.

### 검증
- In-sample / out-of-sample 분리
- Walk-forward test
- 여러 기간(강세/약세/횡보) 비교
- 거래비용 민감도
- ATR stop 민감도
- 20/55일 돌파 파라미터 민감도
- survivorship bias를 줄이기 위해 당시 존재했던 종목 유니버스를 사용
- 데이터 누수 테스트 자동화

### 전략 비교 화면
각 전략을 동일한 초기자금/수수료/슬리피지 조건에서 비교하고 CAGR보다 MDD, Profit Factor, 안정성도 함께 평가하라.

실제 주문 연결은 별도 승인 없이는 수행하지 말라.
