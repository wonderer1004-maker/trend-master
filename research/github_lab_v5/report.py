"""Readable report from executed results; no hard-coded performance claims."""
import json
from pathlib import Path
import pandas as pd
from run import OUT
from models import RULES

def md(d,columns):
    out=['| '+' | '.join(columns)+' |','|'+'|'.join(['---']*len(columns))+'|']
    pct={'cagr','xirr','mdd','avg_exposure','total_return'}
    for _,r in d.iterrows():
      vals=[f'{r[c]*100:.2f}%' if c in pct else str(r[c]) for c in columns]
      out.append('| '+' | '.join(vals)+' |')
    return '\n'.join(out)

def main():
    d=pd.read_csv(OUT/'comparison.csv');s=json.loads((OUT/'summary.json').read_text());selected=s['selected'];decisions=json.loads((OUT/'decisions.json').read_text())
    text=['# GitHub 공개 엔진을 사용한 기존·신규·보완 전략 비교 v5',f'\n**실행 완료: Backtrader {s["backtrader_runs"]}회 + 별도 원장 {s["independent_ledger_runs"]}회 대조, 기간별 결과 {s["summary_rows"]}개. 최대 자산금액 상대 오차 {s["max_engine_relative_error"]:.3g}.**',f'\n개발구간 선택 모델: {selected}. 연구 게이트 통과 시장: {s["research_gate_passers"] or "없음"}. 실제 증권사 주문은 연결/활성화하지 않았다.','\n![자산곡선](curves.png)','\n## 무엇을 실제로 사용했나','\nGitHub 공개 프로그램 **mementum/backtrader 1.9.78.123**을 설치해 다종목 주문·수수료·현금을 계산했다. 별도의 NumPy 원장으로 같은 가격과 주문 규칙을 재실행하여 매일 자산 금액을 대조했다. 이는 체결·회계 구현의 일치 확인이며 전략의 미래 수익 보증은 아니다. 다른 도구의 데모 수익률을 가져오거나 공개 엔진이 수익을 보장한다고 해석하지 않는다.','\n기존 저장소 `scripts/trend_refined_v8.py`의 `enrich`, `regime`, `target`을 직접 호출해 HYST45 목표 비중을 재사용했다. 기존 V8 전체 시뮬레이터의 쿨다운·손절·거래 반올림은 이식하지 않았으므로 **V8_HYST45_PORT는 목표 비중만 재사용한 변형**이다. 이전 20일 돌파·모멘텀 스윙도 종가 확인·다음 시가 체결 변형이며 이전 장중 손절 결과와 동일하지 않다.','\n## 개발 선택과 평가 방식','\n2018–2021 개발, 2022–2023 재사용 검증, 2024–2026-10-16 재사용 최종평가. 각 후보를 일시금/월납입 × 비용 1/2배에서 실행하고, 개발구간의 `CAGR / max(|MDD|,2%)` 중 최악값이 가장 높은 후보를 선택했다. 보유·2배보유·고정1.25배는 비교군이어서 선택에서 제외했다. 기간을 나눴지만 이미 여러 번 연구한 역사 자료여서 독립적인 미사용 검증은 아니다.','\n운용은 2018년부터 연속된다. 검증/최종평가 표는 당시 보유 포지션·자산을 이어받은 부분기간 수익이다. 매 구간을 동일 자금의 현금에서 새로 시작한 실험과 다르다. 월납입은 미국 최초10만달러+월1천달러, 국내 최초1억원+월100만원이다. 월 첫 공통 관측일 시가에 입금한다. 원화/달러 환산은 하지 않았다.','\n## 최종평가: 개발 선택 모델과 비교군 (기본 비용)','\nCAGR는 현금 입금 영향을 제거한 시가 단위기준가의 연복리, XIRR는 납입 시점을 반영한 금액가중 연수익률, MDD는 단위기준가 최대낙폭이다. 레버리지는 실제 2배 ETF 가격을 썼다. 일반 ETF보다 더 큰 위험 노출이므로 수익 증가가 곧 초과수익 창출 능력을 뜻하지 않는다.']
    keep=d.apply(lambda r:r.strategy in ['HOLD','LEV2_HOLD','STATIC125',selected[r.case]],axis=1)
    z=d[(d.stage=='primary')&(d.window=='test_reused')&(d.cost==1)&keep]
    text.append('\n'+md(z,['case','strategy','funding','cagr','xirr','mdd','avg_exposure']))
    follow=json.loads((OUT/'posthoc_followup.json').read_text()) if (OUT/'posthoc_followup.json').exists() else []
    text+=['\n## 사후 탐색 후 추가 확인한 후보 — 개발 선택 모델과 구분','\n재사용 검증/최종평가 × 비용1/2배 × 일시금/월납입의 8조건 전부에서 지수보다 수익률과 낙폭이 함께 개선되고 수익률이 양수인 후보를 전체 후보에서 기계적으로 찾았다. 그런 다음 1거래일 추가 지연을 확인했다. **평가 결과를 본 뒤 골랐으므로 독립 미사용 검증이나 개발 선택 성공으로 간주하지 않는다.**']
    for f in follow:
      text.append(f'\n- {f["case"]} / {f["strategy"]}: 기본 8/8 통과, 추가 지연 8조건 모두 통과={f["delay_all_pass"]}, 3개월 블록 재표본의 초과수익 95%구간={f["bootstrap"]["excess_cagr_ci95"]}, 사후 연구 게이트={f["exploratory_gate"]}.')
    mask=d.apply(lambda r:any(r.case==f['case'] and r.strategy==f['strategy'] for f in follow),axis=1)
    z=d[mask&(d.window=='test_reused')&(d.stage.isin(['primary','posthoc_delay']))]
    text.append('\n'+md(z,['case','strategy','stage','cost','funding','cagr','xirr','mdd']))
    text+=['\n## 보완 전후 비교: 사후 최고 수익만 골라 표시하지 않음','\n아래는 미리 정한 대응 후보 전부다. 현금 비중을 줄인 보완안은 투자 노출과 위험이 같이 커질 수 있다. 다른 진입·청산 규칙이 포함되어 특정 수정 한 가지의 효과를 분리한 실험은 아니다.']
    paired=['OLD_MOM60_PORT','IMPROVED_MOM_CORE','OLD_BREAK20_CLOSE_PORT','IMPROVED_BREAK55_CORE','OLD_VOL20','NEW_TREND_ENSEMBLE','NEW_CORE_ENSEMBLE','NEW_MOM12_1','V8_HYST45_PORT']
    z=d[(d.stage=='primary')&(d.window=='test_reused')&(d.cost==1)&(d.funding=='lump')&d.strategy.isin(paired)]
    text.append('\n'+md(z,['case','strategy','cagr','mdd','avg_exposure']))
    text+=['\n## 선택 후보의 비용·체결 지연 스트레스','\n기본은 완료 종가 신호의 다음 공통 관측 시가, 지연 스트레스는 그 다음 시가다. 비용2는 기본 편도 비용의 두 배다. 적립식 비교에서는 CAGR 대신 XIRR도 함께 확인해야 한다.']
    keep=d.apply(lambda r:r.strategy in ['HOLD',selected[r.case]],axis=1)
    z=d[(d.window.isin(['validation_reused','test_reused']))&(d.stage.isin(['primary','delay_stress']))&keep]
    text.append('\n'+md(z,['case','strategy','window','stage','cost','funding','cagr','xirr','mdd']))
    text+=['\n## 국내 대체 자료 민감도','\n주 결과는 Naver fchart 가격 자료로 현금 배당/분배금이 포함되지 않은 가격 수익률이다. 대조 자료는 기존 Yahoo 조정가격의 배당 포함 수익률 근사다. **공급원과 수익률 기준이 함께 달라지므로 순수한 공급원 효과로 해석하면 안 된다.** 국내 총수익 우월성은 이 실험만으로 확정할 수 없다.']
    z=d[(d.stage=='source_control')&(d.window=='test_reused')&(d.cost==1)]
    text.append('\n'+md(z,['case','strategy','funding','cagr','xirr','mdd']))
    text+=['\n## 불확실성과 진입 제한','\n선택 후보가 재사용 검증/최종평가 × 두 비용 × 두 납입 × 두 체결시점 모두에서 양수, 지수보유보다 높은 CAGR(월납입은XIRR), 낮거나 같은 MDD를 충족하고 아래 블록 재표본의 95% 구간 하단도 양수여야 연구 게이트를 통과한다. 이는 원지수 HOLD 대비 조건이며 고정 레버리지 또는 전 시장 우월성을 의미하지 않는다. 통과하더라도 독립 미래 모의운용이 남는다. 국내 대체자료 표는 추가 민감도이며 이 게이트에는 포함하지 않았다.']
    for x in decisions:
      lo,hi=x['bootstrap']['excess_cagr_ci95'];text.append(f'\n- {x["case"]}: {x["selected"]}, 게이트 {x["research_gate"]}, 최종평가 월별 수익의 3개월 블록 2,000회 재표본 기준 초과 연복리 차이 구간 [{lo*100:.2f}%, {hi*100:.2f}%].')
    text+=['\n이 재표본 구간은 선택된 모델과 고정 종목 표본을 조건으로 한 추정이다. 반복 연구·다중 탐색·생존편향을 완전히 보정하지 못했다. 어떤 결과도 수익 보장이 아니다.','\n## 전략 규칙']
    for k,v in RULES.items():text.append(f'\n- **{k}**: {v}')
    text+=['\nOLD_MOM60_PORT는 양의 60일 수익률·200일선 위 종목 상위5개를 20개 관측 세션마다 고르고, 목표 비중은 min(20%,0.25%/(2ATR/종가))다. OLD_BREAK20_CLOSE_PORT는 같은 위험 배분과 20일 돌파를 쓴다. IMPROVED_BREAK55_CORE는 55일 돌파, 목표 비중 min(20%,0.75%/(3ATR/종가)), 종목 합계50% 상한, 나머지 원지수 배분이다. 공통 돌파 보유는 최대20개 관측 세션, 종가가 추적선/이전20일저가/200일선 아래면 다음 시가 청산한다. 장중 지정 손절은 없다.','\nIMPROVED_MOM_CORE는 매월 관측 시작 시점에서 직전 종가 정보로 60/126/252 관측일 모멘텀(최근21 관측일 제외) 순위 평균을 사용한다. 200일선 위·양의12-1 및60일 모멘텀 종목 최대5개에 각10%, 나머지 원지수다. 월 리밸런싱 기준 하락장에서는 원지수50%와 현금50%다. NEW_MOM12_1은 시장200일선 필터를 적용하고 최대5개 각20%, 미충족 슬롯은 현금이다.','\n추세 앙상블의 노출은 min(0.5+3개 이동평균 추세투표 평균,22%/20일 변동성)이다. 1초과 노출은 원지수(2-e)와 실제2배ETF(e-1), 1이하는 원지수e와 미국SHY 또는 국내현금으로 구현한다. 최대 명목노출1.5배, 직접 차입/공매도는 없다.','\n매월 첫 공통 관측일과 목표비중 변경일에 재조정한다. HOLD/LEV2_HOLD는 처음 진입과 새 납입금 매수만 하므로 불필요한 월 재매매를 하지 않는다. 매도 먼저, 매수는 남은 현금 내림차순 목표비중/종목코드 순서다. 매수는 직전 관측봉 거래대금의0.5% 한도다. 매도 거래량 제한은 구현하지 않았다.','\n## 비용·체결·자료의 중요한 한계','\n미국ETF 편도0.07%, 미국종목0.10%, 국내ETF0.15%, 국내종목 매수0.15%/매도0.35%를 수수료·스프레드·슬리피지·매도측 비용의 합산 가정으로 차감한다. stress=2는 각각 두 배다. 실제 세율/증권사 수수료 확정값이 아니다. 슬리피지는 시가를 바꾸지 않고 동액 비용으로 차감했다. 실제 주문장·시장충격·거래정지/VI·상하한가 미체결·개인 양도세·환전·현금 이자는 재현하지 않았다.','\nBacktrader cheat_on_open은 **기존 종가로 확정된 비중**을 다음 시가에 수량으로 바꾸는 데만 쓴다. 당일 고가/저가/종가로 신규 비중을 정하지 않는다. 다만 실제 시가를 확인한 뒤 같은 시가에 체결하는 것은 보장되지 않는다. 현재 비용과 1거래일 추가 지연 시험이 그 차이를 완전히 설명하지 못할 수 있다. 조정가격 소수 단위는 실제 주문가능 정수 주수/호가와 다르다.','\n미국은 Yahoo adjclose/close 비율을 OHLC에 적용한 기존 스냅샷, 국내 주 결과는 Naver 가격 스냅샷, 국내 대조는 Yahoo 스냅샷이다. 데이터 범위/해시는 input/manifest.json에 보관했다. 자료를 보간하지 않고 잘못된 OHLC·0거래량 봉을 삭제한 뒤 시장별 전체 종목 공통 달력만 사용했다. 따라서 어떤 한 종목의 누락/정지 때문에 시장 전체의 정상 거래일도 빠질 수 있고, 누락일의 낙폭/매매 기회를 놓친다. 이동평균·모멘텀의 일수는 이 공통 관측일 기준이다. 삭제일은 data_audit.json에 있다.','\n개별주식 표본은 미국20개·국내10개의 현재 생존 대형주다. 상장폐지/과거 편입종목/전체 종목 유동성 순위를 복원하지 못했고 미국 기술주 비중도 높다. 원지수 초과성과가 나와도 전 시장 종목선정 능력이 입증되는 것은 아니다. 마지막 평가일은 보유가격 평가이며 강제 청산 비용은 추가하지 않았다. 장중 손절이 없으므로 예정 위험을 넘는 손실도 가능하다.','\n## 재현과 자료','\n`research/github_lab_v5/README_KO.md`의 한 번 실행 명령 또는 GitHub Actions 실행을 사용한다. `comparison.csv`는 표 전체, `details/`는 일별 자산/현금/단위기준가와 체결내역이다. 코드는 고정 스냅샷에서 동작하며 브로커 키/주문 전송 기능이 없다.','\n## 공개 근거','\n- Backtrader 원본: https://github.com/mementum/backtrader (GPL-3.0, 실행 버전1.9.78.123)','- 시가 처리 공식 문서: https://www.backtrader.com/docu/cerebro/cheat-on-open/cheat-on-open/','- 거래비용 공식 문서: https://www.backtrader.com/docu/commission-schemes/commission-schemes/','- 모멘텀 구성 원문: https://www.aqr.com/insights/datasets/momentum-indices-monthly (12개월 중 최근1개월 제외 아이디어; AQR 자체 지수 복제가 아님)','\n이전 지수 장기/위기 연구(PR#3) 및 개별주식 장중손절/분봉 연구(PR#4)와 입력·현금흐름·체결규칙이 다르다. 보고서 간 수익률을 하나의 동일 전략 실적으로 합치면 안 된다. 이번 v5는 일봉 전략 비교에 집중하며 분봉 단타의 장기간 우월성은 추가 입증하지 않았다.']
    (OUT/'RESULT_KO.md').write_text('\n'.join(text),encoding='utf-8');print(json.dumps(s,ensure_ascii=False))
if __name__=='__main__':main()
