import hashlib
import gzip
import json
from pathlib import Path
import numpy as np
import pandas as pd
from engine import RULES,BASELINES,prepare,schedules,replay,exposure_control
from download import US,KR

ROOT=Path(__file__).resolve().parent
OUT=ROOT.parents[1]/'reports'/'quant_survey_v2'

def load(market):
    names=US if market=='us' else KR
    provenance=json.loads((ROOT/'input'/'provenance.json').read_text())
    hashes={r['symbol']:r.get('csv_sha256') for r in provenance}
    for name in names:
        file=ROOT/'input'/market/(name+'.csv.gz')
        if hashlib.sha256(gzip.decompress(file.read_bytes())).hexdigest()!=hashes.get(name):raise ValueError('snapshot hash mismatch: '+name)
    return {s:pd.read_csv(ROOT/'input'/market/(s+'.csv.gz'),index_col=0,parse_dates=True) for s in names}

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    protocol=dict(candidates={k:v for k,v in RULES.items() if k not in BASELINES},
      selection='development: choose highest worst-case Calmar across costs1/2 and delays1/2, requiring CAGR>0 and >=60% of benchmark CAGR, risk-asset exposure>=35%; no later data used',
      development=dict(us=['2010-01-01','2018-12-31'],kr=['2020-01-01','2023-12-31']),
      local_run='fixed rules, no parameter grid or retry until winner',
      initial=dict(us=100000,kr=10000000),execution='signals at close, next session open; delay2 also tested',
      costs=dict(us=dict(fee_each_side=.0002,slippage_each_side=.0005,sell_tax=0),
                 kr=dict(fee_each_side=.0005,slippage_each_side=.001,stock_sell_tax=.002,etf_sell_tax=0)),
      assumptions=['fractional adjusted units, not actual whole-share broker sizing',
       'Yahoo adjclose ratio approximates pre-tax dividend reinvestment; distributions not added again',
       'US USD returns exclude KRW/USD FX and personal Korean overseas capital gains taxes',
       'fixed sell taxes are research assumptions, not actual historical tax schedule',
       'cash interest zero; US defensive holdings use SHY adjusted prices',
       'signals use only past/current prices; monthly actions only after observed completed month-end',
       'equal exposure controls compare risk-asset budget, NOT matched volatility/beta',
       'no short selling, borrowing, synthesized leveraged returns or optimized parameters',
       'all data and periods are historical; development split is not proof of untouched data',
       'Korean 10 surviving stocks are not all-market or survivorship-free',
       'US fixed long-lived ETF universe selected today introduces universe-selection bias',
       'Korean source missing daily bars require disclosed calendar intersection',
       'daily OHLC cannot verify 09:05 execution or intraday fills; market impact not modeled'])
    (OUT/'protocol.json').write_text(json.dumps(protocol,indent=2,ensure_ascii=False),encoding='utf-8')
    (OUT/'rules_sha256.txt').write_text(hashlib.sha256((ROOT/'engine.py').read_bytes()).hexdigest()+'\n')
    allrows=[];selections={};coverage={};audit={};controls=[]
    for market in ['us','kr']:
        raw=load(market);d=prepare(raw,market);end=str(d['idx'][-1].date())
        if end!='2026-10-16':raise ValueError(f'{market}: stale dataset ends {end}')
        audit[market]=d['removed']
        coverage[market]=[dict(symbol=s,rows=len(x),first=str(x.index[0].date()),last=str(x.index[-1].date())) for s,x in raw.items()]
        periods=[('full','2010-01-01',end),('development','2010-01-01','2018-12-31'),
          ('validation','2019-01-01','2023-12-31'),('recent','2024-01-01',end),('since2020','2020-01-01',end)] if market=='us' else [
          ('full','2020-01-01',end),('development','2020-01-01','2023-12-31'),('recent_reused','2024-01-01',end)]
        for period,start,finish in periods:
            targets=schedules(d,start)
            for model,target in targets.items():
                for cost in (1,2):
                    for delay in (1,2):
                        stats,eq,orders=replay(d,target,start,finish,cost,delay)
                        row=dict(market=market,period=period,model=model,cost=cost,delay=delay,**stats)
                        allrows.append(row)
                        if period=='full' and cost==delay==1:
                            folder=OUT/'details'/market;folder.mkdir(parents=True,exist_ok=True)
                            eq.to_csv(folder/(model+'_equity.csv'));orders.to_csv(folder/(model+'_orders.csv'),index=False)
                            annual=eq.equity.resample('YE').last();base=annual.shift();base.iloc[0]=stats['initial_value']
                            pd.DataFrame({'year':annual.index.year,'return_pct':(annual/base-1).values*100}).to_csv(folder/(model+'_annual.csv'),index=False)
                if period=='full' and model not in BASELINES:
                    stats,_,_=replay(d,exposure_control(d,target),start,finish)
                    controls.append(dict(market=market,model=model,**stats))
            print('completed',market,period,flush=True)
        table=pd.DataFrame(allrows)
        dev=table[(table.market==market)&(table.period=='development')&(~table.model.isin(BASELINES))]
        bench=table[(table.market==market)&(table.period=='development')&(table.model=='BENCH_HOLD')]
        scores={}
        for model,g in dev.groupby('model'):
            joined=g.merge(bench[['cost','delay','cagr_pct']],on=['cost','delay'],suffixes=('','_benchmark'))
            if ((joined.cagr_pct>0)&(joined.cagr_pct>=.6*joined.cagr_pct_benchmark)&(joined.average_risk_assets_pct>=35)).all():
                scores[model]=float(g.calmar.min())
        selected=sorted(scores,key=lambda z:(-scores[z],z))[0] if scores else None
        selections[market]=dict(selected_on_development_only=selected,eligible_scores=scores,
            no_claim_of_independent_unseen_data=True)
    table=pd.DataFrame(allrows)
    benchmarks=table[table.model=='BENCH_HOLD'][['market','period','cost','delay','cagr_pct','mdd_pct']].rename(columns={'cagr_pct':'benchmark_cagr_pct','mdd_pct':'benchmark_mdd_pct'})
    table=table.merge(benchmarks,on=['market','period','cost','delay'],validate='many_to_one')
    table['profitable']=table.total_return_pct>0
    table['beats_benchmark_return']=table.cagr_pct>table.benchmark_cagr_pct
    table['improves_both']=table.beats_benchmark_return&(table.mdd_pct>table.benchmark_mdd_pct)
    table.to_csv(OUT/'comparison.csv',index=False)
    pd.DataFrame(controls).to_csv(OUT/'exposure_controls.csv',index=False)
    (OUT/'sources.json').write_text((ROOT/'sources.json').read_text(),encoding='utf-8')
    gate={}
    for market in ['us','kr']:
        q=table[(table.market==market)&(table.period.isin(['full','recent','recent_reused']))&(~table.model.isin(BASELINES))]
        gate[market]=[model for model,g in q.groupby('model') if g.improves_both.all()]
    (OUT/'robust_gate.json').write_text(json.dumps(gate,indent=2))
    (OUT/'selection.json').write_text(json.dumps(selections,indent=2),encoding='utf-8')
    (OUT/'coverage.json').write_text(json.dumps(coverage,indent=2),encoding='utf-8')
    (OUT/'calendar_audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
    summary=dict(selection=selections,full_results=table[(table.period=='full')&(table.cost==1)&(table.delay==1)].to_dict('records'),
                 selected_periods=[r for r in table.to_dict('records') if r['model']==selections[r['market']]['selected_on_development_only']],
                 robust_improves_return_and_drawdown_full_and_later=gate,
                 checks=dict(total_runs=len(table),rule_count=14,us_end='2026-10-16',kr_end='2026-10-16'))
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
    lines=['# 공개 연구 기반 퀀트 전략 비교 — V2','',
      '2026-10-17 수집. 미국 11 ETF, 국내 10개 생존 대형주와 KODEX200. 실제 종가 기준 2026-10-16까지.',
      '논문 원형의 수익률을 재현한 것이 아니라, 명시한 매수 전용 적용 변형의 연구 결과입니다.',
      '미국 수익률은 달러 기준이며 원화 환율·개인 세금은 제외합니다. 국내는 전 종목 검증이 아닙니다.',
      '14개 후보 규칙을 결과 확인 전에 고정했습니다. 개발기간 선택 모델과 전체기간 사후 최고 모델을 구분합니다.',
      '거래비용1·2배와 체결1·2거래일 지연을 모두 공개합니다. 조정 단위의 소수 수량을 사용합니다.',
      '누락 거래일·투자 대상 선택 편향·논문 규칙과 차이는 protocol.json, calendar_audit.json, sources.json에서 확인하세요.','']
    for market in ['us','kr']:
        g=table[(table.market==market)&(table.period=='full')&(table.cost==1)&(table.delay==1)].sort_values('cagr_pct',ascending=False)
        lines += [f'## {market.upper()} 전체기간', '',f"개발기간만으로 선택한 모델: **{selections[market]['selected_on_development_only']}**",'',
          '|전략|연복리|총수익률|최대낙폭|평균 위험자산 비중|','|---|---:|---:|---:|---:|']
        for r in g.to_dict('records'):lines.append(f"|{r['model']}|{r['cagr_pct']:.2f}%|{r['total_return_pct']:.2f}%|{r['mdd_pct']:.2f}%|{r['average_risk_assets_pct']:.1f}%|")
        lines += ['', '### 개발기간 선택 모델의 기간·비용별 결과','', '|기간|비용|지연|연복리|최대낙폭|지수보다 수익·낙폭 모두 개선|','|---|---:|---:|---:|---:|---|']
        chosen=table[(table.market==market)&(table.model==selections[market]['selected_on_development_only'])]
        for r in chosen.to_dict('records'):lines.append(f"|{r['period']}|{r['cost']}배|{r['delay']}일|{r['cagr_pct']:.2f}%|{r['mdd_pct']:.2f}%|{r['improves_both']}|")
        lines+=['']
    lines += ['## 해석과 엄격한 통과 여부','',
      '국내 전체기간 기본비용 결과에서는 HIGH52, LOWVOL, INVVOL, ENSEMBLE이 지수보다 높은 연복리와 작은 최대낙폭을 보였습니다.',
      '하지만 전체기간과 최근기간의 비용·지연 모든 조합에서 수익률과 낙폭을 동시에 개선한 능동 전략은 두 시장 모두 없었습니다.',
      'LOWVOL은 국내 개발기간만으로 선택되었지만 최근기간에는 KODEX200보다 수익률이 낮았습니다. HIGH52의 최근 초과수익은 비용·지연에 민감합니다.',
      '미국 장기 구간에서 이번 능동 후보는 SPY 단순 보유 수익률을 넘지 못했습니다. VOL15는 수익 일부를 포기하며 낙폭을 줄였습니다.',
      'LOWVOL과 HIGH52는 각 3자산에 약 1/3씩 투자하는 집중 전략이며, 낮은 이름의 위험을 보장하지 않습니다.',
      '', '## 조사한 원자료','']
    for source in json.loads((ROOT/'sources.json').read_text()):
        lines += [f"- [{source['family']}]({source['source']}): {source['test']}"]
    lines += ['', '## 고정 규칙','']+[f'- **{k}**: {v}' for k,v in RULES.items()]
    lines += ['', '## 확인 범위', '',
      '과거 양의 수익과 향후 수익 보장은 다릅니다. 사후 최고 전략은 탐색 결과이며 새 검증이 필요합니다.',
      '국내 데이터 날짜 누락은 같은 제공자에서 재수집해도 남아 공통 날짜만 사용했습니다. 실제 거래정지 처리의 대체가 아닙니다.',
      '일별 자산·연도별 수익률·거래내역은 Actions 다운로드 자료의 details/에 있습니다. 실주문은 실행하지 않습니다.']
    (OUT/'README_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(table[(table.period=='full')&(table.cost==1)&(table.delay==1)][['market','model','cagr_pct','mdd_pct','improves_both']].to_string(index=False))
    print('SUMMARY_JSON_BEGIN');print(json.dumps(summary,separators=(',',':')));print('SUMMARY_JSON_END')
if __name__=='__main__':main()
