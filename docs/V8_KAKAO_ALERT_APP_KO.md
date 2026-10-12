# V8 매수·매도 카카오 알림 웹앱

웹앱: https://v8-kakao-alert.wonderer1004.chatgpt.site

본인의 ChatGPT 계정으로 로그인하여 사용합니다. 신호·종목 지표·목표 비중·참고 투자금·알림 기록을 확인할 수 있습니다. 실계좌 주문은 연결되어 있지 않습니다.

## 처음 한 번 연결
1. 웹앱의 카카오 연결·설정을 여세요.
2. https://developers.kakao.com/console/app 에서 본인 앱을 만들고 카카오 로그인·talk_message 동의항목을 설정하세요.
3. REST API 키 설정의 Redirect URI에 https://v8-kakao-alert.wonderer1004.chatgpt.site/api/kakao/callback 을 등록하세요.
4. 제품 링크 관리의 웹 도메인에 https://v8-kakao-alert.wonderer1004.chatgpt.site 를 등록하세요.
5. 앱의 REST API 키와 활성화된 클라이언트 시크릿을 웹앱 설정에 입력하고 저장하세요. 이 문서·대화·GitHub에는 키를 올리지 마세요.
6. 카카오 계정 연결을 누르고 메시지 전송에 동의하세요.
7. 테스트 메시지 보내기를 눌러 본인 카카오톡 나와의 채팅에서 수신을 확인하세요.

## 동작
GitHub에서 평일 17:25 이후 V8 조정 일봉 신호를 계산합니다. 웹앱 자동 확인은 평일 한국시간17:45·18:45로 예약 설정되어 있습니다. 새 매수·매도 신호만 발송하며, 같은 신호는 중복 발송하지 않습니다. 신호 없는 날 요약은 설정에서 선택합니다.

종가에서 판단한 다음 거래일 참고 신호이며 실시간 호가·장중 알림이 아닙니다. 입력 투자금은 목표 금액 계산용이고 실제 계좌 잔고가 아닙니다. 매도 수량은 실제 보유 수량을 확인해야 합니다.

현재 연결이 필요한 부분은 본인의 카카오 앱 키와 동의입니다. 서버 갱신·저장·예약은 구성했지만 실제 카카오 계정 인증과 메시지 수신은 본인 연결 후 테스트해야 합니다. 휴대폰 브라우저 화면 검증은 미완료입니다.

공식 문서: https://developers.kakao.com/docs/ko/kakaotalk-message/rest-api 및 https://developers.kakao.com/docs/ko/kakaologin/rest-api
