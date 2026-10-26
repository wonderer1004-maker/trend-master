"""Explicitly post-hoc follow-up: no replacement of development-selected models."""
import json
import numpy as np
import pandas as pd
from run import OUT,CASES,one
from models import load,build,BENCHMARKS
from assess import block_bootstrap_excess

def main():
    d=pd.read_csv(OUT/'comparison.csv');d=d[d.stage!='posthoc_delay'].copy();base_rows=d.copy();found=[];extra=[];out=[]
    # Mechanical screen across all candidates, not just the best terminal CAGR.
    for case,(market,override) in CASES.items():
      z=d[(d.case==case)&(d.stage=='primary')&d.window.isin(['validation_reused','test_reused'])];b=z[z.strategy=='HOLD']
      for model in sorted(set(z.strategy)-BENCHMARKS):
        m=z[z.strategy==model].merge(b,on=['window','cost','funding'],suffixes=('_a','_b'))
        okay=m.apply(lambda r:(r.xirr_a>r.xirr_b and r.xirr_a>0) if r.funding=='monthly' else (r.cagr_a>r.cagr_b and r.cagr_a>0),axis=1)&(m.mdd_a>=m.mdd_b)
        if len(m)==8 and okay.all():found.append((case,model))
    for case,model in found:
      market,override=CASES[case];data,_=load(market);weights=build(data,market,base_override=override)[model]
      for cost in [1,2]:
        for funding in ['lump','monthly']:
          rows,e=one(data,weights,case,model,market,cost,funding,'posthoc_delay',delay=2);extra+=rows
      initial=100000. if market=='us' else 100000000.
      e=pd.read_csv(OUT/'details'/f'{case}_{model}_1_lump_primary_D1_equity.csv.gz',index_col=0,parse_dates=True)
      b=pd.read_csv(OUT/'details'/f'{case}_HOLD_1_lump_primary_D1_equity.csv.gz',index_col=0,parse_dates=True)
      boot=block_bootstrap_excess(e,b,initial);f=pd.DataFrame(extra);check=[]
      for window in ['validation_reused','test_reused']:
        for cost in [1,2]:
          for funding in ['lump','monthly']:
            a=f[(f.case==case)&(f.strategy==model)&(f.window==window)&(f.cost==cost)&(f.funding==funding)].iloc[0]
            bb=base_rows[(base_rows.case==case)&(base_rows.strategy=='HOLD')&(base_rows.stage=='delay_stress')&(base_rows.window==window)&(base_rows.cost==cost)&(base_rows.funding==funding)].iloc[0]
            metric='xirr' if funding=='monthly' else 'cagr';check.append(dict(window=window,cost=cost,funding=funding,positive=bool(a[metric]>0),higher_return=bool(a[metric]>bb[metric]),lower_drawdown=bool(a.mdd>=bb.mdd)))
      passed=all(x['positive'] and x['higher_return'] and x['lower_drawdown'] for x in check)
      out.append(dict(case=case,strategy=model,selection='POST_HOC_ALL_PRIMARY_EIGHT_JOINT_WINS; not development-selected',primary_joint_wins=8,delay_checks=check,delay_all_pass=passed,bootstrap=boot,exploratory_gate=bool(passed and boot['positive_lower_bound']),live_enabled=False))
    if extra:d=pd.concat([d,pd.DataFrame(extra)],ignore_index=True)
    d.to_csv(OUT/'comparison.csv',index=False)
    import gzip
    (OUT/'comparison.csv.gz').write_bytes(gzip.compress((OUT/'comparison.csv').read_bytes(),mtime=0));(OUT/'posthoc_followup.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
    summary=json.loads((OUT/'summary.json').read_text());primary=summary.get('primary_backtrader_runs',summary['backtrader_runs']);summary.update(primary_backtrader_runs=primary,backtrader_runs=primary+4*len(found),independent_ledger_runs=primary+4*len(found),summary_rows=len(d),max_engine_relative_error=float(d.engine_rel_error.max()),posthoc_candidates=[dict(case=c,strategy=m) for c,m in found],posthoc_gate_passers=[dict(case=x['case'],strategy=x['strategy']) for x in out if x['exploratory_gate']]);(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps({'posthoc_followup':out,'summary':summary},ensure_ascii=False))
if __name__=='__main__':main()
