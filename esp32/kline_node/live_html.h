// live_html.h — the node's live web UI as one embedded page (served at "/" and "/live").
//
// Kept in its own header ON PURPOSE: the Arduino auto-prototype generator scans the .ino
// and would turn the JavaScript `function name(){` lines inside this raw string into bogus
// C++ prototypes (it does not parse included .h files). Styled to match the Pi dashboard
// (Figtree, dark theme, drive tiles + gauges). Three states, driven by /data:
//   • live   — the driver's grid (default on startup)
//   • Muted  — a full-screen "Muted" with Unmute        (logging off = K-line bus freed)
//   • Cable  — a full-screen "Cable mode" with Back to live (node is a USB K-line cable)
// Settings (gear) holds exactly two buttons: Mute and Cable mode.
#pragma once
#include <Arduino.h>

static const char LIVE_HTML[] = R"HTML(<!doctype html><html data-theme=dark><head>
<meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>D2 live</title>
<style>
@import url("https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700;800&display=swap");
:root{--font:Figtree,-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
--bg:#1b1b1b;--surface:#262626;--card:#1b1b1b;--fg:#fafafa;--fg2:#a3a3a3;--fg3:#525252;
--border:#ffffff1a;--bd:#525252;--accent:#ebebeb;--on:#171717;
--green:#84c980;--red:#ff9e97;--yellow:#deb433;--blue:#9eb7ff;--bg-red:#ff9e973d;--bd-red:#ff6f6c}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;padding:0;background:var(--bg)}
::-webkit-scrollbar{width:0;height:0}
body{font-family:var(--font);color:var(--fg);font-size:14px;line-height:20px;font-variant-numeric:tabular-nums}
.app{display:flex;flex-direction:column;height:100vh;height:100dvh;max-width:900px;margin:0 auto;overflow:hidden}
header{display:flex;flex-shrink:0;align-items:center;gap:11px;padding:8px 16px;min-height:56px;background:var(--surface);border-bottom:1px solid var(--border)}
.dot{width:9px;height:9px;border-radius:9999px;background:var(--fg3);flex-shrink:0}
.htitle{font-size:13px;font-weight:800;letter-spacing:.2px}
.hsub{font-size:12px;color:var(--fg2)}
.spacer{flex:1}
.chip{min-height:36px;padding:0 14px;display:inline-flex;align-items:center;gap:7px;border:1px solid var(--bd);border-radius:10px;background:var(--surface);color:var(--fg);font:inherit;font-size:12px;font-weight:700;cursor:pointer}
main{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column}
.drive{width:100%;max-height:100%;margin:auto 0;min-height:0;display:grid;grid-template-columns:repeat(4,1fr);grid-auto-rows:1fr;gap:8px}
.dtile{grid-column:span 2;border:1px solid var(--border);border-radius:14px;background:var(--card);display:flex;flex-direction:column;gap:2px;padding:10px 13px;min-height:0;overflow:hidden}
.dlabel{font-size:14px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;color:var(--fg2)}
.dval{font-size:clamp(30px,11vw,58px);font-weight:800;line-height:1.02;display:flex;align-items:baseline}
.cv-num{text-align:right;min-width:2ch}
.cv-unit{font-size:.42em;color:var(--fg2);font-weight:600;margin-left:.2em;white-space:nowrap}
.dtile.gauge{grid-row:span 2;padding:8px}
.gwrap{flex:1;min-height:0;display:flex;align-items:center;justify-content:center}
.gsvg{width:100%;height:100%}
.gtrack{fill:none;stroke:var(--border);stroke-width:11;stroke-linecap:round}
.gval{fill:none;stroke:var(--blue);stroke-width:11;stroke-linecap:round;transition:stroke-dasharray .3s}
.gnum{fill:var(--fg);font-size:26px;font-weight:800;text-anchor:middle}
.gunit{fill:var(--fg2);font-size:10px;font-weight:600;text-anchor:middle;letter-spacing:.5px}
.state{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:22px;text-align:center;padding:24px}
.state .big{font-size:clamp(36px,11vw,64px);font-weight:800;letter-spacing:.5px}
.state .sub{font-size:14px;color:var(--fg2);max-width:340px;text-wrap:pretty}
.btn{min-height:52px;padding:0 26px;border:1px solid var(--bd);border-radius:12px;background:var(--surface);color:var(--fg);font:inherit;font-size:15px;font-weight:700;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:transform .05s}
.btn.accent{border-color:var(--accent);background:var(--accent);color:var(--on)}
.btn:active{transform:scale(.97);opacity:.85}
@keyframes spin{to{transform:rotate(360deg)}}
.spinner{width:38px;height:38px;border-radius:50%;border:3px solid var(--border);border-top-color:var(--accent);animation:spin .8s linear infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
.pulse{animation:pulse 1.1s ease-in-out infinite}
.sheet{position:fixed;inset:0;background:#000a;display:flex;align-items:flex-end;justify-content:center;z-index:9}
.panel{width:100%;max-width:900px;background:var(--surface);border-radius:18px 18px 0 0;padding:18px 16px calc(18px + env(safe-area-inset-bottom));display:flex;flex-direction:column;gap:12px}
.panel h3{margin:0;font-size:16px;font-weight:800}
.foot{color:var(--fg3);font-size:11px;padding:2px 2px 0;text-wrap:pretty}
</style></head><body>
<div class=app>
 <header><span class=dot id=dot></span>
  <div><div class=htitle>Discovery 2 · live</div><div class=hsub id=sub>connecting…</div></div>
  <span class=spacer></span>
  <button class=chip id=fbtn style="display:none;border-color:var(--bd-red);color:var(--red)" onclick=showFaults()>&#9888; <span id=fn>0</span></button>
  <button class=chip onclick=openSettings()>&#9881; Settings</button></header>
 <main id=main></main>
</div>
<div id=sheet></div>
<script>
const $=s=>document.querySelector(s);
// Fault codes: the ESP reports the RAW 21 3B block; the dictionary lives in the repo and is
// fetched from GitHub (the phone hotspot has data) + cached in localStorage for offline use.
let FMAP=null, FAULTS_NOW=[];
const FMAP_URL='https://raw.githubusercontent.com/Leijoma/discovery2-diag/main/src/d2diag/td5/faultmap.json';
async function loadFaultMap(){
 try{const r=await fetch(FMAP_URL);if(r.ok){FMAP=await r.json();localStorage.setItem('faultmap',JSON.stringify(FMAP));return;}}catch(e){}
 const c=localStorage.getItem('faultmap');if(c)FMAP=JSON.parse(c);   // offline → last cached map
}
function decodeFaults(hex){
 const by=(hex||'').trim()?hex.trim().split(/\s+/).map(x=>parseInt(x,16)):[];
 if(!by.length)return [];
 if(!FMAP)return by.flatMap((b,o)=>[0,1,2,3,4,5,6,7].filter(bit=>b&(1<<bit)).map(bit=>`byte${o}.bit${bit}`));
 const block=by.slice(0,FMAP.block_len),out=[],known={};
 for(const k in FMAP.bits){const p=k.split('.'),o=+p[0],bit=+p[1];known[o]=(known[o]||0)|(1<<bit);if(block[o]!==undefined&&(block[o]&(1<<bit)))out.push(FMAP.bits[k]);}
 for(let o=0;o<block.length;o++){const unk=block[o]&~(known[o]||0)&0xFF;for(let bit=0;bit<8;bit++)if(unk&(1<<bit))out.push('byte'+o+'.bit'+bit);}
 return out;
}
function showFaults(){
 const txt=FAULTS_NOW.join('\n')||'(none)';
 $('#sheet').innerHTML=`<div class=sheet onclick="if(event.target===this)closeSettings()"><div class=panel>
  <h3>Fault codes (${FAULTS_NOW.length})</h3>
  <textarea id=ftext readonly style="width:100%;min-height:180px;background:var(--bg);color:var(--fg);border:1px solid var(--bd);border-radius:9px;padding:10px;font:inherit;font-size:13px">${txt}</textarea>
  <div class=foot>${FMAP?'Decoded via faultmap.json (GitHub)':'Raw bits — fault map not loaded yet (no internet)'}.</div>
  <button class=btn onclick=copyFaults()>Copy</button>
  <button class=btn style=opacity:.7 onclick=closeSettings()>Close</button></div></div>`;
}
async function copyFaults(){const t=FAULTS_NOW.join('\n');try{await navigator.clipboard.writeText(t);}catch(e){const el=$('#ftext');if(el){el.focus();el.select();try{document.execCommand('copy');}catch(_){}}}}
// {n:key, lab, u:unit, d:decimals, div:divisor, g:[min,max] for a gauge}
const TILES=[
 {n:'speed',lab:'Speed',u:'km/h',d:0},
 {n:'rpm',lab:'Engine',u:'rpm',d:0},
 {n:'map_bar',lab:'Boost',u:'bar',d:1,g:[1.0,2.5]},
 {n:'coolant_c',lab:'Coolant',u:'°C',d:0,g:[40,120]},
 {n:'economy',lab:'Fuel',u:'L/mil',d:1,div:10},
 {n:'trip_economy',lab:'Trip',u:'L/mil',d:1,div:10},
 {n:'battery',lab:'Battery',u:'V',d:1},
 {n:'air_c',lab:'Intake',u:'°C',d:0}];
const num=(v,d)=>(v==null||isNaN(v))?'–':Number(v).toFixed(d);
function gauge(v,mn,mx,u,d){
 const r=40,C=2*Math.PI*r,arc=C*0.75;
 const f=(v==null||isNaN(v))?0:Math.max(0,Math.min(1,(v-mn)/(mx-mn)));
 return `<svg viewBox="0 0 100 100" class=gsvg>
  <circle cx=50 cy=50 r=${r} class=gtrack stroke-dasharray="${arc.toFixed(1)} ${C.toFixed(1)}" transform="rotate(135 50 50)"/>
  <circle cx=50 cy=50 r=${r} class=gval stroke-dasharray="${(arc*f).toFixed(1)} ${C.toFixed(1)}" transform="rotate(135 50 50)"/>
  <text x=50 y=54 class=gnum>${num(v,d)}</text><text x=50 y=69 class=gunit>${u}</text></svg>`;
}
function tile(t,s){
 let v=s[t.n]; if(v!=null&&t.div) v=v/t.div;
 if(t.g) return `<div class="dtile gauge"><div class=dlabel>${t.lab}</div><div class=gwrap>${gauge(v,t.g[0],t.g[1],t.u,t.d)}</div></div>`;
 return `<div class=dtile><div class=dlabel>${t.lab}</div><div class=dval><span class=cv-num>${num(v,t.d)}</span><span class=cv-unit>${t.u}</span></div></div>`;
}
function renderLive(d){
 // Stale guard: if no fresh snapshot for 5 s (session dropped / bus quiet), blank every card
 // to "–" rather than showing frozen values.
 const s=(d.age_ms<5000)?(d.signals||{}):{};
 let rows=0; for(let i=0;i<TILES.length;i+=2) rows+=TILES.slice(i,i+2).some(t=>t.g)?2:1;
 $('#main').innerHTML=`<div class=drive style="aspect-ratio:4/${rows}">${TILES.map(t=>tile(t,s)).join('')}</div>`;
}
function renderState(title,sub,action,label){
 $('#main').innerHTML=`<div class=state><div class=big>${title}</div><div class=sub>${sub}</div>
  <button class="btn accent" onclick="${action}">${label}</button></div>`;
}
function openSettings(){
 $('#sheet').innerHTML=`<div class=sheet onclick="if(event.target===this)closeSettings()"><div class=panel>
  <h3>Settings</h3>
  <button class=btn onclick=mute()>Mute</button>
  <button class=btn onclick=cable()>Cable mode</button>
  <div class=foot>Mute stops polling and frees the K-line bus. Cable mode turns the node into a USB K-line cable for the diagnostic tool.</div>
  <button class=btn style=opacity:.7 onclick=closeSettings()>Close</button></div></div>`;
}
function closeSettings(){$('#sheet').innerHTML='';}
const hit=u=>fetch(u).catch(()=>{});
// A control action shows an INSTANT transition screen (spinner), fires the request, and
// holds that screen until /data confirms the new state — the node can be mid K-line poll
// for a second or two. ACT maps each button to its endpoint + the "done" condition on /data.
const ACT={
 mute:  {u:'/log?on=0',    lbl:'Muting…',              done:d=>!d.logging},
 unmute:{u:'/log?on=1',    lbl:'Resuming…',            done:d=>d.logging&&!d.bridge},
 cable: {u:'/bridge?on=1', lbl:'Entering cable mode…', done:d=>d.bridge},
 live:  {u:'/bridge?on=0', lbl:'Returning to live…',   done:d=>!d.bridge}};
let pending=null,pendingSince=0;
function transition(lbl){closeSettings();$('#main').innerHTML=`<div class=state><div class=spinner></div><div class="big pulse" style="font-size:clamp(26px,7vw,42px)">${lbl}</div></div>`;}
function act(name){const a=ACT[name];pending=name;pendingSince=Date.now();transition(a.lbl);hit(a.u);setTimeout(tick,300);}
function mute(){act('mute')} function unmute(){act('unmute')} function cable(){act('cable')} function backToLive(){act('live')}
function header(d){
 const live=d.session&&d.age_ms<3000;
 $('#dot').style.background=pending?'var(--blue)':(d.bridge?'var(--blue)':(!d.logging?'var(--yellow)':(live?'var(--green)':'var(--yellow)')));
 $('#sub').textContent=pending?ACT[pending].lbl:(d.bridge?'cable mode':(!d.logging?'muted':((d.session?'live · '+(d.age_ms/1000).toFixed(0)+'s':'no session')+' · '+d.rssi+' dBm')));
}
async function tick(){
 let d;try{d=await(await fetch('/data')).json();}catch(e){$('#dot').style.background='var(--red)';$('#sub').textContent=pending?ACT[pending].lbl:'no connection';return;}
 header(d);
 FAULTS_NOW=decodeFaults(d.faults);
 const fb=$('#fbtn');
 if(FAULTS_NOW.length){fb.style.display='inline-flex';$('#fn').textContent=FAULTS_NOW.length;}
 else fb.style.display='none';
 if(pending){
  if(ACT[pending].done(d)) pending=null;                 // confirmed → fall through to the real state
  else if(Date.now()-pendingSince<20000) return;         // still switching → keep the transition screen
  else pending=null;                                     // gave up after 20 s → unfreeze
 }
 if(d.bridge) return renderState('Cable mode','The node is acting as a USB K-line cable for the diagnostic tool. Live logging is paused.','backToLive()','Back to live mode');
 if(!d.logging) return renderState('Muted','Polling is stopped and the K-line bus is free for another tool.','unmute()','Unmute');
 if(d.ign_cycle){$('#main').innerHTML=`<div class=state><div class="big pulse">Cycle the ignition</div><div class=sub>The ECU is holding the previous link open and won't accept a new one. Turn the key off, then back on — the node reconnects on its own. (Bus silence and reboot don't clear it on this car.)</div></div>`;return;}
 renderLive(d);
}
loadFaultMap();setInterval(tick,1000);tick();
</script></body></html>
)HTML";
