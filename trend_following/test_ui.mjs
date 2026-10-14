import assert from 'node:assert/strict';
import {target,blocked,esc,points} from '../docs/trend-following/logic.mjs';
assert.deepEqual(target(10000000,.1,50000),{amount:1000000,quantity:20});
assert.equal(target(-1,.1,10),null);assert.equal(target(1000,.3,10),null);
assert.equal(blocked({status:'error',rows:[1],checked_at:new Date().toISOString()}),true);
assert.equal(blocked({status:'ok',rows:[1],checked_at:new Date().toISOString()}),false);
assert.equal(blocked({status:'ok',rows:[1],checked_at:'2020-01-01'}),true);
assert.equal(esc('<img>'),'&lt;img&gt;');assert.ok(!points([5,5,5]).includes('NaN'));
console.log('UI calculations: 8 checks passed');
