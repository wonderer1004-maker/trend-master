import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';import {parseCSV,scanUniverse} from './dist/engine.mjs';
const b=parseCSV(readFileSync('dist/data/synthetic_bars.csv','utf8')),i=parseCSV(readFileSync('dist/data/synthetic_index.csv','utf8')),d=parseCSV(readFileSync('dist/data/synthetic_daily.csv','utf8'),true),day=b.at(-1).day,u=['005930','000660','035420'].map(symbol=>({symbol,name:symbol,market:'KOSPI',eligible:true,as_of:day}));
const r=scanUniverse(b,i,d,u,{completeConfirmed:true});assert.equal(r.universe_count,3);assert.equal(r.bar_covered,3);assert.equal(r.signals,0); // last sample bar is outside entry time
const rejected=scanUniverse(b,i,d,u.map(x=>({...x,eligible:false})));assert.ok(rejected.rows.every(x=>x.state==='제외'&&x.plan===null));
const stale=scanUniverse(b,i,d,u.map(x=>({...x,as_of:'2020-01-01'})));assert.equal(stale.eligible_count,0);
console.log('Scanner coverage, eligibility and stale-universe checks passed');
