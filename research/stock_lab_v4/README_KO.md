# 개별주식 단타·스윙 연구 v4

목적: 고정 후보를 비용·납입·다른 시기에서 비교하고, 검증 미달 전략의 실거래 진입을 막는다. 수익 보장 상품이나 증권사 주문 연결 프로그램이 아니다.

결과는 `reports/stock_lab_v4/RESULT_KO.md`, 진입 제한은 `execution_gate.json`을 확인한다. GitHub Actions 실행에서 테스트 결과와 `stock-lab-v4-reproducible` 아티팩트를 열면 모든 자산곡선·매수/매도·거래별 손익을 확인할 수 있다. 다운로드한 `comparison.csv`는 엑셀로 열 수 있다.

```bash
pip install pandas==2.2.3 numpy==2.3.5 matplotlib==3.10.8
python -m unittest discover -s research/stock_lab_v4 -p 'test_*.py' -v
python research/stock_lab_v4/run.py
python research/stock_lab_v4/paper.py --market us --capital 100000
python research/stock_lab_v4/paper.py --market kr --capital 100000000
python research/stock_lab_v4/report.py
python research/stock_lab_v4/plot.py
```

보관된 스냅샷으로 오프라인 재현한다. `download.py`는 원자료 수집 기록을 위한 별도 명령이다. 일봉 종료일은 2026-10-16로 고정되어 있고 분봉은 실행 시점의 최근 60세션이므로, 시간이 지난 뒤 다시 받으면 동일 표본이 아니다. 입력을 덮어쓴 뒤 이전 결과와 혼용하면 안 된다. CI는 다운로드를 실행하지 않는다.

5종 스윙: 20/55일 돌파, RSI2 과매도, 상승추세 눌림목, 60일 모멘텀의 20세션 간격 진입. 2종 단타: 5/15분 범위 돌파. 시장·비용·기간·납입을 합쳐 232개 결과. 정기매수는 최초금의 1%를 매월 추가한다. 규칙·비용·표본 제약은 결과 보고서에 모두 적었다.

`paper.py`는 마지막 완료 일봉에서 **연구용 관심종목**만 만든다. 입력은 오래된 고정 스냅샷이고 가격도 조정가격이므로 현재 매수 추천이나 전송 가능한 주문이 아니다. 실제 브로커 연결·실시간 시세·자동 주문은 구현/활성화되지 않았다. `live_enabled`는 항상 false이며 실거래를 켜는 설정은 없다. 검증 실패를 숨기고 거래를 강제하지 않는다.
