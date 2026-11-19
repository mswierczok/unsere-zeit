'use strict';
// Stand-alone, read-only PWA. No access credentials or private URLs are embedded.
const $ = q => document.querySelector(q);
const TZ = 'Europe/Berlin';
const dfDate = new Intl.DateTimeFormat('de-DE',{timeZone:TZ,weekday:'long',day:'numeric',month:'long'});
const dfMonth = new Intl.DateTimeFormat('de-DE',{timeZone:TZ,month:'long',year:'numeric'});
const dfTime = new Intl.DateTimeFormat('de-DE',{timeZone:TZ,hour:'2-digit',minute:'2-digit'});
const dfWeek = new Intl.DateTimeFormat('de-DE',{timeZone:TZ,weekday:'short'});
const partsFormatter = new Intl.DateTimeFormat('en-GB',{timeZone:TZ,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
const parts = d => Object.fromEntries(partsFormatter.formatToParts(d).filter(p=>p.type!=='literal').map(p=>[p.type,+p.value]));
const p2 = n => String(n).padStart(2,'0');
const keyOf = d => {let p=parts(d);return `${p.year}-${p2(p.month)}-${p2(p.day)}`};
const fromKey = s => new Date(s+'T12:00:00Z');
const plusDays = (d,n) => new Date(d.getTime()+n*86400000);
const month = (y,m,day=1) => new Date(Date.UTC(y,m,day,12));
const monthParts = d=>({y:d.getUTCFullYear(),m:d.getUTCMonth()});
const esc = s => String(s ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const local = (s,t='09:00')=>{const [y,m,d]=s.split('-').map(Number),[h,min]=t.split(':').map(Number),desired=Date.UTC(y,m-1,d,h,min);let actual=new Date(desired);for(let i=0;i<3;i++){const p=parts(actual),clock=Date.UTC(p.year,p.month-1,p.day,p.hour,p.minute);actual=new Date(actual.getTime()+desired-clock)}return actual};
const todayKey = ()=>keyOf(new Date());
const tm=monthParts(fromKey(todayKey()));
const state={view:month(tm.y,tm.m),selected:todayKey(),events:[],sources:{me:{configured:false},her:{configured:false}},updatedAt:null,recovery:8,filter:'all',periodStart:null,periodEnd:null};
let passphrase = null;
let demoMode = false;
let snapshotVersion = null;
let notificationTimer;
function notify(message){const n=$('#toast');n.textContent=message;n.classList.remove('hidden');clearTimeout(notificationTimer);notificationTimer=setTimeout(()=>n.classList.add('hidden'),3800)}
function b64(s){let bin=atob(s);return Uint8Array.from(bin,c=>c.charCodeAt(0))}
async function decrypt(payload, secret){
 if(!payload||payload.v!==1||payload.kdf!=='PBKDF2-SHA256'||!Number.isInteger(payload.iterations)||payload.iterations<250000||payload.iterations>1500000)throw Error('Unbekanntes Datenformat');
 const salt=b64(payload.salt), nonce=b64(payload.nonce), encrypted=b64(payload.ciphertext);
 if(salt.length!==16||nonce.length!==12||encrypted.length<16)throw Error('Ungültige verschlüsselte Daten');
 const source=await crypto.subtle.importKey('raw',new TextEncoder().encode(secret),'PBKDF2',false,['deriveKey']);
 const key=await crypto.subtle.deriveKey({name:'PBKDF2',salt,iterations:payload.iterations,hash:'SHA-256'},source,{name:'AES-GCM',length:256},false,['decrypt']);
 const plain=await crypto.subtle.decrypt({name:'AES-GCM',iv:nonce},key,encrypted);
 const data=JSON.parse(new TextDecoder().decode(plain));
 if(!data||data.format!==1||!Array.isArray(data.events)||!data.sources||!data.updatedAt||data.events.length>15000)throw Error('Ungültige Kalenderdaten');
 for (const e of data.events){if(!['me','her'].includes(e.owner)||typeof e.start!=='string'||typeof e.end!=='string'||typeof e.title!=='string')throw Error('Ungültiges Kalenderformat')}
 return data;
}
async function downloadEncrypted(){
 let r=await fetch('./snapshot.enc.json?t='+Date.now(),{cache:'no-store'});
 if(r.status===404)throw Error('Die erste Kalender-Synchronisierung ist noch nicht eingerichtet. Details stehen in der README.');
 if(!r.ok)throw Error('Kalenderdaten sind aktuell nicht erreichbar.');
 const content=await r.text(); if(content.length>4000000)throw Error('Die Kalenderdatei ist zu groß.');
 return JSON.parse(content);
}
function setData(data,payload){
 state.events=data.events;
 state.sources=data.sources;
 state.updatedAt=data.updatedAt;
 state.periodStart=data.periodStart||null;state.periodEnd=data.periodEnd||null;
 snapshotVersion=payload.ciphertext;
 render();
}
async function openWithPassword(secret){
 demoMode=false;
 const payload=await downloadEncrypted();
 const data=await decrypt(payload,secret);
 passphrase=secret;
 setData(data,payload);
 $('#unlock').classList.add('hidden');$('#app').classList.remove('hidden');$('#passphrase').value='';
}
async function refresh({quiet=false}={}){
 if(demoMode){if(!quiet)notify('Demo: nur Beispieldaten, keine echte Synchronisierung.');return}
 if(!passphrase)return;
 try{
   const payload=await downloadEncrypted();
   if(payload.ciphertext===snapshotVersion){if(!quiet)notify('Kalender ist auf dem neuesten Stand.');updateStatus();return}
   const data=await decrypt(payload,passphrase);
   setData(data,payload);
   if(!quiet)notify('Neue Kalenderdaten geladen.');
 }catch(e){if(!quiet)notify('Aktualisierung nicht möglich: '+e.message);updateStatus()}
}
function signOut(){demoMode=false;passphrase=null;snapshotVersion=null;state.events=[];state.periodStart=null;state.periodEnd=null;$('#app').classList.add('hidden');$('#unlock').classList.remove('hidden');$('#unlockError').textContent='';$('#passphrase').value=''}
const fullCoverage=()=>Boolean(state.sources.me?.configured&&state.sources.her?.configured);
const dataAge=()=>state.updatedAt?(Date.now()-new Date(state.updatedAt).getTime())/3600000:Infinity;
function trustworthy(){return !demoMode && fullCoverage() && dataAge()>=-0.2 && dataAge()<4}
function updateStatus(){
 if(demoMode){$('#meStatus').textContent='Beispieldaten';$('#herStatus').textContent='Beispieldaten';$('#syncAge').textContent='Demo';const banner=$('#connectionNotice');banner.textContent='DEMO: Alle angezeigten Termine sind erfunden. Es sind keine Kalenderquellen verbunden.';banner.classList.remove('hidden');return}
 const age=dataAge();
 const sourceCount=owner=>Number.isInteger(state.sources[owner]?.eventCount)?state.sources[owner].eventCount:state.events.filter(e=>e.owner===owner).length;
 $('#meStatus').textContent=state.sources.me?.configured?(state.sources.me.name||'iCloud')+' · '+sourceCount('me')+' Termine':'Noch nicht verbunden';
 $('#herStatus').textContent=state.sources.her?.configured?'MYDUTY · '+sourceCount('her')+' Schichten':'Noch nicht verbunden';
 $('#syncAge').textContent=Number.isFinite(age)?'vor '+(age<1?Math.max(1,Math.round(age*60))+' Min.':Math.round(age)+' Std.'):'Nicht synchronisiert';
 const note=$('#connectionNotice');
 const problems=[];
 if(!fullCoverage())problems.push('Nicht beide Kalenderquellen sind eingerichtet. Freie Zeitfenster sind unverbindlich.');
 if(state.sources.me?.configured && state.events.every(e=>e.owner!=='me'))problems.push('Marcel: Die synchronisierten Quellen haben im angezeigten Zeitraum keine Termine geliefert.');
 if(age>=4)problems.push('Die letzte erfolgreiche Aktualisierung ist älter als vier Stunden. Eventuell ist ein MYDUTY-Link abgelaufen.');
 if(age<-.2)problems.push('Das Datum der Synchronisierung liegt in der Zukunft; die Systemzeit prüfen.');
 note.textContent=problems.join(' '); note.classList.toggle('hidden',problems.length===0);
}
function dayEvents(day){const start=local(day,'00:00').getTime(),after=local(keyOf(plusDays(fromKey(day),1)),'00:00').getTime();return state.events.filter(e=>new Date(e.start).getTime()<after&&new Date(e.end).getTime()>start)}
function slots(day){
 let start=local(day,'09:00').getTime(), end=local(day,'23:00').getTime(),busy=[];
 for(let e of state.events){if(e.isOff)continue;let a=Date.parse(e.start),b=Date.parse(e.end);if(!Number.isFinite(a)||!Number.isFinite(b))continue;
   if(e.owner==='her'&&(e.isNight||/\b(nacht\w*|night\w*|n|nd)\b/i.test(e.title)))b+=state.recovery*3600000;
   if(a>=end||b<=start)continue;busy.push([Math.max(a,start),Math.min(b,end)]);
 }
 busy.sort((a,b)=>a[0]-b[0]);let merged=[];
 for(let pair of busy){if(merged.length&&pair[0]<=merged[merged.length-1][1])merged[merged.length-1][1]=Math.max(pair[1],merged[merged.length-1][1]);else merged.push([...pair])}
 let result=[],at=start;for(let [a,b] of merged){if(a>at)result.push({start:new Date(at),end:new Date(a),minutes:(a-at)/60000});at=Math.max(at,b)}if(at<end)result.push({start:new Date(at),end:new Date(end),minutes:(end-at)/60000});return result;
}
function renderMonth(){
 const {y,m}=monthParts(state.view),first=month(y,m),offset=(first.getUTCDay()+6)%7,initial=plusDays(first,-offset);
 $('#monthTitle').textContent=dfMonth.format(state.view);
 const grid=$('#monthGrid');grid.replaceChildren();
 for(let i=0;i<42;i++){
  const d=plusDays(initial,i),k=keyOf(d),events=dayEvents(k);
  const visible=events.filter(e=>state.filter==='all'||e.owner===state.filter);
  const owners=['me','her'].filter(owner=>visible.some(e=>e.owner===owner&&!e.isOff));
  const isWithinRange=(!state.periodStart||k>=state.periodStart.slice(0,10))&&(!state.periodEnd||k<state.periodEnd.slice(0,10));
  const isFree=trustworthy()&&isWithinRange&&!events.some(e=>!e.isOff)&&slots(k).some(t=>t.minutes>=660);
  const preview=visible.filter(e=>!e.isOff).slice(0,2).map(e=>`<span class="day-preview ${e.owner}" title="${esc(e.title)}">${esc(e.title)}</span>`).join('');
  const el=document.createElement('button');el.type='button';
  el.className='day'+(d.getUTCMonth()!==m?' outside':'')+(k===todayKey()?' today':'')+(k===state.selected?' selected':'');
  el.setAttribute('aria-label',dfDate.format(d)+(visible.length?' · '+visible.length+' Termine':''));
  el.innerHTML=`<span class="day-num">${d.getUTCDate()}</span><div class="marks">${owners.map(o=>`<span class="pill-mini ${o}"></span>`).join('')}</div><div class="day-previews">${preview}</div>${isFree&&d.getUTCMonth()===m?'<span class="free-indicator">♥ frei</span>':''}`;
  el.addEventListener('click',()=>{state.selected=k;if(d.getUTCMonth()!==m)state.view=month(d.getUTCFullYear(),d.getUTCMonth());renderMonth();renderDay()});
  grid.append(el);
 }
}
function formattedEvent(e){if(e.allDay)return 'Ganztägig';return `${dfTime.format(new Date(e.start))}–${dfTime.format(new Date(e.end))}`}
function renderDay(){
 $('#dayTitle').textContent=dfDate.format(fromKey(state.selected));
 const e=dayEvents(state.selected).filter(x=>state.filter==='all'||x.owner===state.filter);
 $('#dayEvents').innerHTML=e.length?e.map(x=>`<div class="event-line"><span class="event-track ${x.owner}"></span><div class="event-content"><strong>${esc(x.title)}</strong><div class="meta">${x.owner==='me'?'Marcel':'Visto'} · ${formattedEvent(x)} · ${esc(x.source||'Kalender')}${x.isOff?' · Frei':''}</div></div></div>`).join(''):'<p class="empty">Hier sind keine Termine erfasst.</p>';
 const available=slots(state.selected).filter(x=>x.minutes>=60);
 $('#freeToday').innerHTML=`<strong>♥ ${trustworthy()?'Gemeinsame Zeitfenster':'Mögliche Zeitfenster'}</strong>${available.length?available.map(x=>dfTime.format(x.start)+'–'+dfTime.format(x.end)).join(' · '):'Keine mindestens einstündige freie Zeit zwischen 9 und 23 Uhr.'}${trustworthy()?'':'<div class="small">Noch nicht vollständig bestätigt.</div>'}`;
}
function renderFreeList(){
 let data=[];for(let i=0;i<14;i++){let day=plusDays(fromKey(todayKey()),i),s=slots(keyOf(day)).filter(x=>x.minutes>=120);if(s.length)data.push({date:day,slot:s.sort((a,b)=>b.minutes-a.minutes)[0]})}
 $('#freeList').innerHTML=data.length?data.slice(0,8).map(x=>`<div class="free-row"><div class="free-date"><span>${esc(dfWeek.format(x.date))}</span><strong>${x.date.getUTCDate()}</strong></div><div class="free-info"><strong>${Math.floor(x.slot.minutes/60)} Std. ${Math.round(x.slot.minutes%60)} Min. ${trustworthy()?'gemeinsam':'möglich'}</strong><p>${dfTime.format(x.slot.start)}–${dfTime.format(x.slot.end)}${trustworthy()?'':' · unter Vorbehalt'}</p></div></div>`).join(''):'<p class="empty">Keine freien Zeitfenster erkannt.</p>';
}
function renderSources(){
 const today=Date.now();
 for(const [owner,target,sourceName] of [['me','#meUpcoming','iCloud'],['her','#herUpcoming','MYDUTY']]){
  const list=$(target);
  if(!state.sources[owner]?.configured && !demoMode){list.innerHTML='<p class="empty">'+sourceName+' ist noch nicht verbunden.</p>';continue}
  const events=state.events.filter(e=>e.owner===owner&&!e.isOff&&Number.isFinite(Date.parse(e.end))&&Date.parse(e.end)>=today).sort((a,b)=>Date.parse(a.start)-Date.parse(b.start));
  if(events.length===0){list.innerHTML='<p class="empty">Keine kommenden '+(owner==='me'?'Termine für Marcel':'MYDUTY-Dienste für Visto')+' in den synchronisierten Kalenderdaten.</p>';continue}
  list.innerHTML=events.slice(0,5).map(e=>`<div class="source-event"><span class="source-event-date">${esc(dfDate.format(new Date(e.start)))}</span><strong>${esc(e.title)}</strong><span class="source-event-time">${esc(formattedEvent(e))}</span></div>`).join('')+(events.length>5?`<p class="small muted">+ ${events.length-5} weitere Termine im synchronisierten Zeitraum</p>`:'');
 }
}
function renderFilters(){document.querySelectorAll('[data-filter]').forEach(btn=>{let yes=btn.dataset.filter===state.filter;btn.classList.toggle('active',yes);btn.setAttribute('aria-pressed',String(yes))})}
function render(){updateStatus();renderFilters();renderMonth();renderDay();renderFreeList();renderSources()}
function openDemo(){
 demoMode=true; passphrase=null; snapshotVersion=null;
 const today=todayKey(), tomorrow=keyOf(plusDays(fromKey(today),1)), after=keyOf(plusDays(fromKey(today),2));
 const example=(owner,title,date,start,end,overnight=false)=>({owner,title,start:local(date,start).toISOString(),end:local(overnight?keyOf(plusDays(fromKey(date),1)):date,end).toISOString(),allDay:false,source:owner==='me'?'Beispiel iCloud':'Beispiel MYDUTY',isOff:false,isNight:overnight});
 state.events=[example('me','Uni · Seminar',today,'09:00','14:00'),example('her','Frühdienst',today,'06:00','14:00'),example('me','Arbeit',tomorrow,'08:30','17:00'),example('her','Nachtdienst',tomorrow,'21:00','07:00',true),example('me','Privater Termin',after,'15:00','16:00')];
 state.sources={me:{configured:false},her:{configured:false}};state.updatedAt=null;
 $('#unlock').classList.add('hidden');$('#app').classList.remove('hidden');render();
}
document.querySelectorAll('[data-filter]').forEach(btn=>btn.addEventListener('click',()=>{state.filter=btn.dataset.filter;render()}));
$('#demoButton').addEventListener('click',openDemo);
$('#showPassphrase').addEventListener('change',()=>{$('#passphrase').type=$('#showPassphrase').checked?'text':'password'});
$('#unlockForm').addEventListener('submit',async e=>{e.preventDefault();const secret=$('#passphrase').value;const btn=$('#unlockForm button');btn.disabled=true;$('#unlockError').textContent='';try{await openWithPassword(secret)}catch(err){$('#unlockError').textContent=err.name==='OperationError'?'Dieser Schlüssel entschlüsselt die aktuelle Kalenderdatei nicht. Verwende exakt SYNC_PASSPHRASE aus GitHub. Falls du den Wert neu gesetzt hast, muss der GitHub-Workflow danach erneut erfolgreich laufen.':err.message}finally{btn.disabled=false}});
$('#lockButton').addEventListener('click',signOut);
$('#refresh').addEventListener('click',()=>refresh());
$('#previous').addEventListener('click',()=>{let {y,m}=monthParts(state.view);state.view=month(y,m-1);renderMonth()});
$('#next').addEventListener('click',()=>{let {y,m}=monthParts(state.view);state.view=month(y,m+1);renderMonth()});
$('#today').addEventListener('click',()=>{const p=monthParts(fromKey(todayKey()));state.selected=todayKey();state.view=month(p.y,p.m);render()});
try{let r=Number(localStorage.getItem('unserezeit-recovery'));if([0,6,8,10,12].includes(r)){state.recovery=r;$('#recovery').value=String(r)}}catch{}
$('#recovery').addEventListener('change',()=>{state.recovery=Number($('#recovery').value);try{localStorage.setItem('unserezeit-recovery',String(state.recovery))}catch{}render()});
window.addEventListener('focus',()=>refresh({quiet:true}));
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh({quiet:true})});
setInterval(()=>{if(!document.hidden)refresh({quiet:true})},600000);
(async()=>{try{let r=await fetch('./snapshot.enc.json',{cache:'no-store'});if(r.status===404)$('#setupHint').textContent='Noch keine Daten vorhanden: Bitte die GitHub-Secrets einrichten. Die App ist bereits veröffentlichbar.';else if(!r.ok)$('#setupHint').textContent='Daten sind derzeit nicht erreichbar.'}catch{$('#setupHint').textContent='Zum Laden der Kalenderdaten wird eine Internetverbindung benötigt.'}})();