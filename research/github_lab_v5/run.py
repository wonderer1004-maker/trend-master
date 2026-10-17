"""Backtrader + independent-ledger comparison, fixed candidate set, reused history."""
import argparse,gzip,hashlib,json,time
from pathlib import Path
import numpy as np
import pandas as pd
from models import load,build,RULES,BENCHMARKS,ROOT
from bt_engine import execute,reference
from assess import metrics,select,block_bootstrap_excess,WINDOWS
OUT=ROOT.parents[1]/'reports'/'github_lab_v5'
CASES={'SP500':('us',None),'NASDAQ100':('us','QQQ'),'KOSPI200':('kr',None)}
INDEX_ONLY={'HOLD','LEV2_HOLD','STATIC125','OLD_HYST150','OLD_VOL20','NEW_TREND_ENSEMBLE','NEW_CORE_ENSEMBLE'}

def save(key,e,o):
    p=OUT/'details';p.mkdir(exist_ok=True,parents=True);e.to_csv(p/f'{key}_equity.csv.gz');o.to_csv(p/f'{key}_orders.csv.gz',index=False)

def one(data,w,case,model,market,cost,funding,stage,delay=1):
    initial=100000. if market=='us' else 100000000.;flow=initial*.01 if funding=='monthly' else 0.
    e,o,stats=execute(data,w,'2018-01-01','2026-10-16',market,cost,flow,delay,model in ['HOLD','LEV2_HOLD'],initial)
    ref=reference(data,w,'2018-01-01','2026-10-16',market,cost,flow,delay,model in ['HOLD','LEV2_HOLD'],initial)
    error=float(np.max(abs(e.equity-ref.equity)/np.maximum(1,ref.equity)))
    if error>1e-8:raise AssertionError(f'engine mismatch {case} {model}: {error}')
    key=f'{case}_{model}_{cost}_{funding}_{stage}_D{delay}';save(key,e,o)
    rows=[]
    for window in WINDOWS:
      rows.append(dict(case=case,market=market,strategy=model,stage=stage,cost=cost,funding=funding,delay=delay,window=window,engine_rel_error=error,**metrics(e,o,initial,window)))
    return rows,e

def main():
    global OUT
    parser=argparse.ArgumentParser();parser.add_argument('--case',choices=list(CASES));parser.add_argument('--output');args=parser.parse_args();OUT=Path(args.output) if args.output else OUT;OUT.mkdir(exist_ok=True,parents=True)
    # Recorded before evaluations; not a claim of external preregistration.
    rulelog={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.glob('*.py')};rulelog['strategies']=RULES
    (OUT/'rules_before_run.json').write_text(json.dumps(rulelog,indent=2))
    rows=[];audit={};selections={};curves={};decisions=[];run_count=0;t=time.monotonic()
    for case,(market,override) in CASES.items():
      if args.case and args.case!=case:continue
      data,qa=load(market);audit[case]=qa;models=build(data,market,base_override=override)
      if case=='NASDAQ100':models={k:v for k,v in models.items() if k in INDEX_ONLY}
      for model,w in models.items():
        for cost in [1,2]:
          for funding in ['lump','monthly']:
            rr,e=one(data,w,case,model,market,cost,funding,'primary');rows+=rr;run_count+=1
            if funding=='lump' and cost==1:curves[(case,model)]=e
        print(json.dumps(dict(progress=case,strategy=model,runs=run_count,seconds=round(time.monotonic()-t,1))),flush=True)
      selected,scores=select(pd.DataFrame(rows),case);selections[case]=dict(strategy=selected,development_scores=scores)
      # Extra open delay, only development-selected candidate and same baseline.
      for model in [selected,'HOLD']:
        for cost in [1,2]:
          for funding in ['lump','monthly']:
            rr,e=one(data,models[model],case,model,market,cost,funding,'delay_stress',delay=2);rows+=rr;run_count+=1
      if market=='kr':
        alternate,qa=load(market,'yahoo');audit['KR_YAHOO']=qa;altmodels=build(alternate,market)
        for model in sorted(set([selected,'HOLD','OLD_HYST150','V8_HYST45_PORT'])):
          for cost in [1,2]:
            for funding in ['lump','monthly']:
              rr,e=one(alternate,altmodels[model],case,model,market,cost,funding,'source_control');rows+=rr;run_count+=1
      frame=pd.DataFrame(rows);checks=[]
      for stage in ['primary','delay_stress']:
        for window in ['validation_reused','test_reused']:
          for cost in [1,2]:
            for funding in ['lump','monthly']:
              subset=frame[(frame.case==case)&(frame.stage==stage)&(frame.window==window)&(frame.cost==cost)&(frame.funding==funding)]
              a=subset[subset.strategy==selected].iloc[0];b=subset[subset.strategy=='HOLD'].iloc[0];metric='xirr' if funding=='monthly' else 'cagr'
              checks.append(dict(stage=stage,window=window,cost=cost,funding=funding,positive=bool(a[metric]>0),higher_return=bool(a[metric]>b[metric]),lower_drawdown=bool(a.mdd>=b.mdd)))
      boot=block_bootstrap_excess(curves[(case,selected)],curves[(case,'HOLD')],100000. if market=='us' else 100000000.)
      passed=all(c['positive'] and c['higher_return'] and c['lower_drawdown'] for c in checks) and boot['positive_lower_bound']
      decisions.append(dict(case=case,selected=selected,research_gate=passed,live_enabled=False,checks=checks,bootstrap=boot,reason='reused history and fixed surviving-stock universe; independent forward observation still required'))
    frame=pd.DataFrame(rows);frame.to_csv(OUT/'comparison.csv',index=False);(OUT/'comparison.csv.gz').write_bytes(gzip.compress((OUT/'comparison.csv').read_bytes(),mtime=0))
    for name,obj in [('data_audit',audit),('selection',selections),('decisions',decisions)]: (OUT/f'{name}.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2))
    result=dict(backtrader_runs=run_count,summary_rows=len(rows),max_engine_relative_error=float(frame.engine_rel_error.max()),elapsed_seconds=time.monotonic()-t,selection=selections,decisions=decisions,live_enabled=False)
    (OUT/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
