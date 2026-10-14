import json, hashlib, xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
import pandas as pd

P=Path(__file__).parent
CFG=json.loads((P/'protocol.json').read_text())

def load_market(market, total_return=True):
    frames={}; audit={}
    for s in CFG['universe'][market]:
        path=P/'raw'/f'{s}.json'
        z=json.loads(path.read_text())['chart']['result'][0]
        idx=pd.to_datetime(z['timestamp'],unit='s',utc=True).tz_convert(z['meta']['exchangeTimezoneName']).tz_localize(None).normalize()
        d=pd.DataFrame(z['indicators']['quote'][0],index=idx)[['open','high','low','close','volume']]
        adj=pd.Series(z['indicators']['adjclose'][0]['adjclose'],index=idx)
        d=d.loc[d.index<=CFG['end']].copy(); adj=adj.reindex(d.index)
        valid=d.notna().all(axis=1)&adj.notna()&(d[['open','high','low','close']]>0).all(axis=1)&(adj>0)&(d.volume>0)
        missing_dates=[str(x.date()) for x in d.index[~valid]]
        if market=='KR':
            nx=P/'raw'/f'{s[:6]}_naver.xml'
            root=ET.fromstring(nx.read_bytes().decode('euc-kr'))
            rows=[a.attrib['data'].split('|') for a in root.iter('item')]
            nd=pd.DataFrame(rows,columns=['date','open','high','low','close','volume'])
            nd.index=pd.to_datetime(nd.pop('date'),format='%Y%m%d');nd=nd.astype(float)
            nd=nd.loc[(nd.index>='2014-01-01')&(nd.index<=CFG['end'])]
            d=nd;adj=d.close.copy()
            assert d.notna().all().all() and (d[['open','high','low','close','volume']]>0).all().all()
        else:assert valid.all(), f'missing or invalid bars {s}' 
        envelope=(d[['open','close']].max(axis=1)>d.high)|(d[['open','close']].min(axis=1)<d.low)
        repairs=[str(x.date()) for x in d.index[envelope]]
        if market=='KR':
            assert ((d[['open','close']].max(axis=1)-d.high)/d.close<.001).all()
            assert ((d.low-d[['open','close']].min(axis=1))/d.close<.001).all()
            d['high']=d[['high','open','close']].max(axis=1)
            d['low']=d[['low','open','close']].min(axis=1)
        assert not d.index.duplicated().any()
        assert (d.high+1e-5>=d[['open','close']].max(axis=1)).all()
        assert (d.low-1e-5<=d[['open','close']].min(axis=1)).all()
        if total_return: d.loc[:,['open','high','low','close']]=d[['open','high','low','close']].mul(adj/d.close,axis=0)
        audit[s]={'source':'NAVER_PRICE_ONLY' if market=='KR' else 'YAHOO_ADJUSTED_PROXY','envelope_repairs_below10bps':repairs,'yahoo_missing_dates':missing_dates,'rows':len(d),'first':str(d.index[0].date()),'last':str(d.index[-1].date()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'name':z['meta'].get('longName'),'daily_abs_return_over15pct':{str(k.date()):v for k,v in d.close.pct_change().items() if abs(v)>.15}}
        frames[s]=d
    index=next(iter(frames.values())).index
    assert all(d.index.equals(index) for d in frames.values()),'market calendars differ'
    return frames,audit

def features(data, params=(60,20,120,60,50,200),vol_window=60):
    o=pd.DataFrame({s:d.open for s,d in data.items()});c=pd.DataFrame({s:d.close for s,d in data.items()})
    h=pd.DataFrame({s:d.high for s,d in data.items()});l=pd.DataFrame({s:d.low for s,d in data.items()})
    a,b,x,y,f,slow=params
    return {'index':c.index,'symbols':list(c.columns),'o':o.to_numpy(),'c':c.to_numpy(),
        'vol':(c.pct_change().rolling(vol_window).std(ddof=1)*np.sqrt(252)).to_numpy(),
        'upA':(c>h.rolling(a).max().shift()).to_numpy(),'dnA':(c<l.rolling(b).min().shift()).to_numpy(),
        'upB':(c>h.rolling(x).max().shift()).to_numpy(),'dnB':(c<l.rolling(y).min().shift()).to_numpy(),
        'upC':(c.rolling(f).mean()>c.rolling(slow).mean()).to_numpy(),'dnC':(c.rolling(f).mean()<c.rolling(slow).mean()).to_numpy(),
        'up200':(c>c.rolling(200).mean()).to_numpy(),'dn200':(c<c.rolling(200).mean()).to_numpy()}

def scores(f,i,state,model):
    for j,k in enumerate(['A','B','C','200']):
        state[j]=np.where(f['dn'+k][i],False,np.where(f['up'+k][i],True,state[j]))
    if model in ['HOLD_EQUAL','ALWAYS_INVVOL','FIXED50']:return np.ones(len(f['symbols']))
    if model=='BLEND':return state[:3].mean(axis=0)
    return state[{'BREAK60':0,'BREAK120':1,'MA50_200':2,'SMA200':3}[model]].astype(float)

def metrics(curve, initial=1.):
    arr=np.r_[initial,curve.to_numpy()];peak=np.maximum.accumulate(arr);dd=arr/peak-1
    days=(curve.index[-1]-curve.index[0]).days+1;growth=(arr[-1]/initial)**(365.25/days)-1
    underwater=0;longest=0
    for v in dd:
        underwater=underwater+1 if v<-1e-10 else 0;longest=max(longest,underwater)
    return {'return_pct':float((arr[-1]/initial-1)*100),'CAGR_pct':float(growth*100),'MDD_pct':float(dd.min()*100),'Calmar':float(growth/abs(dd.min())) if dd.min()<0 else None,'longest_underwater_sessions':longest,'underwater_at_end':bool(dd[-1]<-1e-10)}

def simulate(f,model,start,end,cost=.001,save=None,delay=0,fixed_fraction=.5):
    index=f['index'];ids=np.where((index>=start)&(index<=end))[0];n=len(f['symbols'])
    qty=np.zeros(n);cash=1.;state=np.zeros((4,n),bool);lastscore=np.zeros(n);cap=np.zeros(n)
    target=np.zeros(n);orders=[];records=[];total_fee=0.;turn=0.;first=True
    for pos,i in enumerate(ids):
        k=i-1-delay;assert k>=0
        sc=scores(f,k,state,model)
        week=index[k].to_period('W-FRI')!=index[k+1].to_period('W-FRI')
        changed=abs(sc-lastscore)>1e-12
        trade=first or (model!='HOLD_EQUAL' and (week or changed.any()))
        if first or week:
            v=f['vol'][k];inv=np.where(np.isfinite(v)&(v>0),1/v,0.)
            cap=np.minimum(.2,inv/inv.sum()) if inv.sum()>0 else np.zeros(n)
            target=cap*sc
        else:target[changed]=cap[changed]*sc[changed]
        if model=='HOLD_EQUAL':target=np.ones(n)/n
        if model=='FIXED50':target=np.ones(n)*fixed_fraction/n
        opening=f['o'][i];close=f['c'][i];eqopen=cash+qty@opening
        if trade:
            # Solve self-financing post-cost NAV for a portfolio of target weights.
            values=qty*opening;post=eqopen
            for _ in range(30):post=eqopen-cost*np.abs(post*target-values).sum()
            desired=post*target/opening;delta=desired-qty
            for a in np.flatnonzero(np.abs(delta*opening)>1e-10):
                notional=delta[a]*opening[a];fee=abs(notional)*cost
                orders.append({'date':str(index[i].date()),'signal_date':str(index[k].date()),'symbol':f['symbols'][a],'side':'BUY' if delta[a]>0 else 'SELL','notional_initial_nav':float(abs(notional)),'fee_initial_nav':float(fee),'target_weight':float(target[a]),'price_synthetic':float(opening[a])})
                total_fee+=fee;turn+=abs(notional)/eqopen
            cash=eqopen-np.abs(delta*opening).sum()*cost-(desired*opening).sum();qty=desired
            assert cash>-1e-9
        nav=cash+qty@close;exposure=qty@close/nav
        if pos==len(ids)-1:
            for a in np.flatnonzero(qty>1e-12):
                value=qty[a]*close[a];fee=value*cost;total_fee+=fee;turn+=value/nav
                orders.append({'date':str(index[i].date()),'signal_date':None,'symbol':f['symbols'][a],'side':'SELL_END','notional_initial_nav':float(value),'fee_initial_nav':float(fee),'target_weight':0.,'price_synthetic':float(close[a])})
            cash+=qty@close*(1-cost);qty[:]=0;nav=cash
        records.append({'date':str(index[i].date()),'nav':float(nav),'exposure':float(exposure),'cash':float(cash),'target_sum':float(target.sum())})
        assert nav>0 and target.sum()<=1+1e-9
        lastscore=sc.copy();first=False
    frame=pd.DataFrame(records).set_index('date');frame.index=pd.to_datetime(frame.index);curve=frame.nav
    out=metrics(curve);out.update(orders=len(orders),buy_orders=sum(x['side']=='BUY' for x in orders),sell_orders=sum(x['side']!='BUY' for x in orders),average_exposure_pct=float(frame.exposure.mean()*100),oneway_turnover_per_year=float(turn/((index[ids[-1]]-index[ids[0]]).days/365.25)),fees_pct_initial_nav=float(total_fee*100))
    prev=1.;yearly={}
    for y,p in curve.groupby(curve.index.year):yearly[str(y)]=float((p.iloc[-1]/prev-1)*100);prev=p.iloc[-1]
    out['yearly_pct']=yearly
    if save:
        (P/(save+'_orders.json')).write_text(json.dumps(orders,indent=2));(P/(save+'_equity.json')).write_text(json.dumps(records,indent=2));(P/(save+'_metrics.json')).write_text(json.dumps(out,indent=2))
    return out,frame,orders

def main():
    results=[];sensitivity=[];audits={};price_checks=[]
    for market in CFG['universe']:
        data,audit=load_market(market);audits[market]=audit;f=features(data)
        for model in CFG['models']:
            for period,(start,end) in CFG['periods'].items():
                for label,cost in [('normal',.001),('stress',.005)]:
                    out,_,_=simulate(f,model,start,end,cost,save=f'{market}_{model}_{period}_{label}' if period=='full' else None)
                    results.append(dict(market=market,model=model,period=period,cost=label,**out))
        for label,params,vol in [('channels_minus20',(48,16,96,48,50,200),60),('channels_plus20',(72,24,144,72,50,200),60),('MA_minus20',(60,20,120,60,40,160),60),('MA_plus20',(60,20,120,60,60,240),60),('vol_minus20',(60,20,120,60,50,200),48),('vol_plus20',(60,20,120,60,50,200),72)]:
            ff=features(data,params,vol)
            for period in ['validation','recent','full']:
                for fee,cost in [('normal',.001),('stress',.005)]:
                    out,_,_=simulate(ff,'BLEND',*CFG['periods'][period],cost)
                    sensitivity.append(dict(market=market,variant=label,period=period,cost=fee,**out))
        dp,_=load_market(market,False);fp=features(dp)
        for model in CFG['models']:
            out,_,_=simulate(fp,model,*CFG['periods']['full'],.001)
            price_checks.append(dict(market=market,model=model,**out))
    for name,val in [('results',results),('sensitivity',sensitivity),('data_audit',audits),('price_only_checks',price_checks)]:
        (P/f'{name}.json').write_text(json.dumps(val,indent=2))
    for m in CFG['universe']:
        print(m)
        for r in results:
            if r['market']==m and r['period']=='full' and r['cost']=='normal':print(r['model'],*[round(r[k],3) for k in ['return_pct','CAGR_pct','MDD_pct','Calmar','average_exposure_pct']])

if __name__=='__main__':main()
