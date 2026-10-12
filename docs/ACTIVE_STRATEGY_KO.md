# 현재 자동 모의매매 전략

현재 예약 실행은 Trend Fast V7 risk return comparison입니다. 이전 V2~V6는 예약 실행을 중단했고 수동 재검사는 유지합니다.

자동 선택 후보: MIX45(개발 구간 위험 대비 성과 기준). 별도 연구 후보: FAST100(재사용 검사 구간에서 V5보다 수익과 낙폭이 동시에 개선).

평일 한국시간 17:25 조건검색·비교·가상잔고 갱신. 실제 계좌 주문은 연결되어 있지 않습니다.

2024~2026.09 MIX45 수익303.97%·MDD-25.74%, 시장ETF보유220.01%·MDD-40.79%. V5는343.91%·MDD-49.47%이므로 MIX45는 V5대비 낙폭을 줄이는 대신 수익도 줄어든 절충입니다.

FAST100은489.67%·MDD-40.08%지만 이 결과로 자동 선택을 변경하지 않습니다. 이미 확인한 자료를 반복 사용했고 레버리지를 포함하여 미래 성과를 보장하지 않습니다.

자세한 조건·매매 규칙: [TREND_FAST_V7_KO.md](TREND_FAST_V7_KO.md)

결과: [comparison.csv](../reports/trend_fast_v7/comparison.csv)

최신 가상 상태: [paper_state.json](../reports/trend_fast_v7_latest/paper_state.json)
