"""Additional available-history stress; no rule or allocation refitting."""
import json
import sys
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parent/'index_challenge_v3';sys.path.insert(0,str(ROOT))
from engine import SPECS,RULES,BASELINES,prepare,replay
from run import load,OUT


def main():
    OUT.mkdir(exist_ok=True,parents=True);raw=load();rows=[]
    for index in ['SP500','NASDAQ100']:
        d=prepare(raw,SPECS[index])
        for period,start,end in [('crisis2008_2011','2008-01-01','2011-12-31'),('extended2008','2008-01-01','2026-10-16')]:
            for model in RULES:
                for funding in ['LUMP','DCA']:
                    for cost in [1,2]:
                        for delay in [1,2]:
                            stat,_,_=replay(d,model,start,end,funding,cost,delay)
                            rows.append(dict(index=index,period=period,model=model,funding=funding,cost=cost,delay=delay,**stat))
            print('completed stress',index,period,flush=True)
    t=pd.DataFrame(rows);keys=['index','period','funding','cost','delay']
    b=t[t.model=='INDEX_HOLD'][keys+['final_value','twr_mdd_pct']].rename(columns={'final_value':'benchmark_final','twr_mdd_pct':'benchmark_mdd_pct'})
    t=t.merge(b,on=keys);t['wealth_ratio']=t.final_value/t.benchmark_final
    t['improves_both']=(t.wealth_ratio>1+1e-9)&(t.twr_mdd_pct>t.benchmark_mdd_pct+1e-8)
    t.to_csv(OUT/'crisis_comparison.csv',index=False)
    full=t[(t.cost==1)&(t.delay==1)&t.model.isin(['INDEX_HOLD','STATIC125','STATIC150','HYST150_HALF','CORE_BOOST125','VOL20_ALWAYS150'])]
    summary=dict(total_runs=len(t),scope='US actual ETFs 2008-2011 and 2008-2026; unchanged existing 19 rules',full_base=full.to_dict('records'))
    (OUT/'crisis_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    lines=['# 추가 위기 검증 — 미국 실제 ETF, 2008년 포함','',
      '2012년부터의 공통 비교 후, 실제 ETF 이력이 있는 미국에 2008년 금융위기를 추가했습니다. 규칙·비중은 다시 맞추지 않았습니다.',
      '기존4288회와 추가608회, 총4896회입니다. 같은 데이터의 기간을 확장한 스트레스이며 독립된 신규 표본이 아닙니다.',
      '국내 2배ETF는2008년에 상장되지 않아 가상의 2배 가격으로 금융위기를 만들어 넣지 않았습니다.',
      '', '|지수|구간|방법|일시금 연복리|적립식 XIRR|일시금 최대낙폭|적립 최종금액/지수적립|','|---|---|---|---:|---:|---:|---:|']
    for index in ['SP500','NASDAQ100']:
        for period in ['crisis2008_2011','extended2008']:
            for model in ['INDEX_HOLD','STATIC125','STATIC150','HYST150_HALF','CORE_BOOST125','VOL20_ALWAYS150']:
                q=full[(full['index']==index)&(full.period==period)&(full.model==model)]
                l=q[q.funding=='LUMP'].iloc[0];c=q[q.funding=='DCA'].iloc[0]
                lines.append(f'|{index}|{period}|{model}|{l.twr_cagr_pct:.2f}%|{c.money_irr_pct:.2f}%|{l.twr_mdd_pct:.2f}%|{c.wealth_ratio:.3f}|')
    (OUT/'CRISIS_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    original_path=OUT/'comparison.csv'
    original=pd.read_csv(original_path if original_path.exists() else OUT/'comparison.csv.gz')
    picked=[]
    for index,model in [('KOSPI200','STATIC125'),('SP500','VOL20_ALWAYS150'),('NASDAQ100','HYST150_HALF')]:
        source=original if index=='KOSPI200' else t
        period='full' if index=='KOSPI200' else 'extended2008'
        for m in ['INDEX_HOLD',model]:
            a=source[(source['index']==index)&(source.model==m)&(source.period==period)&(source.cost==1)&(source.delay==1)]
            l=a[a.funding=='LUMP'].iloc[0];c=a[a.funding=='DCA'].iloc[0]
            picked.append(dict(index=index,model=m,lump_cagr=float(l.twr_cagr_pct),dca_irr=float(c.money_irr_pct),
              mdd=float(l.twr_mdd_pct),dca_final=float(c.final_value),first=l['first'],last=l['last']))
    final=['# 국내·미국 지수 정기매수와 보유 비교 — 최종 정리','',
      '실제 ETF로 총4896회 시험했습니다. 아래는 전체 연구를 본 뒤 주목한 탐색 후보이며 개발기간의 사전 선택 모델과 구분합니다.',
      '국내는2012년부터, 미국은2008년부터2026-10-16까지입니다. 같은 납입·같은 시점·같은 시장 비용으로 비교했습니다.',
      '일시금: 국내1천만원/미국1만달러. 적립식: 초기 별도 일시금 없이 매월100만원/1000달러. 적립 수익률은 XIRR, 최대낙폭은 입금 효과를 제거한 TWR입니다.','',
      '|시장|방법|일시금 연복리|적립식 연환산 수익률|과거 최대낙폭|','|---|---|---:|---:|---:|']
    for r in picked:final.append(f"|{r['index']}|{r['model']}|{r['lump_cagr']:.2f}%|{r['dca_irr']:.2f}%|{r['mdd']:.2f}%|")
    final+=['', '## 규칙','',
      '- 국내 STATIC125: KODEX20075%+실제 KODEX레버리지25%, 월초 리밸런싱. 수익 우세에는 추가 위험 노출이 포함됩니다. 코스닥150에서는 실패했습니다.',
      '- SP500 VOL20_ALWAYS150: 최근20거래일 SPY 일간 수익률 표준편차×sqrt(252)를 v라 할 때 목표 노출 e=min(1.5,0.20/v). e가1 이하면 SPY e와 SHY(1-e),1 초과면 SPY(2-e)와 SSO(e-1). 목표가5%p 이상 바뀌면 다음 시가, 월초에도 비중을 맞춥니다.',
      '- NASDAQ100 HYST150_HALF: QQQ 종가가200일평균×1.01 위에서3거래일 연속이면 QQQ50%+QLD50%,200일평균×0.99 아래에서3거래일 연속이면 QQQ50%+SHY50%. 사이에서는 직전 상태 유지. 다음 시가 체결과 월초 리밸런싱.',
      '', '## 우월성의 한계','',
      '국내75/25는2012년 이후 전체·검증·후속 구간의 두 납입·비용1/2배·지연1/2일에서 수익을 넘었지만 낙폭은 커졌습니다.',
      '미국 두 탐색 후보는2008~2026 전체 구간의 두 납입·비용·지연 조합에서 수익과 낙폭을 함께 개선했습니다. 모든 짧은 하위 구간까지 우월한 것은 아닙니다.',
      '특히2008~2011만 보면 나스닥 HYST 적립식은 지수 적립식에 뒤졌습니다. SP500 변동성 조절도 일부 후속 구간에서 지수에 뒤졌습니다.',
      '75/25 고정 레버리지 혼합은2008~2011의 미국 일시금에서 지수에 뒤졌고, 위기 최대낙폭도 더 컸습니다.',
      '이미 검토한 역사 자료·겹치는 기간·여러 규칙 중 선택한 결과이므로 독립적인 새 검증이 아닙니다. 개인 세금·환율·국내 일부 가격 누락·조정단위 매매 한계가 남습니다.',
      '모든 시장·기간에서 확실히 이기는 비레버리지 전략을 찾았다고 주장할 수 없습니다. 실시간 모의 검증과 계좌별 세후 검증이 남습니다.']
    (OUT/'FINAL_KO.md').write_text('\n'.join(final)+'\n',encoding='utf-8')
    print('CRISIS_JSON_BEGIN');print(json.dumps(summary,separators=(',',':')));print('CRISIS_JSON_END')
if __name__=='__main__':main()
