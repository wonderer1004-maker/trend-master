# V8 포트폴리오 웹앱

실행: https://v8-kakao-alert.wonderer1004.chatgpt.site/portfolio/index.html

- 보유 현금, 수량, 평균단가 입력 → 보유 내역 저장
- 총 평가자산, 보유 평가손익, 현재 비중, V8 다음 거래일 목표 비중과 수량 차이 표시
- 실제 체결 후 매수·매도 기록 추가 (주문 전송 없음)
- 브라우저 localStorage 저장, JSON 백업/복원. 브라우저가 다르면 별도 보유 기록입니다.
- 기존 카카오 알림 설정 웹앱 링크 제공. 카카오 앱 키와 사용자 동의 설정이 필요합니다.

## 시세와 신호

V8 신호는 GitHub 장마감 산출 JSON입니다. 전략을 장중 전략으로 변경하지 않았습니다.
호스팅 웹앱에서는 서버의 `/api/quotes`로 네이버 공개 참고 시세를 70초마다 확인합니다. 거래소 직접 실시간 시세가 아니며 지연·누락 가능성이 있습니다. 장 종료 상태와 조회 시각을 표시합니다.
GitHub Pages 단독 실행 또는 서버 실패 시 Yahoo 조정 일봉 종가로 대체하며 화면에 이를 명시합니다. 가격 조회시각은 거래소 체결시각과 다릅니다.
보유 원가 대비 평가손익을 표시하며 누적 계좌 수익률, 실현손익 합계, 증권사 잔고는 아닙니다. 수수료·세금을 매매 기록에서 입력할 수 있습니다. 다음 시가·수수료 차이로 목표 수량은 실제 주문 수량과 다를 수 있습니다.

## GitHub Pages

기존 `Domestic ETF Yahoo alerts` 워크플로가 docs 폴더를 배포합니다.
저장소 Settings → Pages → Build and deployment → Source를 GitHub Actions로 선택 후 해당 워크플로를 실행하세요.
Pages 활성화 후 주소: https://wonderer1004-maker.github.io/trend-master/portfolio/
GitHub Pages 버전은 장마감 종가 기반이며 서버 참고 시세는 위 호스팅 앱에서 제공됩니다.

## 검증

`node docs/portfolio/core.test.mjs` — 평가손익, 가중 평균단가, 현금 부족, 초과 매도, 유지/청산 구분 검증.
브라우저 화면 및 증권계좌 연동 검증은 수행하지 않았습니다.
