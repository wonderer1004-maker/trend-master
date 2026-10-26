"""Independent market processes with separate outputs, then merge complete results."""
import concurrent.futures,gzip,json,shutil,subprocess,sys,time,os
from pathlib import Path
import pandas as pd
from run import ROOT,OUT,CASES
OUT=Path(os.environ.get("GITHUB_LAB_OUTPUT",str(OUT)))

def worker(case):
    folder=OUT/'parts'/case;folder.mkdir(parents=True,exist_ok=True)
    with (folder/'run.log').open('w') as log:
      subprocess.run([sys.executable,str(ROOT/'run.py'),'--case',case,'--output',str(folder)],stdout=log,stderr=subprocess.STDOUT,check=True)
    summary=json.loads((folder/'summary.json').read_text());print(json.dumps({'case_finished':case,'runs':summary['backtrader_runs'],'seconds':summary['elapsed_seconds']}),flush=True);return folder

def main():
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:folders=list(ex.map(worker,CASES))
    comparison=pd.concat([pd.read_csv(p/'comparison.csv') for p in folders],ignore_index=True);comparison.to_csv(OUT/'comparison.csv',index=False);(OUT/'comparison.csv.gz').write_bytes(gzip.compress((OUT/'comparison.csv').read_bytes(),mtime=0))
    decisions=[];selection={};audits={};runs=0;max_error=0.;details=OUT/'details';details.mkdir(exist_ok=True)
    for p in folders:
      decisions+=json.loads((p/'decisions.json').read_text());selection.update(json.loads((p/'selection.json').read_text()));audits.update(json.loads((p/'data_audit.json').read_text()));s=json.loads((p/'summary.json').read_text());runs+=s['backtrader_runs'];max_error=max(max_error,s['max_engine_relative_error'])
      for f in (p/'details').glob('*.gz'):shutil.copyfile(f,details/f.name)
    for name,obj in [('decisions',decisions),('selection',selection),('data_audit',audits)]: (OUT/(name+'.json')).write_text(json.dumps(obj,ensure_ascii=False,indent=2))
    shutil.copyfile(folders[0]/'rules_before_run.json',OUT/'rules_before_run.json')
    summary=dict(backtrader_runs=runs,independent_ledger_runs=runs,summary_rows=len(comparison),max_engine_relative_error=max_error,selected={k:v['strategy'] for k,v in selection.items()},research_gate_passers=[x['case'] for x in decisions if x['research_gate']],live_enabled=False)
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
