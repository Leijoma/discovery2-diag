"""HTTP + SSE-server för dashboarden (stdlib, inga externa beroenden).

En bakgrundstråd pollar datakällan och uppdaterar ``latest``; ``/events`` strömmar
den via Server-Sent Events. ``/command`` är en hook för framtida skriv-/rensa-
kommandon (ej implementerad än).
"""
from __future__ import annotations

import json
import os
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .docs import DocLibrary
from .sources import DataSource

_DASHBOARD = Path(__file__).with_name("dashboard.html")


def _calibrate(req: "dict") -> "dict":
    """Lös skala/offset ur inskickade (rå, visat)-prover → Signal-förslag."""
    from ..sniff.calib import solve_linear, suggest_signal

    samples = req.get("samples") or []
    try:
        fit = solve_linear([(float(s[0]), float(s[1])) for s in samples])
    except (TypeError, ValueError, IndexError):
        fit = None
    if fit is None:
        return {"ok": False, "error": "need ≥2 samples with different raw values"}
    lid = req.get("lid", 0)
    if isinstance(lid, str):
        lid = int(lid, 16)
    sig = suggest_signal(
        (req.get("name") or "signal"), int(lid), int(req.get("offset", 0)),
        (req.get("kind") or "u16"), fit["scale"], fit["bias"], (req.get("unit") or ""),
    )
    return {"ok": True, "signal": sig, **fit}


_capture_lock = threading.Lock()


def _append_capture(path: "str | None", rec: "dict") -> "dict":
    """Lägg en märkt fångst {module, lid, raw, text} till en JSONL-fil (durabelt
    dataset för mappnings-analys)."""
    if not path:
        return {"ok": True, "stored": False}
    row = {"t": time.strftime("%Y-%m-%d %H:%M:%S"),
           "module": rec.get("module"), "lid": rec.get("lid"),
           "raw": rec.get("raw"), "text": rec.get("text")}
    try:
        with _capture_lock, open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"ok": True, "stored": True}


def _automap(req: "dict") -> "dict":
    """Auto-sök rätt råfält (offset/typ/skala eller byte.bit) ur klartext-avläsningar."""
    from ..sniff.automap import solve

    try:
        return solve(
            req.get("samples") or [],
            [str(x) for x in (req.get("candidate_lids") or [])],
            (req.get("name") or "signal"),
            (req.get("unit") or ""),
        )
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


_ALLOWED_MODULES = ("td5", "slabs", "airbag")


def _signal_upsert(req: "dict") -> "dict":
    """Skriv en bekräftad/kandidat-mappning till den deklarativa signalstoren
    (write-back — stänger mappnings-loopen). Ersätter localStorage för det
    värdefulla RE-arbetet: mappning gjord i bilen överlever server-side."""
    from ..signals import upsert_field

    module = (req.get("module") or "").lower()
    if module not in _ALLOWED_MODULES:
        return {"ok": False, "error": f"unknown module: {module!r}"}
    rec = req.get("record") or {}
    if not rec.get("name") or rec.get("lid") is None or rec.get("offset") is None:
        return {"ok": False, "error": "record requires at least name, lid, offset"}
    try:
        upsert_field(module, rec)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"ok": True, "module": module, "name": rec["name"]}


def _signals_list(module: str) -> "dict":
    """Läs storen för en modul (för UI: visa mappade fält + konfidens)."""
    from ..signals import load_records

    if module not in _ALLOWED_MODULES:
        return {"module": module, "signals": []}
    return {"module": module, "signals": load_records(module)}


def _fields_list(module: str) -> "dict":
    """Förväntade fält för en modul (namn/enhet/confidence) — så UI:t kan visa
    layouten med tomma platshållare även UTAN kabel/live-data."""
    from ..signals import load_signals

    store_mod = {"motor": "td5"}.get(module, module)  # UI-modulnamn → store-modul
    fields = [{"name": s.name, "unit": s.unit, "c": s.confidence}
              for s in load_signals(store_mod)]
    return {"module": module, "fields": fields}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # tyst logg
        pass

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/index.html"):
            self._html()
        elif self.path == "/events":
            self._sse()
        elif self.path == "/snapshot":
            self._json(self.server.latest)
        elif self.path.split("?")[0] == "/map":
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            mod = (q.get("module", [None])[0]) or self.server._active
            if mod in self.server._menus:
                mp = self.server._menus[mod]
            else:
                mp = self.server.source.menu_map()
            self._json({
                "module": mod, "map": mp,
                "modules": list(self.server._menus),
                "coverage": self.server.coverage(),
            })
        elif self.path.split("?")[0] == "/sniff":
            if self.server.sniffer is None:
                self._json({"module": None, "modules": [], "lids": []})
            else:
                from urllib.parse import parse_qs, urlparse
                q = parse_qs(urlparse(self.path).query)
                self._json(self.server.sniffer.snapshot(q.get("module", [None])[0]))
        elif self.path.split("?")[0] == "/signals":
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            self._json(_signals_list((q.get("module", ["td5"])[0]) or "td5"))
        elif self.path.split("?")[0] == "/fields":
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            self._json(_fields_list((q.get("module", ["motor"])[0]) or "motor"))
        elif self.path == "/community":
            c = self.server.community
            self._json(c.state() if c is not None else {"consent": None, "endpoint": None})
        elif self.path == "/docs":
            self._json({"docs": self.server.docs.index()})
        elif self.path.split("?")[0] == "/doc":
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            frag = self.server.docs.html((q.get("id", [""])[0]))
            if frag is None:
                self.send_error(404)
            else:
                self._send(frag.encode("utf-8"), "text/html; charset=utf-8")
        else:
            self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/command":
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                cmd = json.loads(raw or b"{}")
            except (ValueError, TypeError):
                cmd = {}
            # Basic-mode-skanningen är sekventiell över flera moduler (slow init
            # för airbag) → ge den rejält med tid; övriga kommandon är snabba.
            timeout = 45.0 if cmd.get("action") == "read_all_faults" else 8.0
            result = self.server.enqueue_command(cmd, timeout=timeout)
            self._json(result, code=200 if result.get("ok") else 400)
        elif self.path == "/calib":
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                req = json.loads(raw or b"{}")
            except (ValueError, TypeError):
                req = {}
            self._json(_calibrate(req))
        elif self.path == "/automap":
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                req = json.loads(raw or b"{}")
            except (ValueError, TypeError):
                req = {}
            self._json(_automap(req))
        elif self.path == "/capture":
            self._json(_append_capture(self.server.captures_path, self._body()))
        elif self.path == "/signal":
            res = _signal_upsert(self._body())
            self._json(res, code=200 if res.get("ok") else 400)
        elif self.path == "/community/consent":
            c = self.server.community
            if c is None:
                self._json({"ok": False, "error": "community disabled"}, 400)
            else:
                body = self._body()
                self._json(c.set_consent(bool(body.get("consent")), body.get("vehicle")))
        elif self.path == "/community/contribute":
            c = self.server.community
            if c is None:
                self._json({"ok": False, "error": "community disabled"}, 400)
            else:
                self._json(c.contribute(self._body()))
        else:
            self.send_error(404)

    def _body(self) -> "dict":
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw or b"{}")
        except (ValueError, TypeError):
            return {}

    # ---- svar ---------------------------------------------------------- #
    def _send(self, body: bytes, content_type: str, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self) -> None:
        self._send(_DASHBOARD.read_bytes(), "text/html; charset=utf-8")

    def _json(self, obj: "dict", code: int = 200) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _sse(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        try:
            while True:
                payload = json.dumps(self.server.latest)
                self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                self.wfile.flush()
                time.sleep(self.server.stream_interval)
        except (BrokenPipeError, ConnectionResetError):
            pass  # klienten stängde


class DiagServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        source: "DataSource | dict | None" = None,
        host: str = "0.0.0.0",
        port: int = 8080,
        poll_interval: float = 0.5,
        stream_interval: float = 0.5,
        logger=None,
        active: "str | None" = None,
        menus: "dict | None" = None,
        docs: "DocLibrary | None" = None,
        sniffer=None,
        captures_path: "str | None" = None,
        variants: "dict | None" = None,
        mode: "str | None" = None,
        scan_port: str = "auto",
        csv_dir: str = "logs",
        community=None,
        public: bool = False,
        fault_watch: bool = False,
    ) -> None:
        super().__init__((host, port), _Handler)
        self._fault_watch = fault_watch  # True = polla felkoder varje cykel (snabbt)
        self._scan_port = scan_port  # port för "läs alla felkoder" (basic mode)
        self._csv_dir = csv_dir  # var CSV-live-loggar hamnar (start/stop i UI:t)
        self._csv = None  # aktiv CsvLogger eller None
        self.community = community  # opt-in bidrags-klient (Community) eller None
        self._public = public  # publikt läge: enklare UI (döljer Karta/Fångst/Dok + ställdon)
        self._menus = menus or {}  # modul → meny-lista (Karta-fliken)
        self.docs = docs or DocLibrary()  # markdown-vy (Dokument-fliken)
        self.sniffer = sniffer  # passiv sniff-feed (Mappning-fliken), valfri
        self.captures_path = captures_path  # märkta live-fångster → JSONL
        # ``variants`` = {modul: {läge: DataSource}} → mock/live kan väljas i UI:t
        # och bytas i drift. ``source`` (enkel DataSource eller {modul: DataSource})
        # är bakåtkompatibelt (inget lägesval). Bara EN modul är aktiv åt gången
        # (K-line = delad buss) → flikbyte släpper gammal session och etablerar ny.
        if variants:
            self._variants: "dict | None" = {n: dict(v) for n, v in variants.items()}
            self._modes = sorted({m for v in self._variants.values() for m in v})
            self._mode: "str | None" = mode if mode in self._modes else self._modes[0]
            self._modules: "dict[str, DataSource]" = {
                n: (v.get(self._mode) or next(iter(v.values()))) for n, v in self._variants.items()}
        else:
            self._variants = None
            self._modes = []
            self._mode = None
            if isinstance(source, dict):
                self._modules = dict(source)
            elif source is not None:
                self._modules = {source.name: source}
            else:
                raise ValueError("DiagServer requires source or variants")
        self._active = active if active in self._modules else next(iter(self._modules))
        self.source = self._modules[self._active]
        self.poll_interval = poll_interval
        self.stream_interval = stream_interval
        self.logger = logger  # valfri SnapshotLogger → loggar varje poll till fil
        self.latest: "dict" = {
            "status": "connecting", "source": self.source.name,
            "module": self._active, "mode": self._mode, "modes": self._modes,
            "signals": {}, "faults": [], "logging": {"recording": False},
            "public": self._public, "fault_watch": self._fault_watch,
        }
        self._apply_fault_watch()  # sätt fel-pollnings-kadensen på alla källor
        for s in self._all_sources():  # live-feedback under blockande etablering
            s.on_progress = self._connect_progress
        # Anslutningslogg: hela etableringsförloppet + fel skrivs hit (och till stderr)
        # så man kan felsöka en session som "dör" strax efter uppkoppling.
        self._conn_log_path = os.path.join(self._csv_dir, "connection.log")
        self._last_conn_status: "str | None" = None
        self._last_conn_error: "str | None" = None
        self._stop = threading.Event()
        self._commands: "queue.Queue" = queue.Queue()
        self._poller = threading.Thread(target=self._poll_loop, daemon=True)

    def _conn_log(self, msg: str) -> None:
        """Skriv en tidsstämplad rad till anslutningsloggen och stderr. Får aldrig
        fälla poll-loopen — sväljer alla fel."""
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{self._active}/{self._mode}] {msg}"
        try:
            print(line, flush=True)  # → task/stderr-loggen
        except Exception:  # noqa: BLE001
            pass
        try:
            os.makedirs(os.path.dirname(self._conn_log_path), exist_ok=True)
            with open(self._conn_log_path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except Exception:  # noqa: BLE001
            pass

    def _connect_progress(self, phase: str) -> None:
        """Källorna ropar hit under den blockande etableringen (i pollertråden).
        Vi uppdaterar ``self.latest`` direkt så SSE-tråden pushar fasen live till
        webläsaren medan poll fortfarande blockerar. Bara meningsfullt medan vi
        faktiskt försöker koppla upp — poll skriver över med färsk snapshot sen."""
        self._conn_log(f"establish: {phase}")
        self.latest = {
            **self.latest,
            "status": "connecting",
            "module": self._active,
            "source": self.source.name,
            "connect_phase": phase,
        }

    def _all_sources(self) -> list:
        if self._variants:
            return [s for v in self._variants.values() for s in v.values()]
        return list(self._modules.values())

    def _apply_fault_watch(self) -> None:
        """Sätt fel-pollnings-kadensen på alla källor: 1 = varje cykel (~0,5 s,
        fångar intermittenta fel), annars var 10:e (~5 s, sparar busstrafik)."""
        every = 1 if self._fault_watch else 10
        for s in self._all_sources():
            if hasattr(s, "fault_every"):
                s.fault_every = every

    def set_fault_watch(self, on: bool) -> "dict":
        """Slå på/av snabb fel-pollning (för att fånga t.ex. tre-amigos i stunden)."""
        self._fault_watch = bool(on)
        self._apply_fault_watch()
        return {"ok": True, "fault_watch": self._fault_watch}

    def enqueue_command(self, cmd: "dict", timeout: float = 8.0) -> "dict":
        """Köa ett skrivkommando till pollertråden och vänta på resultatet.

        Serialiseras med pollningen så K-line-åtkomsten aldrig krockar."""
        holder = {"result": None, "event": threading.Event()}
        self._commands.put((cmd, holder))
        if holder["event"].wait(timeout):
            return holder["result"]
        return {"ok": False, "error": "timeout — no response from the diagnostic layer"}

    def handle_error(self, request, client_address) -> None:
        """Tysta ofarliga klient-frånkopplingar (webbläsaren stänger fetch/SSE)."""
        import sys
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, BrokenPipeError, ConnectionAbortedError)):
            return
        super().handle_error(request, client_address)

    def modules(self) -> "list[str]":
        return list(self._modules)

    def coverage(self) -> "dict":
        """Täckning per modul: {modul: {ok, maybe, total}} — driver Karta-pickern."""
        cov: "dict[str, dict]" = {}
        for name, menu in self._menus.items():
            ok = mb = tot = 0
            for group in menu:
                for item in group.get("items", []):
                    tot += 1
                    status = item.get("status")
                    if status == "ok":
                        ok += 1
                    elif status == "maybe":
                        mb += 1
            cov[name] = {"ok": ok, "maybe": mb, "total": tot}
        return cov

    def _select(self, name: "str | None") -> "dict":
        """Byt aktiv modul: släpp gamla sessionen, aktivera den nya (etableras
        lazily vid nästa poll). K-line är en delad buss → bara en session åt gången."""
        if name not in self._modules:
            return {"ok": False, "error": f"unknown module: {name}"}
        if name != self._active:
            try:
                self.source.disconnect()  # släpp K-line-porten/sessionen
            except Exception:  # noqa: BLE001
                pass
            self._active = name
            self.source = self._modules[name]
            # bevara public/fault_watch/logging/modes — annars tappar UI:t public-läget
            self.latest = {**self.latest, "status": "connecting", "source": self.source.name,
                           "module": name, "signals": {}, "faults": [], "connect_phase": None,
                           "error": ""}
        return {"ok": True, "message": f"module: {name}", "module": name}

    def _set_mode(self, mode: "str | None") -> "dict":
        """Växla datakälla mock↔live i drift (utan omstart). Släpper aktiv session
        och pekar om alla moduler till det valda lägets variant."""
        if not self._variants or mode not in self._modes:
            return {"ok": False, "error": f"unknown mode: {mode}"}
        if mode != self._mode:
            try:
                self.source.disconnect()  # släpp ev. K-line-session före byte
            except Exception:  # noqa: BLE001
                pass
            self._mode = mode
            self._modules = {n: (v.get(mode) or next(iter(v.values())))
                             for n, v in self._variants.items()}
            self.source = self._modules[self._active]
            self.latest = {**self.latest, "status": "connecting", "source": self.source.name,
                           "module": self._active, "mode": mode, "signals": {}, "faults": [],
                           "connect_phase": None, "error": ""}
        return {"ok": True, "message": f"mode: {mode}", "mode": mode}

    def _read_all_faults(self) -> "dict":
        """Basic mode: läs felkoder från alla moduler sekventiellt. Släpper den
        aktiva sessionen först (frigör K-line-porten), skannar, låter sedan
        normal pollning återansluta. Körs i pollertråden → serialiserat med bussen."""
        try:
            self.source.disconnect()  # frigör porten före sekvensskanning
        except Exception:  # noqa: BLE001
            pass
        from ..faultscan import read_all
        try:
            report = read_all(self._mode or "mock", self._scan_port)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return {"ok": True, "mode": self._mode or "mock", "report": report}

    def start_csv(self, path: "str | None" = None) -> "dict":
        """Börja logga live-data till en CSV-fil (för användaren — följa temp m.m.).
        Loggar den AKTIVA modulens signaler, en rad per poll. Idempotent."""
        from .logger import CsvLogger
        if self._csv is not None:
            return {"ok": True, "file": os.path.basename(self._csv.path),
                    "message": "already recording"}
        if path is None:
            path = os.path.join(self._csv_dir, f"livedata-{time.strftime('%Y%m%d-%H%M%S')}.csv")
        self._csv = CsvLogger(path)
        return {"ok": True, "file": os.path.basename(path), "path": path, "message": "recording"}

    def stop_csv(self) -> "dict":
        """Stoppa CSV-loggningen. Returnerar filnamn + antal rader."""
        if self._csv is None:
            return {"ok": True, "message": "not recording", "rows": 0}
        rows, fname = self._csv.rows, os.path.basename(self._csv.path)
        self._csv = None
        return {"ok": True, "file": fname, "rows": rows, "message": "stopped"}

    def _drain_commands(self) -> None:
        while True:
            try:
                cmd, holder = self._commands.get_nowait()
            except queue.Empty:
                return
            action = cmd.get("action", "")
            try:
                if action == "select_module":
                    params = cmd.get("params") or {}
                    holder["result"] = self._select(params.get("module") or cmd.get("module"))
                elif action == "set_mode":
                    params = cmd.get("params") or {}
                    holder["result"] = self._set_mode(params.get("mode") or cmd.get("mode"))
                elif action == "read_all_faults":
                    holder["result"] = self._read_all_faults()
                elif action == "start_csv":
                    holder["result"] = self.start_csv()
                elif action == "stop_csv":
                    holder["result"] = self.stop_csv()
                elif action == "set_fault_watch":
                    holder["result"] = self.set_fault_watch((cmd.get("params") or {}).get("on"))
                else:
                    holder["result"] = self.source.command(action, cmd.get("params"))
            except Exception as exc:  # noqa: BLE001
                holder["result"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            holder["event"].set()

    def _log_conn_transition(self, snap: "dict") -> None:
        """Logga bara när status faktiskt ändras (connected↔error) eller när
        feltexten ändras — annars skulle en tappad kabel spamma varje ~0,5 s.
        Mock-källor (alltid connected utan riktig session) loggas inte."""
        status = snap.get("status")
        if self._mode == "mock" or type(self.source).__name__.startswith("Mock"):
            return  # mock är alltid "connected" utan riktig session → inget att logga
        err = snap.get("error") or ""
        if status == self._last_conn_status and err == self._last_conn_error:
            return
        if status == "connected":
            n = len(snap.get("signals") or {})
            self._conn_log(f"CONNECTED — {n} signaler, {len(snap.get('faults') or [])} felkoder")
        elif status == "error":
            self._conn_log(f"ERROR — {err}")
        self._last_conn_status = status
        self._last_conn_error = err

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            self._drain_commands()  # skrivningar först, serialiserat med poll
            active = self._active
            try:
                snap = self.source.poll()
            except Exception as exc:  # noqa: BLE001
                snap = {
                    "status": "error", "source": self.source.name,
                    "signals": {}, "faults": [], "error": f"{type(exc).__name__}: {exc}",
                }
            snap["module"] = active  # vilken flik datan hör till
            snap["mode"] = self._mode  # aktivt datakällsläge (mock/live)
            snap["modes"] = self._modes  # valbara lägen (för UI-toggeln)
            snap["logging"] = self._csv.status() if self._csv is not None else {"recording": False}
            snap["public"] = self._public  # UI förenklas i publikt läge
            snap["fault_watch"] = self._fault_watch  # snabb fel-pollning på/av
            self._log_conn_transition(snap)  # logga connected/error-övergångar
            self.latest = snap
            if self.logger is not None:
                try:
                    self.logger.log(self.latest)
                except Exception:  # noqa: BLE001 — loggfel får aldrig fälla poll-loopen
                    pass
            if self._csv is not None:
                try:
                    self._csv.log(self.latest)
                except Exception:  # noqa: BLE001 — CSV-fel får aldrig fälla poll-loopen
                    pass
            self._stop.wait(self.poll_interval)

    def start_polling(self) -> None:
        if not self._poller.is_alive():
            self._poller.start()

    def stop(self) -> None:
        self._stop.set()

    def serve(self) -> None:
        self.start_polling()
        if self.sniffer is not None:
            self.sniffer.start()
        try:
            self.serve_forever()
        finally:
            self.stop()
