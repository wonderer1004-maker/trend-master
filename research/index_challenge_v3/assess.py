"""Report fixed-risk baselines alongside active hypotheses, without hiding failures."""
import json
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parent;OUT=ROOT.parents[1]/'reports'/'index_challenge_v3'

def main():
    t=pd.read_csv(OUT/'comparison.csv');selection=json.loads((OUT/'selection.json').read_text())
    results={};full=[]
    for index in t['index'].unique():
        q=t[(t['index']==index)&(t.model=='STATIC125')&t.period.isin(['full','validation','later'])]
        results[index]=dict(cases=len(q),beats_return_all=bool(q.beats_return.all()),improves_both_all=bool(q.improves_both.all()),
          worst_wealth_ratio=float(q.wealth_ratio.min()),worst_mdd_pct=float(q.twr_mdd_pct.min()))
        q=t[(t['index']==index)&t.model.isin(['INDEX_HOLD','STATIC125','HYST150_HALF','CORE_BOOST125'])&(t.period=='full')&(t.cost==1)&(t.delay==1)]
        full+=q.to_dict('records')
    assessment=dict(total_runs=4288,static125=results,full_base=full,
      critical='75/25 higher exposure is a fixed risky baseline, not proof of market timing alpha; not validated for personal taxes or future returns',
      common_selected_on_development=selection['common']['selected_on_development'],
      common_development_worst_excess_irr_pp=selection['common']['development_worst_excess_irr_pp'])
    (OUT/'assessment.json').write_text(json.dumps(assessment,indent=2),encoding='utf-8')
    lines=['# 최종 결과: 지수 보유·정기매수 비교','',
      '**수익률 기준으로 통과한 75·25 구성은 추가 위험 노출을 포함합니다.** 일반 지수ETF75%와 실제2배ETF25%를 월초에 맞추는 고정 위험 기준선입니다.',
      '1차 실험은 15개 능동 규칙과 4개 기준선으로3648회, 2차 지수교체 실험은640회, 총4288회입니다.',
      '단순 지수 보유도 적립식 조건에서는 같은 월초에 같은 금액을 입금해 지수ETF를 추가 매수합니다.',
      '개발기간만으로 선택한 공통 능동 규칙은 UNLEV_CORE75였고 개발기간 최악 초과 XIRR도 음수였습니다. 독립 검증된 공통 초과수익 알고리즘을 얻었다고 주장할 수 없습니다.',
      '', '## 사전 포함한 75·25 고정 구성의 수익 검증','',
      '|지수|전체·검증·후속/납입·비용·지연 조합|모두 수익 우세|모두 낙폭도 개선|최악 최종금액 비율|','|---|---:|---|---|---:|']
    for index,r in results.items():lines.append(f"|{index}|{r['cases']}|{r['beats_return_all']}|{r['improves_both_all']}|{r['worst_wealth_ratio']:.4f}|")
    lines+=['', '지수별24조건은3구간×2납입방식×2비용×2체결지연입니다. 관측 기간이 겹치므로 독립 표본24개라는 뜻은 아닙니다.',
      '코스닥150은 통과하지 못했습니다. 수익 우세와 위험 개선을 구분합니다.', '',
      '## 전체기간 기본 비용·다음 시가 체결','',
      '코스피200·미국은2012년부터, 코스닥150은2017년부터2026-10-16까지입니다. 미국은 달러 기준입니다.',
      '일시금: 국내1천만원/미국1만달러. 적립식: 별도 초기금 없이 매월 국내100만원/미국1000달러입니다.',
      '|지수|방법|일시금 연복리|적립식 XIRR|일시금 최대낙폭|적립 최종금액|','|---|---|---:|---:|---:|---:|']
    for r in full:
        if r['model'] not in ['INDEX_HOLD','STATIC125']:continue
        if r['funding']!='LUMP':continue
        d=next(x for x in full if x['index']==r['index'] and x['model']==r['model'] and x['funding']=='DCA')
        lines.append(f"|{r['index']}|{r['model']}|{r['twr_cagr_pct']:.2f}%|{d['money_irr_pct']:.2f}%|{r['twr_mdd_pct']:.2f}%|{d['final_value']:,.0f} {d['currency']}|")
    lines+=['', '## 확인한 능동 후보','',
      '나스닥100 HYST150_HALF·CORE_BOOST125·MA200_200은 전체·검증·후속의 두 납입 방식/비용/지연 조건에서 지수 수익을 모두 넘었습니다. 낙폭 개선은 통과하지 못했습니다.',
      'HYST150_HALF: 나스닥100 ETF 종가가200일평균의1.01배 위에서3회 연속 마감하면 QQQ50%+QLD50%, 0.99배 아래에서3회면 QQQ50%+SHY50%를 목표로 합니다. 중간에서는 직전 상태를 유지합니다. 월초와 상태 변경 후 실행합니다.',
      'HYST 후보는 전체 결과를 본 뒤 주목한 탐색 후보이며 개발기간의 선택 규칙은 별도 파일에 있습니다.',
      'SP500 변동성 조절은 전체기간에서 좋았지만 후속 구간의 일부 조건에서 졌습니다. 두 지수 교체는 각 지역의 강한 지수 보유까지 넘는 엄격한 기준을 통과하지 못했습니다.',
      '', '## 실무 한계','',
      '실제2배ETF 조정가격을 사용해 비용·조달·일일재설정 효과가 가격에 반영되어 있습니다. 계좌 차입은 사용하지 않았습니다.',
      '원금 유입과 수익을 구분한 TWR 낙폭과 날짜별 XIRR입니다. 개인 과세·환율·분봉 체결은 제외합니다.',
      'Yahoo의 국내 일부 거래일 누락, 조정가격 소수 단위 매매, 기간·규칙의 반복 검토, 중첩 구간의 편향이 남습니다.',
      '보다 높은 수익이 미래에도 유지되거나 실제 개인세금 후에도 유지된다고 확정할 수 없습니다.']
    (OUT/'DECISION_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('ASSESSMENT_JSON_BEGIN');print(json.dumps(assessment,separators=(',',':')));print('ASSESSMENT_JSON_END')
if __name__=='__main__':main()
