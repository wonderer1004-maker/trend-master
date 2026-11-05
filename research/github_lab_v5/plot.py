import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
from run import OUT

def main():
    summary=json.loads((OUT/'summary.json').read_text());follow=json.loads((OUT/'posthoc_followup.json').read_text());fig,axes=plt.subplots(3,2,figsize=(12,10),layout='constrained')
    for row,(case,selected) in enumerate(summary['selected'].items()):
      for cost in [1,2]:
        p=OUT/'details'/f'{case}_{selected}_{cost}_lump_primary_D1_equity.csv.gz';d=pd.read_csv(p,index_col=0,parse_dates=True)
        axes[row,0].plot(d.index,(d.unit_nav-1)*100,label=f'{selected}, cost x{cost}',lw=1.4)
      for model in ['HOLD','STATIC125']:
        p=OUT/'details'/f'{case}_{model}_1_lump_primary_D1_equity.csv.gz';d=pd.read_csv(p,index_col=0,parse_dates=True)
        axes[row,0].plot(d.index,(d.unit_nav-1)*100,label=model,alpha=.7)
      for model in [selected,'HOLD']:
        d=pd.read_csv(OUT/'details'/f'{case}_{model}_1_lump_primary_D1_equity.csv.gz',index_col=0,parse_dates=True)
        axes[row,1].plot(d.index,(d.unit_nav/d.unit_nav.cummax()-1)*100,label=model)
      for f in follow:
        if f['case']!=case:continue
        model=f['strategy'];d=pd.read_csv(OUT/'details'/f'{case}_{model}_1_lump_primary_D1_equity.csv.gz',index_col=0,parse_dates=True)
        axes[row,0].plot(d.index,(d.unit_nav-1)*100,label=model+' (post-hoc)',linestyle='--',color='purple',lw=1.3)
        axes[row,1].plot(d.index,(d.unit_nav/d.unit_nav.cummax()-1)*100,label=model+' (post-hoc)',linestyle='--',color='purple',lw=1.2)
      axes[row,0].set_title(case+' cumulative unit return');axes[row,1].set_title(case+' drawdown')
    for ax in axes.flat:ax.legend(fontsize=7);ax.grid(alpha=.2);ax.set_ylabel('%');ax.tick_params(axis='x',labelsize=8)
    fig.suptitle('Backtrader v5: selected and post-hoc candidates; reused historical data')
    fig.savefig(OUT/'curves.png',dpi=140);plt.close(fig)
if __name__=='__main__':main()
