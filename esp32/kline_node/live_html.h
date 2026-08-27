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
.btn{min-height:52px;padding:0 26px;border:1px solid var(--bd);border-radius:12px;background:var(--surface);color:var(--fg);font:inherit;font-size:15px;font-weight:700;cursor:pointer;display:flex;align-items:center;justify-content:center}
.btn.accent{border-color:var(--accent);background:var(--accent);color:var(--on)}
.sheet{position:fixed;inset:0;background:#000a;display:flex;align-items:flex-end;justify-content:center;z-index:9}
.panel{width:100%;max-width:900px;background:var(--surface);border-radius:18px 18px 0 0;padding:18px 16px calc(18px + env(safe-area-inset-bottom));display:flex;flex-direction:column;gap:12px}
.panel h3{margin:0;font-size:16px;font-weight:800}
.foot{color:var(--fg3);font-size:11px;padding:2px 2px 0;text-wrap:pretty}
</style></head><body>
<div class=app>
 <header><span class=dot id=dot></span>
  <div><div class=htitle>Discovery 2 · live</div><div class=hsub id=sub>connecting…</div></div>
  <span class=spacer></span>
  <button class=chip onclick=openSettings()>&#9881; Settings</button></header>
 <main id=main></main>
</div>
<div id=sheet></div>
<script>
const $=s=>document.querySelector(s);
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
 const s=d.signals||{};
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
async function mute(){closeSettings();await hit('/log?on=0');setTimeout(tick,200);}
async function unmute(){await hit('/log?on=1');setTimeout(tick,200);}
async function cable(){closeSettings();await hit('/bridge?on=1');setTimeout(tick,200);}
async function backToLive(){await hit('/bridge?on=0');setTimeout(tick,200);}
async function tick(){
 let d;try{d=await(await fetch('/data')).json();}catch(e){$('#dot').style.background='var(--red)';$('#sub').textContent='no connection';return;}
 const live=d.session&&d.age_ms<3000;
 $('#dot').style.background=d.bridge?'var(--blue)':(!d.logging?'var(--yellow)':(live?'var(--green)':'var(--yellow)'));
 $('#sub').textContent=d.bridge?'cable mode':(!d.logging?'muted':((d.session?'live · '+(d.age_ms/1000).toFixed(0)+'s':'no session')+' · '+d.rssi+' dBm'));
 if(d.bridge){closeSettings();return renderState('Cable mode','The node is acting as a USB K-line cable for the diagnostic tool. Live logging is paused.','backToLive()','Back to live mode');}
 if(!d.logging){closeSettings();return renderState('Muted','Polling is stopped and the K-line bus is free for another tool.','unmute()','Unmute');}
 renderLive(d);
}
setInterval(tick,1000);tick();
</script></body></html>
)HTML";
