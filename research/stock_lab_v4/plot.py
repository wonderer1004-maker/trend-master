"""Plot saved numerical results; no synthetic prices."""
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
from run import OUT,load

def main():
    selected=json.loads((OUT/'execution_gate.json').read_text())['selections']
    fig,axes=plt.subplots(2,2,figsize=(11,7),layout='constrained')
    for col,market in enumerate(['us','kr']):
      capital=100000 if market=='us' else 100000000;ax=axes[0,col];s=selected[market]
      for stress in [1,2]:
        d=pd.read_csv(OUT/'details'/f'{market}_{s}_test_{stress}_lump_equity.csv.gz',index_col=0,parse_dates=True)
        ax.plot(d.index,100*(d.equity/capital-1),label=f'{s}, cost x{stress}')
      data=load(market,'1d')
      for symbol in (['SPY','QQQ'] if market=='us' else ['069500.KS']):
        d=data[symbol].loc['2024-01-01':'2026-10-16'];fee=.001 if market=='us' else .0015
        curve=d.close/(d.open.iloc[0]*(1+fee));curve.iloc[-1]*=1-(.001 if market=='us' else .0035)
        ax.plot(d.index,100*(curve-1),label=symbol,alpha=.75)
      ax.set_title(market.upper()+': swing test, cumulative return');ax.set_ylabel('%');ax.legend(fontsize=8);ax.grid(alpha=.2)
      ax=axes[1,col]
      for opening in [5,15]:
        for stress in [1,2]:
          d=pd.read_csv(OUT/'details'/f'{market}_ORB{opening}_full_{stress}_equity.csv.gz',index_col=0,parse_dates=True)
          ax.plot(d.index,100*(d.equity/capital-1),label=f'ORB{opening}, cost x{stress}',linestyle='-' if stress==1 else '--')
      ax.set_title(market.upper()+': day-trade pilot'+(' (exit 14:30)' if market=='kr' else ''));ax.set_ylabel('%');ax.legend(fontsize=8);ax.grid(alpha=.2)
    for ax in axes.flat:ax.tick_params(axis='x',labelrotation=20,labelsize=8)
    fig.suptitle('Stock lab v4: historical research, not a profit guarantee',fontsize=13)
    fig.savefig(OUT/'curves.png',dpi=155);plt.close(fig)
if __name__=='__main__':main()
