import assert from 'node:assert/strict';import fs from 'node:fs';import {evaluate,guard,validateHoldings}from '../docs/domestic-alerts/logic.mjs';const data=JSON.parse(fs.readFileSync(new URL('../docs/domestic-alerts/market.json',import.meta.url)));let count=0;function test(fn){fn();count++}const date=data.as_of;
test(()=>{const r=evaluate(data,[],5000000,date);assert.ok(r.events.every(e=>e.type==='BUY'));assert.ok(r.events.length<=4)});
test(()=>assert.throws(()=>evaluate(data,[],5000000,'2099-01-01'),/오래된/));
test(()=>{const item=data.instruments['069500'],b=item.bars.at(-1),p={symbol:'069500',qty:1,entry:b.h*1.02,stop:b.h*1.01,entry_date:date};const r=evaluate(data,[p],5000000-b.c,date);assert.ok(r.events.some(e=>e.type==='SELL'));assert.ok(!r.events.some(e=>e.type==='BUY'));assert.equal(r.positions.length,1)});
test(()=>assert.throws(()=>validateHoldings([{symbol:'AAPL'}],data),/종목코드/));
test(()=>{const r=evaluate(data,[],5000000,date);const g=guard(r,{peak:6000000,equity:6000000,date:'2020-01-01',halted:false},date);assert.equal(g.risk.halted,true);assert.equal(g.result.events.length,0);const h=guard(evaluate(data,[],7000000,date),g.risk,date);assert.equal(h.risk.halted,true)});
test(()=>{const d=structuredClone(data);d.candidates=[{symbol:'069500',stop:d.instruments['069500'].bars.at(-1).c*.97,ceiling:1e8,rank:1,volume:1e9}];const r=evaluate(d,[],5000000,date);assert.equal(r.events.length,1);assert.ok(r.events[0].qty>0);assert.ok(r.events[0].qty*d.instruments['069500'].bars.at(-1).c<=1000000)});
console.log(count+' browser strategy tests passed');
const {conditions}=await import('../docs/domestic-alerts/indicators.mjs');
for(const item of Object.values(data.instruments)){assert.ok(item.metrics);assert.ok(conditions(item.metrics).every(c=>Number.isFinite(c.progress)&&c.progress>=0&&c.progress<=100))}
assert.deepEqual(conditions({close:100,ma20:100,ma60:100,return20_pct:0,turnover20:5e8}).map(c=>c.ok),[false,false,false,true]);
console.log('ETF metric availability and exact threshold boundaries verified');
