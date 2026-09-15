# TREND MASTER — 국내·미국 통합 추세추종 스캐너

## 웹앱으로 배포하기 (Render)

이 저장소에는 `render.yaml`이 포함돼 있어 Render에서 바로 웹 서비스로 띄울 수 있습니다.

1. 이 폴더 전체를 새 GitHub 저장소(퍼블릭)에 업로드합니다.
2. Render 대시보드 → **New > Blueprint** → 방금 만든 저장소 선택 → `render.yaml`을 자동으로 인식합니다.
3. 배포가 끝나면 `https://trend-master-〈랜덤문자〉.onrender.com` 같은 URL이 생성되고, Streamlit 대시보드(스캔 + 백테스트)가 그대로 웹에서 동작합니다.

무료 플랜은 15분간 요청이 없으면 슬립 상태로 들어가고, 다음 접속 시 30~50초 정도 깨어나는 시간이 걸립니다.

## 이번 수정 사항 (코드 리뷰 반영)

- **스코어링 100점 만점 복구**: `scoring.py`에 빠져 있던 "시장 환경 20점" 항목을 추가했습니다 (벤치마크 지수의 150일선 상회/상승 여부). 이전에는 4개 항목(80점)만 구현돼 있어 `STRONG_BUY_CANDIDATE`(90점 이상)가 구조적으로 나올 수 없었습니다.
- **시장 국면 게이팅 추가**: 벤치마크로 BULL/NEUTRAL/BEAR를 판정하고, BEAR에서는 신규 매수 신호(READY 이상)를 전부 WATCH로 강등, NEUTRAL에서는 STRONG_BUY를 BUY_CANDIDATE로 한 단계 낮춥니다. (`market_regime` 필드로 결과에 노출)
- **한국 종목 데이터 소스 교체**: `.KS`(코스피 전용) 접미사 추정 방식을 버리고 `pykrx`로 직접 조회하도록 변경했습니다. 코스닥 종목도 별도 처리 없이 6자리 코드 그대로 조회됩니다.

목표:
- Jesse Livermore: 강한 종목이 더 강해지는 구간
- Stan Weinstein: Stage 2
- Turtle: 20/55일 돌파
- William O'Neil: 성장·상대강도·돌파
- Mark Minervini: 추세 정렬·고점 근접·압축 후 돌파
- Darvas: 박스권 돌파
- ATR: 포지션 사이징/리스크 관리

주의:
- 이 프로젝트는 투자 교육/리서치용 스캐너입니다.
- 기본값은 주문을 실행하지 않습니다.
- 실제 주문 연동 전에는 데이터 오류, 거래정지, 액면분할/배당 조정, 환율, 세금, 슬리피지, 수수료를 별도로 검증하세요.

## 설치

Python 3.11+ 권장

```bash
pip install -r requirements.txt
```

## 실행

미국:
```bash
python -m app.cli --market US --symbols AAPL MSFT NVDA AMZN
```

한국:
```bash
python -m app.cli --market KR --symbols 005930 000660 373220
```

CSV:
```bash
python -m app.cli --market US --symbols AAPL MSFT NVDA --csv results.csv
```

전체 유니버스는 별도 데이터 공급자를 연결하는 방식으로 확장합니다.

## 점수 구조

100점:
- 시장 환경 20
- Weinstein 20
- Livermore/Turtle 20
- O'Neil/Minervini 20
- 거래량/상대강도/업종 20

신호:
- 90+: STRONG_BUY_CANDIDATE
- 80~89: BUY_CANDIDATE
- 70~79: READY
- 60~69: WATCH
- <60: AVOID

실전에서는 '점수'만 보고 매수하지 말고 시장/업종/돌파/손절 조건을 동시에 확인합니다.

## 백테스트

기본 백테스트는 **신호는 당일 종가까지 계산하고 실제 진입은 다음 거래일 시가**에 하는 구조입니다. 거래비용과 슬리피지를 입력할 수 있고, ATR 손절과 50일선 이탈 청산을 사용합니다.

예:
```bash
python -m app.backtest_cli --market US --symbol NVDA --cash 10000000 --breakout 55 --risk 0.01
python -m app.backtest_cli --market KR --symbol 005930 --cash 10000000 --breakout 20 --risk 0.01
```

대시보드에서도 Scan + Backtest 버튼으로 종목별 CAGR/MDD/승률/Profit Factor/거래횟수/Equity Curve/거래내역을 확인할 수 있습니다.

### 중요한 검증 규칙
- 미래 데이터 참조 금지
- 신호일 종가 체결 금지: 기본은 다음 날 시가
- 수수료/슬리피지 반영
- ATR 손절은 보수적으로 처리
- 백테스트 성과를 실전 기대수익으로 간주하지 않음
- 향후 버전에서는 상장폐지 종목을 포함한 survivorship-bias-free universe와 walk-forward/기간 분할 검증을 추가 권장
