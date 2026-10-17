import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from engine import SPECS,RULES,BASELINES,prepare,replay

ROOT=Path(__file__).resolve().parent;OUT=ROOT.parents[1]/'reports'/'index_challenge_v3'

def load():
    meta=json.loads((ROOT/'input'/'provenance.json').read_text());raw={}
    for r in meta:
        p=ROOT/'input'/r['market']/(r['symbol']+'.csv.gz')
        if hashlib.sha256(gzip.decompress(p.read_bytes())).hexdigest()!=r['csv_sha256']:raise ValueError('snapshot checksum mismatch')
        raw[r['symbol']]=pd.read_csv(p,index_col=0,parse_dates=True)
    return raw

def main():
    OUT.mkdir(parents=True,exist_ok=True);raw=load();rows=[];prepared={};audits={}
    (OUT/'rules.json').write_text(json.dumps(RULES,indent=2),encoding='utf-8')
    for index,spec in SPECS.items():
        d=prepare(raw,spec);prepared[index]=d;audits[index]=d['removed']
        if str(d['idx'][-1].date())!='2026-10-16':raise ValueError('stale input')
        periods=[('full',spec['start'],'2026-10-16'),('development',spec['start'],spec['dev_end']),
          ('validation',spec['val_start'],spec['val_end']),('later',spec['test_start'],'2026-10-16'),
          ('recent','2024-01-01','2026-10-16'),('since2020','2020-01-01','2026-10-16')]
        for period,start,end in periods:
            for model in RULES:
                for funding in ['LUMP','DCA']:
                    for cost in [1,2]:
                        for delay in [1,2]:
                            stats,eq,orders=replay(d,model,start,end,funding,cost,delay)
                            rows.append(dict(index=index,period=period,model=model,funding=funding,cost=cost,delay=delay,**stats))
                            if period=='full' and cost==delay==1:
                                folder=OUT/'details'/index;folder.mkdir(parents=True,exist_ok=True)
                                eq.to_csv(folder/(model+'_'+funding+'_equity.csv'));orders.to_csv(folder/(model+'_'+funding+'_orders.csv'),index=False)
            print('completed',index,period,flush=True)
    table=pd.DataFrame(rows)
    base=table[table.model=='INDEX_HOLD'][['index','period','funding','cost','delay','final_value','money_irr_pct','twr_mdd_pct']].rename(columns={
        'final_value':'benchmark_final','money_irr_pct':'benchmark_irr_pct','twr_mdd_pct':'benchmark_mdd_pct'})
    table=table.merge(base,on=['index','period','funding','cost','delay'],validate='many_to_one')
    table['wealth_ratio']=table.final_value/table.benchmark_final
    table['excess_irr_pp']=table.money_irr_pct-table.benchmark_irr_pct
    table['beats_return']=table.wealth_ratio>1+1e-9
    table['improves_both']=table.beats_return&(table.twr_mdd_pct>table.benchmark_mdd_pct+1e-8)
    table.to_csv(OUT/'comparison.csv',index=False)
    active=table[~table.model.isin(BASELINES)]
    dev=active[active.period=='development'];selection={}
    for index in SPECS:
        scores=dev[dev['index']==index].groupby('model').excess_irr_pp.min().to_dict()
        selected=sorted(scores,key=lambda k:(-scores[k],k))[0]
        selection[index]=dict(selected_on_development=selected,development_worst_excess_irr_pp=scores[selected],scores=scores)
    scores=dev.groupby('model').excess_irr_pp.min().to_dict()
    common=sorted(scores,key=lambda k:(-scores[k],k))[0]
    selection['common']=dict(selected_on_development=common,development_worst_excess_irr_pp=scores[common],scores=scores)
    gates={}
    for index in SPECS:
        q=active[(active['index']==index)&active.period.isin(['full','validation','later'])]
        gates[index]=dict(return_all_cases=[m for m,g in q.groupby('model') if g.beats_return.all()],
          return_and_drawdown_all_cases=[m for m,g in q.groupby('model') if g.improves_both.all()])
    joint=active[active.period.isin(['full','validation','later'])]
    gates['ALL_INDICES']=dict(return_all_cases=[m for m,g in joint.groupby('model') if g.beats_return.all()],
        return_and_drawdown_all_cases=[m for m,g in joint.groupby('model') if g.improves_both.all()])
    vintages=[]
    for index,d in prepared.items():
        selected=selection[index]['selected_on_development'];common_model=selection['common']['selected_on_development']
        for year in range(int(SPECS[index]['start'][:4]),2024):
            for funding in ['LUMP','DCA']:
                b,_,_=replay(d,'INDEX_HOLD',f'{year}-01-01','2026-10-16',funding)
                for m in set([selected,common_model]):
                    met,_,_=replay(d,m,f'{year}-01-01','2026-10-16',funding)
                    vintages.append(dict(index=index,start_year=year,model=m,funding=funding,wealth_ratio=met['final_value']/b['final_value'],
                      improves_both=met['final_value']>b['final_value'] and met['twr_mdd_pct']>b['twr_mdd_pct']))
    pd.DataFrame(vintages).to_csv(OUT/'start_year_checks.csv',index=False)
    (OUT/'selection.json').write_text(json.dumps(selection,indent=2),encoding='utf-8')
    (OUT/'gates.json').write_text(json.dumps(gates,indent=2),encoding='utf-8')
    (OUT/'calendar_audit.json').write_text(json.dumps(audits,indent=2),encoding='utf-8')
    protocol=dict(data_end='2026-10-16',rules_sha256=hashlib.sha256((ROOT/'engine.py').read_bytes()).hexdigest(),
      funding=dict(LUMP='initial KRW10million / USD10000, no subsequent contributions',
                   DCA='zero initial, KRW1million / USD1000 at first session open of every month including first month'),
      accounting='opening external flows issue fund units at pre-flow open NAV; drawdown and CAGR based on fund unit price; XIRR uses dated external flows and final value',
      selection='choose active rule with highest minimum development excess money-IRR across both cashflows, both costs and both execution delays; no validation/later data used',
      execution='prior close target; next session open; delay2 stress; fresh deposits use latest executable target; monthly rebalance for active/static blends',
      costs=dict(us=dict(fee_each_side=.0002,slippage_each_side=.0005),kr=dict(fee_each_side=.0005,slippage_each_side=.001)),
      limitations=['real 2x ETF prices embed daily reset, expenses and financing; no synthetic 2*index return',
       'real 2x ETFs increase risk exposure, so higher returns are not evidence of alpha',
       'no direct borrowing/shorting; fractional adjusted units, not whole-share broker execution',
       'Yahoo adjustment approximates pre-tax distribution reinvestment; no double-added dividends',
       'US returns USD, exclude FX and personal capital-gains/dividend taxes; account-specific Korean ETF taxes also excluded',
       'idle KRW cash zero interest, US defensive holdings SHY, ETF exchange sell tax assumed zero',
       'some source OHLC sessions missing; common-date intersection disclosed; does not reconstruct missing daily trades',
       'monthly thresholds are targets, allocation can drift intramonth',
       'four liquid index/2x pairs chosen today; indices are investable ETF proxies not exact tax-free index returns',
       'historical period splits already partly inspected in prior research; no claim of untouched live out-of-sample',
       'unleveraged alternatives and static leveraged benchmarks retained; all 15 candidates and all failed cases disclosed',
       'starting-year checks overlap and are not statistically independent'])
    (OUT/'protocol.json').write_text(json.dumps(protocol,indent=2),encoding='utf-8')
    summary=dict(total_runs=len(table),selection=selection,gates=gates,
      full_base=table[(table.period=='full')&(table.cost==1)&(table.delay==1)].to_dict('records'),
      selected_periods=[r for r in table.to_dict('records') if r['model']==selection[r['index']]['selected_on_development'] or r['model']==common])
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    lines=['# 지수 정기매수·보유 초과 전략 연구 V3','',
      '국내 코스피200·코스닥150, 미국 S&P500·나스닥100의 지수 ETF와 실제 2배 ETF만 사용합니다.',
      '일시금과 정기매수를 서로 다른 납입 방식으로 분리하며, 같은 방식 안에서는 모든 전략의 납입 날짜와 금액이 같습니다.',
      '보유 기준선도 정기매수 방식에서는 월초 추가 납입금을 지수 ETF로 즉시 매수합니다.',
      '원금 유입으로 낙폭이 줄어 보이지 않도록 펀드 단위가격(TWR)으로 낙폭을 계산합니다. 적립식 수익률은 날짜별 현금흐름 XIRR입니다.',
      '실제 2배 ETF를 쓰는 후보는 위험 노출이 커집니다. 지수보다 높은 수익 자체가 초과수익 능력의 입증은 아닙니다.',
      '비용1·2배 × 다음날/이틀후 시가 체결 × 일시금/정기매수 × 6구간 × 19규칙 × 4지수 = 3648회. 원형 논문 재현이 아닌 고정 적용안입니다.',
      '',f'개발기간만으로 고른 공통 규칙: **{common}**. 개발기간 최악 초과 XIRR: {scores[common]:.2f}%p. 양수 여부를 확인해야 합니다.','']
    for index,spec in SPECS.items():
        chosen=selection[index]['selected_on_development'];lines += [f'## {index}', '',
          f"기간 {spec['start']}~2026-10-16. 개발기간 선택: **{chosen}**. 개발기간 최악 초과 XIRR {selection[index]['development_worst_excess_irr_pp']:.2f}%p.",
          '', '|전략|일시금 연복리|적립식 XIRR|일시금 최대낙폭|적립식 최종금액|','|---|---:|---:|---:|---:|']
        for model in RULES:
            l=table[(table['index']==index)&(table.period=='full')&(table.model==model)&(table.funding=='LUMP')&(table.cost==1)&(table.delay==1)].iloc[0]
            c=table[(table['index']==index)&(table.period=='full')&(table.model==model)&(table.funding=='DCA')&(table.cost==1)&(table.delay==1)].iloc[0]
            lines.append(f"|{model}|{l.twr_cagr_pct:.2f}%|{c.money_irr_pct:.2f}%|{l.twr_mdd_pct:.2f}%|{c.final_value:,.0f} {c.currency}|")
        lines += ['', '### 엄격한 후속기간 통과 여부','',
          f"전체·검증·후속 구간의 두 납입 방식, 비용1·2배, 지연1·2일에서 모두 수익 우세: {gates[index]['return_all_cases']}",
          f"위 조건에서 수익·낙폭 모두 개선: {gates[index]['return_and_drawdown_all_cases']}",'']
    lines += ['## 규칙','']+[f'- **{k}**: {v}' for k,v in RULES.items()]
    lines += ['', '## 검증 원자료', '',
      '- [Gayed/Bilello 원 논문](https://docs.cmtassociation.org/dow-award/2016-gayed-bilello.pdf)',
      '- [SSO 공식 자료](https://www.proshares.com/our-etfs/leveraged-and-inverse/sso)',
      '- [QLD 공식 자료](https://www.proshares.com/our-etfs/leveraged-and-inverse/qld)',
      '- [KRX KODEX 레버리지 공시](https://kind.krx.co.kr/disclosure/etfisudetail.do?method=searchEtfIsuSummary&strIsurCd=12263)',
      '', '상세 납입·단위가격·주문 내역은 Actions artifact의 details/에서 확인합니다. 개인 세금·환율·분봉 체결은 검증 범위 밖입니다.',
      '사후에 성과가 좋았던 전략과 개발기간에서 고정한 전략을 구분해야 하며, 향후 수익을 보장하지 않습니다.']
    (OUT/'README_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(table[(table.period=='full')&(table.cost==1)&(table.delay==1)][['index','model','funding','twr_cagr_pct','money_irr_pct','twr_mdd_pct','wealth_ratio']].to_string(index=False))
    print('SUMMARY_JSON_BEGIN');print(json.dumps(summary,separators=(',',':')));print('SUMMARY_JSON_END')
if __name__=='__main__':main()
