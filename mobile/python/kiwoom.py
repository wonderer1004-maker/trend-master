"""Read-only Kiwoom REST adapter. Does NOT transmit orders."""
import os,json,time,argparse
from urllib.request import Request,urlopen
from pathlib import Path
import pandas as pd

class Kiwoom:
    def __init__(self):
        self.base='https://mockapi.kiwoom.com'; self.token=None
    def request(self,path,body,api=None,cont='N',key=''):
        headers={'Content-Type':'application/json;charset=UTF-8'}
        if api: headers.update({'authorization':'Bearer '+self.token,'api-id':api,'cont-yn':cont,'next-key':key})
        req=Request(self.base+path,data=json.dumps(body).encode(),headers=headers)
        with urlopen(req,timeout=30) as r:
            out=json.load(r); h=dict((k.lower(),v) for k,v in r.headers.items())
        if int(out.get('return_code',0))!=0: raise RuntimeError(out.get('return_msg','Kiwoom error'))
        return out,h
    def login(self):
        d,_=self.request('/oauth2/token',{'grant_type':'client_credentials','appkey':os.environ['KIWOOM_APPKEY'],'secretkey':os.environ['KIWOOM_SECRET']}); self.token=d['token']
    def collect(self,symbol,kind,max_pages):
        api='ka10080' if kind=='minute' else 'ka10081'
        body={'stk_cd':symbol,'upd_stkpc_tp':'1'}
        if kind=='minute': body['tic_scope']='5'
        else: body['base_dt']=pd.Timestamp.now(tz='Asia/Seoul').strftime('%Y%m%d')
        arr='stk_min_pole_chart_qry' if kind=='minute' else 'stk_dt_pole_chart_qry'
        rows=[]; cont='N'; key=''; seen=set()
        for _ in range(max_pages):
            d,h=self.request('/api/dostk/chart',body,api,cont,key)
            if arr not in d: raise ValueError('Chart schema changed; inspect official API guide')
            for r in d[arr]:
                rows.append({'timestamp':pd.to_datetime(r['cntr_tm'] if kind=='minute' else r['dt'],format='%Y%m%d%H%M%S' if kind=='minute' else '%Y%m%d'),'symbol':symbol,'open':abs(float(r['open_pric'])),'high':abs(float(r['high_pric'])),'low':abs(float(r['low_pric'])),'close':abs(float(r['cur_prc'])),'volume':abs(float(r['trde_qty']))})
            cont=h.get('cont-yn','N'); key=h.get('next-key','')
            if cont!='Y': break
            if not key or key in seen: raise RuntimeError('Invalid pagination cursor')
            seen.add(key); time.sleep(.6)
        out=pd.DataFrame(rows)
        if out.empty: raise ValueError('No chart data')
        return out.drop_duplicates(['timestamp','symbol']).sort_values('timestamp')

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--symbols',required=True); p.add_argument('--kind',choices=['minute','daily'],default='minute'); p.add_argument('--pages',type=int,default=30); p.add_argument('--out',required=True); a=p.parse_args()
    k=Kiwoom(); k.login(); out=pd.concat([k.collect(s,a.kind,a.pages) for s in a.symbols.split(',')]); Path(a.out).parent.mkdir(parents=True,exist_ok=True); out.to_csv(a.out,index=False); print('Saved',len(out),'bars. Verify timestamps, adjustment and session completeness before backtest.')
