# TREND MASTER 모바일 단타 연구 V1

접속: https://trend-master-kr-mobile.wonderer1004.chatgpt.site

모바일에서 5분봉 백테스트와 과거 매매 리플레이를 실행하는 PWA입니다.
실제 키움 계좌·실시간 시세·증권사 주문은 연결되어 있지 않습니다.

## 기능
- 브라우저 안에서 종목 5분봉·시장지표 5분봉·종목 일봉 CSV를 읽고 계산
- 투자금·위험비율·종목비중·수수료·매도세 가정·슬리피지 설정
- 자산 곡선, 거래 내역, 수익률·MDD·PF·평균 R
- 과거 매매 기록 재생과 결과 JSON 다운로드
- 홈 화면 추가용 manifest와 service worker

예제는 상승 편향을 넣은 합성 데이터입니다. 예제 결과는 실제 투자 성과가 아닙니다.
실제 CSV의 정확성, 제외종목, 상장폐지와 조정가격은 사용자가 확인해야 합니다.
기본 비용은 검증용 가정이며 현재 법정 세율을 의미하지 않습니다.

## 로컬 웹 실행
저장소를 내려받고 저장소 루트에서:

```bash
python -m http.server 8000 --directory mobile/dist
```

브라우저에서 http://localhost:8000 에 접속합니다.
파일을 직접 여는 file:// 방식은 모듈·Worker 때문에 지원하지 않습니다.
같은 Wi-Fi의 휴대폰에서 PC의 LAN IP와 8000 포트로 접속할 수도 있습니다.
PWA 설치·오프라인 기능은 HTTPS 또는 localhost와 브라우저 지원이 필요합니다.

## 검증
Node.js 18 이상에서:

```bash
cd mobile
node verify.mjs
```

Python V1과 합성 예제의 7개 핵심 지표가 오차 1e-7 미만으로 일치합니다.
누락 세션 거절, OHLC 검증, 비용 민감도와 미래 데이터의 이전 결과 불변성을 검증합니다.
브라우저 시각 QA와 WebMCP 지원 환경에서의 검증은 미실행입니다.

## Python 엔진

```bash
cd mobile/python
python -m pip install -r requirements.txt
python -m unittest -v
python demo.py
```

실제 데이터 실행법과 키움 읽기 전용 수집 어댑터는 python/README.md를 참고하세요.
키움 어댑터는 실제 인증·조회 테스트가 미실행이며 주문을 보내지 않습니다.
API 키는 환경변수에만 보관하고 저장소에 업로드하지 마세요.

## 구조
- dist/: 배포 가능한 정적 웹앱과 합성 예제
- verify.mjs: 브라우저 계산 엔진 검증
- verification_expected.json: Python 합성 예제 기준 결과
- python/: 독립 실행 가능한 Python 연구·리플레이 엔진

기존 저장소의 app/ 스캐너와 독립적으로 실행됩니다.
별도 서버 없이 계산하지만 휴대폰을 닫으면 리플레이는 중단됩니다.
상시 자동매매에는 데이터·계좌·주문·체결을 처리하는 별도 서버가 필요합니다.

## 코스피 감시와 Yahoo Finance 검증

‘종목 감시’ 화면에서 입력 데이터의 조건별 후보, 진입 상한, 초기 손절과 단일 포지션 수량을 계산합니다. 실시간 전 종목 연결은 아닙니다. 실제 데이터에는 거래일별 적격성 확인을 반영한 마스터 CSV가 필요합니다.

Yahoo Finance 백테스트 스크립트는 KRX KIND의 현재 기업 목록을 받아 리츠·스팩 이름을 제외하고 일봉을 수집합니다. 평가기간 중 어느 날이든 전일 필터를 통과한 후보의 최근 1개월 5분봉을 수집하여 검증합니다.

```bash
cd mobile/python
python -m pip install -r requirements.txt
python yahoo_kospi_backtest.py
```

Yahoo 분봉에서 15:15 봉이 누락되어, 이 스크립트는 **14:55 청산 변형 전략**만 실행합니다. 원본 15:15 전략의 검증으로 해석하면 안 됩니다. 현재 기업 목록의 생존편향, 데이터 누락, ETF 시장지표 대용, 고정 비용 가정을 포함합니다. 결과와 수집 실패 기록은 yahoo_kospi/에 저장합니다. 실패·미지원 종목은 제외되며 전체 상장 증권·역사적 유니버스를 완전히 검증했다고 볼 수 없습니다.
