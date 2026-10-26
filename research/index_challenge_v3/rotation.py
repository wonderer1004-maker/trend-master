"""Second hypothesis batch: rotate index pairs; documented after stage-A results."""
import json
import hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from engine import replay
from run import load,ROOT,OUT

RULES={'BENCH_A':None,'BENCH_B':None,'ROT6_100':(126,1.),'ROT12_100':(252,1.),
       'ROT6_125':(126,1.25),'ROT6_150':(126,1.5),'ROTBLEND_125':(0,1.25),'ROTBLEND_150':(0,1.5)}
REGIONS={'KR':dict(names=['069500.KS','122630.KS','229200.KS','233740.KS'],start='2017-01-01',dev_end='2019-12-31',val_start='2020-01-01',val_end='2022-12-31',later='2023-01-01',market='kr'),
 'US':dict(names=['SPY','SSO','QQQ','QLD','SHY'],start='2012-01-01',dev_end='2017-12-31',val_start='2018-01-01',val_end='2021-12-31',later='2022-01-01',market='us')}

def prepare_rotation(raw,spec):
    names=spec['names'];idx=raw[names[0]].index
    for s in names[1:]:idx=idx.intersection(raw[s].index)
    feat={}
    for s in names:
        c=raw[s].close
        feat[s]=pd.DataFrame(dict(r6=c/c.shift(126)-1,r12=c/c.shift(252)-1,above=c>c.rolling(200).mean())).reindex(idx)
    targets={m:np.full(len(idx),np.nan) for m in RULES};targets['BENCH_A'][:]=1;targets['BENCH_B'][:]=4
    for i in range(len(idx)-1):
        if idx[i].month==idx[i+1].month:continue
        for m,rule in RULES.items():
            if rule is None:continue
            n,cap=rule;scores=[]
            for j,s in enumerate([names[0],names[2]]):
                r=feat[s].iloc[i]
                score=r.r6 if n==126 else r.r12 if n==252 else .5*r.r6+.5*r.r12
                hurdle=0.
                if spec['market']=='us':
                    f=feat['SHY'].iloc[i];hurdle=f.r6 if n==126 else f.r12 if n==252 else .5*f.r6+.5*f.r12
                if np.isfinite(score) and score>hurdle and bool(r.above):scores.append((score,j))
            targets[m][i]=(max(scores)[1]*3+cap) if scores else 0.
    targets={m:pd.Series(x,index=idx).ffill().to_numpy() for m,x in targets.items()}
    return dict(idx=idx,names=names,market=spec['market'],rotation=True,target=targets,
       open=np.column_stack([raw[s].loc[idx,'open'] for s in names]),close=np.column_stack([raw[s].loc[idx,'close'] for s in names]),
       removed={s:[str(t.date()) for t in raw[s].index.difference(idx)] for s in names})


def main():
    raw=load();rows=[];selection={};gates={};audit={};OUT.mkdir(exist_ok=True,parents=True)
    for region,spec in REGIONS.items():
        d=prepare_rotation(raw,spec);audit[region]=d['removed']
        periods=[('full',spec['start'],'2026-10-16'),('development',spec['start'],spec['dev_end']),
          ('validation',spec['val_start'],spec['val_end']),('later',spec['later'],'2026-10-16'),('recent','2024-01-01','2026-10-16')]
        for period,start,end in periods:
            for model in RULES:
                for funding in ['LUMP','DCA']:
                    for cost in [1,2]:
                        for delay in [1,2]:
                            stat,eq,orders=replay(d,model,start,end,funding,cost,delay,custom_target=d['target'][model])
                            rows.append(dict(region=region,period=period,model=model,funding=funding,cost=cost,delay=delay,**stat))
                            if period=='full' and cost==delay==1:
                                folder=OUT/'rotation_details'/region;folder.mkdir(exist_ok=True,parents=True)
                                eq.to_csv(folder/(model+'_'+funding+'_equity.csv'));orders.to_csv(folder/(model+'_'+funding+'_orders.csv'),index=False)
            print('completed rotation',region,period,flush=True)
    table=pd.DataFrame(rows)
    keys=['region','period','funding','cost','delay']
    bench=table[table.model.isin(['BENCH_A','BENCH_B'])].groupby(keys).agg(best_benchmark_final=('final_value','max'),best_benchmark_irr=('money_irr_pct','max'))
    table=table.merge(bench,on=keys);table['wealth_ratio_vs_best_index']=table.final_value/table.best_benchmark_final
    table['beats_both_indices']=table.wealth_ratio_vs_best_index>1+1e-9
    table['excess_irr_pp']=table.money_irr_pct-table.best_benchmark_irr
    for region in REGIONS:
        dev=table[(table.region==region)&(table.period=='development')&(~table.model.str.startswith('BENCH'))]
        scores=dev.groupby('model').excess_irr_pp.min().to_dict();selected=sorted(scores,key=lambda m:(-scores[m],m))[0]
        selection[region]=dict(selected_on_development=selected,worst_development_excess_irr_pp=scores[selected],scores=scores)
        q=table[(table.region==region)&table.period.isin(['full','validation','later'])&(~table.model.str.startswith('BENCH'))]
        gates[region]=[m for m,g in q.groupby('model') if g.beats_both_indices.all()]
    table.to_csv(OUT/'rotation_comparison.csv',index=False)
    summary=dict(total_runs=len(table),selection=selection,gates=gates,
      full_base=table[(table.period=='full')&(table.cost==1)&(table.delay==1)].to_dict('records'))
    (OUT/'rotation_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    (OUT/'rotation_calendar_audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
    lines=['# 2차 가설: 같은 시장의 두 지수 교체','',
       '1차 고정 지수 타이밍 실험 결과를 본 뒤 추가한 탐색입니다. 새 독립 검증으로 주장하지 않습니다.',
       '국내 코스피200/코스닥150, 미국 S&P500/나스닥100의 실제 ETF 쌍을 월말에 비교합니다.',
       '6개월 또는12개월 모멘텀, 또는 두 모멘텀의 평균으로 순위를 정합니다. MA200 위이고 현금(미국SHY)보다 강한 지수만 선택합니다.',
       '후보가 없으면 국내현금/미국SHY를 보유합니다. 1.25배/1.5배 목표는 실제2배 ETF를 25%/50% 섞습니다.',
       '같은 납입 방식·같은 구간의 두 지수 보유 중 사후 성과가 더 높은 지수까지 넘는지를 비교합니다.',
       '개발기간에서만 선택하며 검증·후속 구간의 비용/지연 결과도 모두 공개합니다. 국내기간은 2017년부터입니다.','']
    for region in REGIONS:
        lines += [f'## {region}', '',f"개발기간 선택: {selection[region]['selected_on_development']}. 최악 초과 XIRR {selection[region]['worst_development_excess_irr_pp']:.2f}%p.",
          '', '|규칙|일시금 연복리|적립식 XIRR|일시금 최대낙폭|적립 최종금액/강한지수 적립|','|---|---:|---:|---:|---:|']
        for model in RULES:
            q=table[(table.region==region)&(table.period=='full')&(table.model==model)&(table.cost==1)&(table.delay==1)]
            l=q[q.funding=='LUMP'].iloc[0];c=q[q.funding=='DCA'].iloc[0]
            lines.append(f'|{model}|{l.twr_cagr_pct:.2f}%|{c.money_irr_pct:.2f}%|{l.twr_mdd_pct:.2f}%|{c.wealth_ratio_vs_best_index:.3f}倍|')
        lines += ['',f'전체·검증·후속의 모든 납입/비용/지연 조건에서 두 지수 모두보다 높은 최종금액: {gates[region]}','']
    (OUT/'ROTATION_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(table[(table.period=='full')&(table.cost==1)&(table.delay==1)][['region','model','funding','twr_cagr_pct','money_irr_pct','twr_mdd_pct','wealth_ratio_vs_best_index']].to_string(index=False))
    print('ROTATION_JSON_BEGIN');print(json.dumps(summary,separators=(',',':')));print('ROTATION_JSON_END')
if __name__=='__main__':main()
