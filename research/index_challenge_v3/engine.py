"""Index-only rules, real 2x ETFs, exact opening cashflow accounting."""
import numpy as np
import pandas as pd

SPECS={
 'KOSPI200':dict(base='069500.KS',lever='122630.KS',market='kr',start='2012-01-01',dev_end='2017-12-31',val_start='2018-01-01',val_end='2021-12-31',test_start='2022-01-01'),
 'KOSDAQ150':dict(base='229200.KS',lever='233740.KS',market='kr',start='2017-01-01',dev_end='2019-12-31',val_start='2020-01-01',val_end='2022-12-31',test_start='2023-01-01'),
 'SP500':dict(base='SPY',lever='SSO',market='us',start='2012-01-01',dev_end='2017-12-31',val_start='2018-01-01',val_end='2021-12-31',test_start='2022-01-01'),
 'NASDAQ100':dict(base='QQQ',lever='QLD',market='us',start='2012-01-01',dev_end='2017-12-31',val_start='2018-01-01',val_end='2021-12-31',test_start='2022-01-01')}
RULES={
 'INDEX_HOLD':'100% underlying ETF; additional deposits buy at first session open each month',
 'LEV2_HOLD':'100% actual 2x ETF; risky benchmark, not an alpha strategy',
 'STATIC125':'75% underlying +25% actual 2x ETF, monthly rebalanced',
 'STATIC150':'50% underlying +50% actual 2x ETF, monthly rebalanced',
 'UNLEV_MA200':'exposure 1 above MA200, 0 below; daily state changes',
 'UNLEV_MA10':'exposure 1 above monthly MA10, 0 below; monthly',
 'UNLEV_CORE75':'exposure 1 above MA200, 0.75 otherwise',
 'MA200_125':'exposure 1.25 above MA200, 0 otherwise',
 'MA200_150':'exposure 1.5 above MA200, 0 otherwise',
 'MA200_200':'exposure 2 above MA200, 0 otherwise',
 'MA10_125':'exposure 1.25 above monthly MA10, 0 otherwise',
 'MA10_150':'exposure 1.5 above monthly MA10, 0 otherwise',
 'MA10_200':'exposure 2 above monthly MA10, 0 otherwise',
 'HYST150_HALF':'MA200*1.01 for 3 closes -> exposure1.5; MA200*.99 for 3 closes -> exposure0.5; retain state between',
 'CORE_BOOST125':'exposure1.25 above MA200, 1 otherwise',
 'THREE_STAGE':'close>MA50>MA200:1.5; otherwise close>MA200:1; else0',
 'MULTI150':'exposure1.5 times fraction of MA50/100/200 below current close',
 'VOL20_TREND150':'above MA200: min(1.5,20%/vol20); below:0; 5pp exposure band',
 'VOL20_ALWAYS150':'min(1.5,20%/vol20), no trend filter; 5pp exposure band'}
BASELINES={'INDEX_HOLD','LEV2_HOLD','STATIC125','STATIC150'}


def prepare(raw,spec):
    names=[spec['base'],spec['lever']]+(['SHY'] if spec['market']=='us' else [])
    for s in names:
        x=raw[s]
        if x.index.has_duplicates or not x.index.is_monotonic_increasing:raise ValueError('bad calendar '+s)
        if not np.isfinite(x[['open','high','low','close']]).all().all() or (x[['open','high','low','close']]<=0).any().any():raise ValueError('bad price '+s)
    idx=raw[names[0]].index
    for s in names[1:]:idx=idx.intersection(raw[s].index)
    b=raw[names[0]].close
    features={f'ma{n}':b.rolling(n).mean() for n in (50,100,200)}
    monthly=b.resample('ME').last().rolling(10).mean()
    actual_dates=pd.Series(b.index,index=b.index).groupby(b.index.to_period('M')).last()
    monthly=monthly[monthly.index.to_period('M').isin(actual_dates.index)]
    monthly.index=pd.DatetimeIndex([actual_dates.loc[x.to_period('M')] for x in monthly.index])
    features['ma10']=monthly.reindex(b.index).ffill()
    features['vol20']=b.pct_change().rolling(20).std()*np.sqrt(252)
    f=pd.DataFrame(features).reindex(idx)
    x=pd.DataFrame({'close':b.reindex(idx),**{k:f[k] for k in f}})
    targets={k:np.full(len(idx),np.nan) for k in RULES};previous={};state=.5
    for i in range(len(idx)):
        if not np.isfinite(f.iloc[i]).all():continue
        r=x.iloc[i];above=r.close>r.ma200
        if i>=2:
            z=x.iloc[i-2:i+1]
            if (z.close>z.ma200*1.01).all():state=1.5
            elif (z.close<z.ma200*.99).all():state=.5
        e20=min(1.5,.20/r.vol20) if r.vol20>0 else 0
        exposures=dict(UNLEV_MA200=float(above),UNLEV_CORE75=1. if above else .75,
          MA200_125=1.25 if above else 0,MA200_150=1.5 if above else 0,MA200_200=2. if above else 0,
          HYST150_HALF=state,CORE_BOOST125=1.25 if above else 1.,
          THREE_STAGE=1.5 if r.close>r.ma50>r.ma200 else (1. if above else 0),
          MULTI150=1.5*np.mean([r.close>r.ma50,r.close>r.ma100,r.close>r.ma200]),
          VOL20_TREND150=e20 if above else 0,VOL20_ALWAYS150=e20)
        for name,e in exposures.items():
            tolerance=.05 if name.startswith('VOL20') else 1e-10
            if name not in previous or abs(e-previous[name])>=tolerance:
                targets[name][i]=e;previous[name]=e
        # Calendar boundaries may be known in advance; final partial month is not treated as a completed month.
        if i+1<len(idx) and idx[i].month!=idx[i+1].month:
            for name,cap in [('UNLEV_MA10',1),('MA10_125',1.25),('MA10_150',1.5),('MA10_200',2)]:
                targets[name][i]=cap if r.close>r.ma10 else 0
            targets['STATIC125'][i]=1.25;targets['STATIC150'][i]=1.5
    # Held target as of every close. Baselines are initialized before the test start too.
    filled={k:pd.Series(v,index=idx).ffill().to_numpy() for k,v in targets.items()}
    for name,e in [('INDEX_HOLD',1.),('LEV2_HOLD',2.),('STATIC125',1.25),('STATIC150',1.5)]:filled[name][:]=e
    return dict(idx=idx,names=names,market=spec['market'],open=np.column_stack([raw[s].loc[idx,'open'] for s in names]),
      close=np.column_stack([raw[s].loc[idx,'close'] for s in names]),target=filled,events=targets,
      removed={s:[str(t.date()) for t in raw[s].index.difference(idx)] for s in names})


def weights(e,p):
    if not np.isfinite(e) or not 0<=e<=2:raise ValueError('invalid exposure')
    w=np.zeros(p)
    if e<=1:
        w[0]=e
        if p==3:w[2]=1-e
    else:w[0]=2-e;w[1]=e-1
    return w


def money_irr(flows,final):
    times=np.array([(d-flows[0][0]).days/365.25 for d,_ in flows]);t=times[-1]
    # caller appends a zero flow at valuation date; avoids date rounding in annual IRR.
    values=np.array([v for _,v in flows]);horizon=t-times
    lo,hi=-10.,10.
    for _ in range(90):
        mid=(lo+hi)/2;fv=float(values@np.exp(mid*horizon))
        if fv>final:hi=mid
        else:lo=mid
    return float(np.expm1((lo+hi)/2))


def replay(d,model,start,end,funding='LUMP',cost=1,delay=1,custom_target=None):
    idx=d['idx'];a=int(idx.searchsorted(pd.Timestamp(start)));z=int(idx.searchsorted(pd.Timestamp(end),side='right'))
    if a<delay or z-a<2:raise ValueError('insufficient evaluation dates')
    p=len(d['names']);units=np.zeros(p);cash=0.;fund_units=0.;flows=[];curve=[];orders=[];last_target=None
    initial=10000 if d['market']=='us' else 10000000
    monthly=1000 if d['market']=='us' else 1000000
    fee=(.0002 if d['market']=='us' else .0005)*cost;slip=(.0005 if d['market']=='us' else .001)*cost
    target=custom_target if custom_target is not None else d['target'][model]
    contribution=0.
    for i in range(a,z):
        first=i==a;month_first=first or idx[i].month!=idx[i-1].month
        flow=(initial if first else 0) if funding=='LUMP' else (monthly if month_first else 0)
        opening_nav=cash+float(units@d['open'][i])
        if flow:
            price=opening_nav/fund_units if fund_units>0 else 1.
            fund_units+=flow/price;cash+=flow;contribution+=flow;flows.append((idx[i],flow))
        e=float(target[i-delay])
        if not np.isfinite(e):raise ValueError('unwarmed target '+model)
        change=last_target is None or abs(e-last_target)>1e-10
        # A target changed at previous close is executed now; fresh deposits use that same latest target.
        monthly_static=model not in ('INDEX_HOLD','LEV2_HOLD','BENCH_A','BENCH_B') and month_first
        trade=first or change or bool(flow) or monthly_static
        if trade:
            op=d['open'][i];nav=cash+float(units@op)
            if d.get('rotation'):
                choice=int(e//3);exposure=e-choice*3;w=np.zeros(p)
                if exposure<=1:
                    w[choice*2]=exposure
                    if p==5:w[4]=1-exposure
                else:w[choice*2]=2-exposure;w[choice*2+1]=exposure-1
            else:w=weights(e,p)
            if (model in ('INDEX_HOLD','LEV2_HOLD') and custom_target is None or model in ('BENCH_A','BENCH_B')) and not first:
                goal=units.copy();j=2 if model=='BENCH_B' else (0 if model in ('INDEX_HOLD','BENCH_A') else 1)
                goal[j]+=cash/(op[j]*(1+slip)*(1+fee))
            else:goal=nav*w/op
            delta=goal-units;sold=np.maximum(-delta,0)
            cash+=float((sold*op*(1-slip)*(1-fee)).sum());units-=sold
            buy=np.maximum(delta,0);needed=float((buy*op*(1+slip)*(1+fee)).sum())
            if needed>0:buy*=min(1,max(0,cash/needed))
            cash-=float((buy*op*(1+slip)*(1+fee)).sum());units+=buy
            for j in range(p):
                for side,q,price in [('SELL',sold[j],op[j]*(1-slip)),('BUY',buy[j],op[j]*(1+slip))]:
                    if q*op[j]>max(1,contribution)*1e-9:orders.append((idx[i-delay],idx[i],d['names'][j],side,float(q),float(price),flow))
        last_target=e
        if cash<-.001 or (units< -1e-10).any():raise AssertionError('unfunded or short position')
        pv=units*d['close'][i];nav=cash+float(pv.sum());unitprice=nav/fund_units
        actual_exposure=float((pv[0]+2*pv[1]+(pv[2]+2*pv[3] if d.get('rotation') else 0))/nav)
        curve.append((idx[i],nav,unitprice,cash,flow,contribution,actual_exposure))
    eq=pd.DataFrame(curve,columns=['date','equity','unit_price','cash','contribution','paid_in','exposure']).set_index('date')
    path=np.r_[1.,eq.unit_price.to_numpy()];r=path[1:]/path[:-1]-1
    years=(eq.index[-1]-eq.index[0]).days/365.25
    cagr=float(path[-1]**(1/years)-1);mdd=float((path/np.maximum.accumulate(path)-1).min())
    irr=money_irr(flows+[(eq.index[-1],0)],float(eq.equity.iloc[-1]))
    stat=dict(final_value=float(eq.equity.iloc[-1]),contributed=contribution,profit=float(eq.equity.iloc[-1]-contribution),
       twr_cagr_pct=cagr*100,money_irr_pct=irr*100,twr_mdd_pct=mdd*100,
       avg_exposure=float(eq.exposure.mean()),calmar=cagr/abs(mdd) if mdd<0 else 0,
       volatility_pct=float(np.std(r,ddof=1)*np.sqrt(252)*100),order_count=len(orders),
       first=str(eq.index[0].date()),last=str(eq.index[-1].date()),currency='USD' if d['market']=='us' else 'KRW')
    od=pd.DataFrame(orders,columns=['signal_date','fill_date','symbol','side','adjusted_units','fill_price','external_flow'])
    return stat,eq,od
