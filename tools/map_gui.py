"""Web GUI for the differential input mapper — a live bit-matrix you click to label.

Host-driven (per references/input_mapper_design.md): the host holds the module session and serves
a page showing every polled bit as a red/green square. Toggle a physical input (open a door, turn
the key) and the bit that moves lights up — click it, name it (with documented-name suggestions),
and it's written to the signal store as `kandidat`. Read-only: only `21 xx` reads, never a write.

    PYTHONPATH=src python3 tools/map_gui.py bcu /dev/cu.usbserial-0001 --esp
    PYTHONPATH=src python3 tools/map_gui.py bcu --mock          # offline, no car
    # then open http://localhost:8090/  (also reachable from a phone on the same network)
"""
import argparse
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_TOOLS, "..", "src"))
sys.path.insert(0, _TOOLS)

import map_inputs as mi  # noqa: E402  (pure logic + _establish + _DEFAULT_LIDS)
from d2diag.signals import load_records, remove_field, upsert_field  # noqa: E402

# Documented input-name suggestions for the click-to-label datalist (valeo_bcu_capabilities.md).
_SUGGESTIONS = {
    "bcu": ["passenger door", "driver door", "bonnet", "key lock", "key unlock", "CDL lock",
            "CDL unlock", "inertia switch", "ignition key inserted", "transfer box neutral",
            "reverse switch", "ignition pos 1", "ignition pos 2", "ignition pos 3", "park/neutral"],
    "td5": ["brake", "clutch", "A/C request", "cruise"],
    "slabs": ["any door", "neutral", "low range", "diff lock", "reverse", "HDC", "shuttle"],
}


class FakeMapSession:
    """Offline stand-in: static switch bits + one noisy counter byte (exercises the mask) +
    a toggleable 'door' bit at 21 D8 byte0 bit3 (flip it via POST /sim)."""

    def __init__(self):
        self._frame = {"20": bytearray(b"\x01\x11\x21\x00"),
                       "2c": bytearray(b"\x71\x71\xff\xff"),
                       "d8": bytearray(b"\x00\x00\xeb\xdf")}
        self._counter = 0

    def read_block(self, lids):
        self._counter = (self._counter + 1) & 0xFF
        out = {}
        for lid in lids:
            h = f"{lid:02x}"
            if h in self._frame:
                out[h] = bytes(self._frame[h])
        if "d8" in out:                                  # inject a self-changing counter → masked
            d = bytearray(out["d8"]); d[1] = self._counter; out["d8"] = bytes(d)
        return out

    def toggle(self, lid, off, bit):
        if lid in self._frame and off < len(self._frame[lid]):
            self._frame[lid][off] ^= (1 << bit)

    def open(self): pass
    def establish(self): pass
    def close(self): pass


class Mapper:
    def __init__(self, session, module, lids, period=0.4, baseline_s=3.0):
        self.session, self.module, self.lids = session, module, lids
        self.period, self.baseline_s = period, baseline_s
        self.lock = threading.Lock()
        self.frame, self.ref, self.mask = {}, {}, set()
        self.baselining, self.status = True, "connecting"
        self._samples, self._until, self._stop = [], None, False

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def rebaseline(self):
        with self.lock:
            self.baselining, self._samples, self._until = True, [], None

    def _loop(self):
        fails = 0
        while not self._stop:
            try:
                fr = self.session.read_block(self.lids)
            except Exception:  # noqa: BLE001
                fr = {}
            if not fr:                                  # every LID failed → session likely gone
                fails += 1
                if fails >= 5:                          # ~2 s of nothing → re-establish and carry on
                    with self.lock:
                        self.status = "reconnecting…"
                    try:
                        self.session.establish()
                        fails = 0
                        with self.lock:
                            self.status = "connected"
                    except Exception as exc:  # noqa: BLE001
                        with self.lock:
                            self.status = f"reconnect failed: {exc}"
                        time.sleep(2.0)
                else:
                    with self.lock:
                        self.status = "no data"
                    time.sleep(self.period)
                continue
            fails = 0
            now = time.monotonic()
            with self.lock:
                self.frame, self.status = fr, "connected"
                if self.baselining:
                    if self._until is None:
                        self._until = now + self.baseline_s
                    self._samples.append(fr)
                    if now >= self._until:
                        self.mask = mi.volatile_bits(self._samples)
                        self.ref = mi.stable_bits(self._samples, self.mask)
                        self.baselining = False
            time.sleep(self.period)

    def _labels(self):
        out = {}
        for r in load_records(self.module):
            if r.get("kind") == "bit":
                out[f"{int(str(r['lid']), 16):02x}:{int(r['offset'])}:{int(r['bit'])}"] = r["name"]
        return out

    def state(self):
        with self.lock:
            return {"module": self.module, "status": self.status, "baselining": self.baselining,
                    "rows": mi.build_matrix(self.frame, self.ref, self.mask),
                    "labels": self._labels(), "suggestions": _SUGGESTIONS.get(self.module, [])}


PAGE = r"""<!doctype html><html data-theme=dark><head>
<meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>Input mapper</title>
<style>
:root{--bg:#1b1b1b;--surface:#262626;--fg:#fafafa;--fg2:#a3a3a3;--border:#ffffff1a;--bd:#525252;
--green:#2c8a4a;--red:#c0392b;--grey:#3a3a3a;--flash:#ffd23f;--accent:#ebebeb;--on:#171717}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font-family:Figtree,system-ui,sans-serif;font-variant-numeric:tabular-nums}
header{display:flex;align-items:center;gap:12px;padding:10px 16px;background:var(--surface);border-bottom:1px solid var(--border);position:sticky;top:0}
h1{font-size:15px;margin:0;font-weight:800}.sub{font-size:12px;color:var(--fg2)}
.btn{margin-left:auto;min-height:36px;padding:0 14px;border:1px solid var(--bd);border-radius:9px;background:var(--surface);color:var(--fg);font:inherit;font-weight:700;cursor:pointer}
#banner{margin:12px 16px 0;padding:10px 14px;border-radius:10px;background:#3a3410;color:var(--flash);font-weight:700;font-size:13px}
table{border-collapse:separate;border-spacing:6px;margin:12px}
td.lbl{font-size:13px;color:var(--fg2);white-space:nowrap;text-align:right;padding-right:6px}
.cell{width:34px;height:34px;border-radius:7px;display:flex;align-items:center;justify-content:center;
font-size:12px;font-weight:700;cursor:pointer;border:2px solid transparent;position:relative}
.v0{background:var(--green)}.v1{background:var(--red)}.masked{background:var(--grey);color:#666;cursor:default}
.changed{border-color:var(--flash);box-shadow:0 0 8px var(--flash)}
.named::after{content:'';position:absolute;bottom:2px;width:5px;height:5px;border-radius:50%;background:#fff}
#tip{font-size:12px;color:var(--fg2);margin:0 16px 16px}
#labeler{position:fixed;inset:0;background:#000a;display:none;align-items:center;justify-content:center}
#labeler .box{background:var(--surface);border-radius:14px;padding:16px;width:min(92vw,360px);display:flex;flex-direction:column;gap:10px}
#labeler input{min-height:44px;padding:0 12px;border-radius:9px;border:1px solid var(--bd);background:var(--bg);color:var(--fg);font:inherit}
#labeler .row{display:flex;gap:8px}#labeler button{flex:1;min-height:44px;border-radius:9px;border:1px solid var(--bd);background:var(--surface);color:var(--fg);font:inherit;font-weight:700}
#labeler button.save{background:var(--accent);color:var(--on);border-color:var(--accent)}
</style></head><body>
<header><div><h1>Input mapper</h1><div class=sub id=sub>…</div></div>
<button class=btn onclick=rebaseline()>Re-baseline</button></header>
<div id=banner style=display:none></div>
<div id=grid></div>
<p id=tip>Green = 0, red = 1, grey = masked noise. A bit that differs from the baseline glows —
toggle an input, then click the glowing square to name it.</p>
<div id=labeler><div class=box><b id=labtitle></b>
<div class=sub id=labcur></div>
<input id=labname list=names placeholder="name this input…" autocomplete=off>
<datalist id=names></datalist>
<div class=row><button onclick=closeLab()>Cancel</button><button onclick=clearLab()>Clear</button><button class=save onclick=saveLab()>Save</button></div>
</div></div>
<script>
let cur=null, LABELS={};
async function tick(){
 let d;try{d=await(await fetch('/state')).json();}catch(e){document.getElementById('sub').textContent='no connection';return;}
 LABELS=d.labels||{};
 document.getElementById('sub').textContent=d.module.toUpperCase()+' · '+d.status;
 const b=document.getElementById('banner');
 if(d.baselining){b.style.display='block';b.textContent='Baselining — leave everything at rest…';}
 else b.style.display='none';
 document.getElementById('names').innerHTML=(d.suggestions||[]).map(s=>`<option value="${s}">`).join('');
 let html='<table>';
 for(const r of d.rows){
  html+=`<tr><td class=lbl>21 ${r.lid.toUpperCase()} · b${r.off}</td>`;
  r.cells.forEach((c,bit)=>{
   const key=`${r.lid}:${r.off}:${bit}`;const named=d.labels[key];
   let cls='cell '+(c.masked?'masked':('v'+c.v))+(c.changed?' changed':'')+(named?' named':'');
   const t=named?` title="${named}"`:'';
   html+=`<td><div class="${cls}"${t} onclick="click_('${r.lid}',${r.off},${bit},${c.masked})">${c.masked?'·':c.v}</div></td>`;
  });
  html+='</tr>';
 }
 document.getElementById('grid').innerHTML=html+'</table>';
}
function click_(lid,off,bit,masked){ if(masked)return; cur={lid,off,bit};
 const name=LABELS[`${lid}:${off}:${bit}`]||'';
 document.getElementById('labtitle').textContent=`21 ${lid.toUpperCase()} byte${off} bit${bit}`;
 document.getElementById('labcur').textContent=name?('Currently: '+name):'Unassigned';
 document.getElementById('labname').value=name;
 document.getElementById('labeler').style.display='flex';
 const inp=document.getElementById('labname'); inp.focus(); inp.select(); }
function closeLab(){document.getElementById('labeler').style.display='none';}
async function post_(name){ if(!cur)return; await fetch('/label',{method:'POST',body:JSON.stringify({...cur,name})}); closeLab(); tick(); }
function saveLab(){post_(document.getElementById('labname').value.trim());}
function clearLab(){post_('');}
async function rebaseline(){await fetch('/rebaseline',{method:'POST'});tick();}
document.getElementById('labname').addEventListener('keydown',e=>{if(e.key==='Enter')saveLab();});
setInterval(tick,400);tick();
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, code, body, ctype="application/json"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        m = self.server.mapper
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif self.path == "/state":
            self._send(200, json.dumps(m.state()))
        else:
            self._send(404, "{}")

    def do_POST(self):
        m = self.server.mapper
        if self.path == "/label":
            d = self._body()
            lid, off, bit = d["lid"], int(d["off"]), int(d["bit"])
            name = (d.get("name") or "").strip()
            remove_field(m.module, lid, off, bit)        # drop any existing assignment on this bit
            if name:                                     # empty name = clear (remove only)
                upsert_field(m.module, {
                    "name": name, "lid": lid, "offset": off, "kind": "bit", "bit": bit,
                    "scale": 1.0, "bias": 0.0, "unit": "", "confidence": "kandidat",
                    "states": {"0": "off", "1": "on"},
                    "source": f"differential map (GUI) — {m.module} 21 {lid.upper()} b{off}.{bit}",
                })
            self._send(200, "{\"ok\":true}")
        elif self.path == "/rebaseline":
            m.rebaseline()
            self._send(200, "{\"ok\":true}")
        elif self.path == "/sim" and isinstance(m.session, FakeMapSession):
            d = self._body()
            m.session.toggle(d.get("lid", "d8"), int(d.get("off", 0)), int(d.get("bit", 3)))
            self._send(200, "{\"ok\":true}")
        else:
            self._send(404, "{}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Web GUI for the differential input mapper")
    ap.add_argument("module", choices=sorted(mi._DEFAULT_LIDS))
    ap.add_argument("port", nargs="?", help="serial port (omit with --mock)")
    ap.add_argument("--esp", action="store_true", help="talk over an ESP32 in cable mode")
    ap.add_argument("--mock", action="store_true", help="offline fake session (no car)")
    ap.add_argument("--lids", help="comma-separated hex LIDs (overrides the default set)")
    ap.add_argument("--http", type=int, default=8090, help="HTTP port (default 8090)")
    args = ap.parse_args()

    lids = ([int(x, 16) for x in args.lids.replace(" ", "").split(",")]
            if args.lids else mi._DEFAULT_LIDS[args.module])

    if args.mock:
        session = FakeMapSession()
    else:
        if not args.port:
            ap.error("a serial port is required unless --mock")
        session = mi._establish(args.module, args.port, args.esp)

    mapper = Mapper(session, args.module, lids)
    mapper.start()
    httpd = ThreadingHTTPServer(("0.0.0.0", args.http), Handler)
    httpd.mapper = mapper
    print(f"Input mapper GUI on http://localhost:{args.http}/  (module {args.module}, "
          f"{'MOCK' if args.mock else args.port})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
