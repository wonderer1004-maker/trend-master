export function blocked(m,now=Date.now()) {return !m || m.status!=='ok' || !Number.isFinite(Date.parse(m.checked_at)) || now-Date.parse(m.checked_at)>72*3600e3 || !m.rows?.length;}
export function target(capital,weight,price){if(!Number.isFinite(capital)||capital<0||capital>1e12||!Number.isFinite(weight)||weight<0||weight>.20000001||!(price>0))return null;const amount=capital*weight;return {amount,quantity:Math.floor(amount/price)};}
export function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
export function points(values){if(!values?.length)return '';const lo=Math.min(...values),hi=Math.max(...values);return values.map((v,i)=>`${i*300/Math.max(1,values.length-1)},${50-(v-lo)/(hi-lo||1)*45}`).join(' ');}
