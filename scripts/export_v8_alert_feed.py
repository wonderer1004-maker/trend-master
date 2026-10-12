"""Export final V8 close decisions. Not real-time quotes or broker orders."""
import argparse,json,hashlib
from pathlib import Path
from datetime import datetime,timezone
import pandas as pd
from trend_refined_v8 import enrich,target
NAMES={'069500.KS':'KODEX 200','122630.KS':'KODEX 레버리지','005930.KS':'삼성전자','000660.KS':'SK하이닉스','005380.KS':'현대차','035420.KS':'NAVER','005490.KS':'POSCO홀딩스','051910.KS':'LG화학','068270.KS':'셀트리온','006400.KS':'삼성SDI','012330.KS':'현대모비스','055550.KS':'신한지주'}
def build(state,raw):
    data=enrich(raw);asof=state['data_asof'];model='DUAL_BAND45'
    if state.get('strategy')!=model:raise ValueError('unexpected active strategy')
    if any(str(d.index[-1].date())!=asof for d in data.values()):raise ValueError('feed dates do not match decision')
    decision=state['next_target'];screen=target(data,data['069500.KS'].index[-1],model)
    positions=state['holdings'];nav=state['cash']+sum(q*float(data[s].iloc[-1].close) for s,q in positions.items())
    assets=[];alerts=[]
    for s,d in data.items():
        row=d.iloc[-1];close=float(row.close);weight=positions.get(s,0)*close/nav
        goal=decision.get(s,0) if decision is not None else None
        side='HOLD' if goal is None or abs(goal-weight)<.001 else ('BUY' if goal>weight else 'SELL')
        rec=dict(symbol=s,name=NAMES.get(s,s),close=close,ma20=float(row.ma20),ma50=float(row.ma50),ma150=float(row.ma150),ma200=float(row.ma200),
            return60=float(row.r60),return120=float(row.r120),score=float(row.score),current_weight=weight,screen_weight=screen.get(s,0),
            target_weight=goal,side=side,paper_quantity=positions.get(s,0))
        assets.append(rec)
        if side!='HOLD':alerts.append(dict(symbol=s,name=rec['name'],side=side,target_weight=goal,current_weight=weight,reference_close=close))
    payload=dict(asof=asof,strategy=model,target=decision)
    event_id=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    return dict(version=1,strategy=model,asof=asof,generated_at=datetime.now(timezone.utc).isoformat(),event_id=event_id,
        action=state.get('action','HOLD'),decision_weights=decision,cash_weight=state['cash']/nav,paused_sessions=state.get('pause_remaining',0),
        assets=assets,alerts=alerts,execution='종가 확인 → 다음 거래일 시가 참고',price_type='Yahoo 조정 일봉 · 실시간 호가 아님',
        live_orders=False,initial_cash=10000000,paper_metrics=state.get('metrics'))
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--dir',default='reports/trend_refined_v8_latest');ap.add_argument('--input');a=ap.parse_args()
    folder=Path(a.dir);state=json.loads((folder/'paper_state.json').read_text());source=Path(a.input) if a.input else folder/'input'
    raw={s:pd.read_csv(source/(s+'.csv'),index_col=0,parse_dates=True) for s in NAMES}
    feed=build(state,raw);(folder/'web_signal.json').write_text(json.dumps(feed,ensure_ascii=False,indent=2,allow_nan=False))
    print(json.dumps(dict(asof=feed['asof'],alerts=len(feed['alerts']),assets=len(feed['assets']))))
if __name__=='__main__':main()
