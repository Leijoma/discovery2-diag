"""HTTP + SSE server for the dashboard (stdlib, no external dependencies).

A background thread polls the data source and updates ``latest``; ``/events``
streams it via Server-Sent Events. ``/command`` is a hook for future write/clear
commands (not implemented yet).
"""
from __future__ import annotations

import base64
import hmac
import json
import os
import queue
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .docs import DocLibrary
from .sources import DataSource

_DASHBOARD = Path(__file__).with_name("dashboard.html")
_DASHBOARD_V2 = Path(__file__).with_name("dashboard_v2.html")  # new design (proof of concept)


def _calibrate(req: "dict") -> "dict":
    """Solve scale/offset from submitted (raw, displayed) samples → Signal suggestion."""
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
    """Append a labelled capture {module, lid, raw, text} to a JSONL file (durable
    dataset for mapping analysis)."""
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
    """Auto-search the right raw field (offset/type/scale or byte.bit) from plaintext readings."""
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
    """Write a confirmed/candidate mapping to the declarative signal store
    (write-back — closes the mapping loop). Replaces localStorage for the
    valuable RE work: mapping done in the car survives server-side."""
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
    """Read the store for a module (for the UI: show mapped fields + confidence)."""
    from ..signals import load_records

    if module not in _ALLOWED_MODULES:
        return {"module": module, "signals": []}
    return {"module": module, "signals": load_records(module)}


def _fields_list(module: str) -> "dict":
    """Expected fields for a module (name/unit/confidence) — so the UI can show
    the layout with empty placeholders even WITHOUT a cable/live data."""
    from ..signals import load_signals

    store_mod = {"motor": "td5"}.get(module, module)  # UI module name → store module
    fields = [{"name": s.name, "unit": s.unit, "c": s.confidence, "limits": s.limits}
              for s in load_signals(store_mod)]
    return {"module": module, "fields": fields}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # silent log
        pass

    def do_GET(self) -> None:  # noqa: N802
        # v2 is now the normal UI at "/". "/v2" is kept as an alias for old
        # bookmarks. The old v1 dashboard is the mapping/admin console and
        # lives at "/admin" behind a password (it has the Map/Capture/Docs tabs).
        if self.path in ("/", "/index.html", "/v2", "/v2.html"):
            self._send(_DASHBOARD_V2.read_bytes(), "text/html; charset=utf-8")
        elif self.path in ("/admin", "/admin.html"):
            # Same app as "/", but admin mode: the page detects /admin and shows
            # the mapping tabs. One app, one routing, one UI.
            if not self._require_admin():
                return
            self._send(_DASHBOARD_V2.read_bytes(), "text/html; charset=utf-8")
        elif self.path in ("/v1", "/v1.html"):
            if not self._require_admin():  # the old dashboard — kept as a reference
                return
            self._html()
        elif self.path == "/events":
            self._sse()
        elif self.path == "/snapshot":
            self._json(self.server.latest)
        elif self.path.split("?")[0] == "/map":
            if not self._require_admin():
                return
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
            if not self._require_admin():
                return
            if self.server.sniffer is None:
                self._json({"module": None, "modules": [], "lids": []})
            else:
                from urllib.parse import parse_qs, urlparse
                q = parse_qs(urlparse(self.path).query)
                self._json(self.server.sniffer.snapshot(q.get("module", [None])[0]))
        elif self.path.split("?")[0] == "/signals":
            if not self._require_admin():
                return
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
            if not self._require_admin():
                return
            self._json({"docs": self.server.docs.index()})
        elif self.path.split("?")[0] == "/doc":
            if not self._require_admin():
                return
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
            # The basic-mode scan is sequential over several modules (slow init
            # for airbag) → give it plenty of time; other commands are fast.
            timeout = 45.0 if cmd.get("action") == "read_all_faults" else 8.0
            result = self.server.enqueue_command(cmd, timeout=timeout)
            self._json(result, code=200 if result.get("ok") else 400)
        elif self.path == "/calib":
            if not self._require_admin():
                return
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                req = json.loads(raw or b"{}")
            except (ValueError, TypeError):
                req = {}
            self._json(_calibrate(req))
        elif self.path == "/automap":
            if not self._require_admin():
                return
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                req = json.loads(raw or b"{}")
            except (ValueError, TypeError):
                req = {}
            self._json(_automap(req))
        elif self.path == "/capture":
            if not self._require_admin():
                return
            self._json(_append_capture(self.server.captures_path, self._body()))
        elif self.path == "/signal":
            if not self._require_admin():
                return
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

    # ---- admin gate (HTTP Basic Auth) --------------------------------- #
    # Protects the mapping/dev surface (/admin + automap/capture/signal/calib/…).
    # If no password is set, admin is UNGATED (local dev, backwards-compatible) — the Pi
    # runs with --admin-password. Basic Auth over HTTP without TLS is "keep the curious
    # off the LAN", not strong crypto; no sensitive data lives behind it.
    def _admin_ok(self) -> bool:
        pw = getattr(self.server, "_admin_password", None)
        if not pw:
            return True
        hdr = self.headers.get("Authorization", "")
        if hdr.startswith("Basic "):
            try:
                decoded = base64.b64decode(hdr[6:]).decode("utf-8", "replace")
            except Exception:  # noqa: BLE001
                decoded = ""
            supplied = decoded.partition(":")[2]  # optional username, only the password counts
            if hmac.compare_digest(supplied, pw):
                return True
        return False

    def _require_admin(self) -> bool:
        """True if the call may proceed; otherwise a 401 is sent and False returned."""
        if self._admin_ok():
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="d2diag admin"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    # ---- responses ----------------------------------------------------- #
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
            pass  # the client closed


# Commands that do NOT touch K-line and may therefore run straight on the HTTP thread.
# Queuing them behind the poller thread means they have to wait out an ongoing
# establishment (SLABS: bus-idle + 3 attempts × 5 s retry ≈ 20 s) and then time out
# at 8 s in the UI — even though they later succeed once the queue drains. They only
# touch the server's own state (CsvLogger object, fault_every attribute).
_INLINE_COMMANDS = frozenset({"start_csv", "stop_csv", "set_fault_watch", "shutdown"})


class ConnectAborted(Exception):
    """Establishment aborted because a command is waiting (e.g. module switch)."""


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
        admin_password: "str | None" = None,
        allow_shutdown: bool = False,
    ) -> None:
        super().__init__((host, port), _Handler)
        # None/"" = admin ungated (local dev). Set = /admin + mapping endpoints
        # behind HTTP Basic Auth. See _Handler._admin_ok.
        self._admin_password = admin_password or None
        self._fault_watch = fault_watch  # True = poll fault codes every cycle (fast)
        self._scan_port = scan_port  # port for "read all fault codes" (basic mode)
        self._csv_dir = csv_dir  # where CSV live logs go (start/stop in the UI)
        self._csv = None  # active CsvLogger or None
        self._csv_lock = threading.Lock()  # start/stop on the HTTP thread, log() in the poller
        self.community = community  # opt-in contribution client (Community) or None
        self._public = public  # public mode: simpler UI (hides Map/Capture/Docs + actuators)
        # allow_shutdown: expose a "Shut down Pi" button in Settings. Off by default so
        # dev on a laptop can never power off the host; the Pi's systemd unit passes
        # --allow-shutdown. Stopgap until proper power control exists.
        self._allow_shutdown = bool(allow_shutdown)
        self._menus = menus or {}  # module → menu list (Map tab)
        self.docs = docs or DocLibrary()  # markdown view (Documents tab)
        self.sniffer = sniffer  # passive sniff feed (Mapping tab), optional
        self.captures_path = captures_path  # labelled live captures → JSONL
        # ``variants`` = {module: {mode: DataSource}} → mock/live can be chosen in the UI
        # and switched at runtime. ``source`` (a single DataSource or {module: DataSource})
        # is backwards-compatible (no mode selection). Only ONE module is active at a time
        # (K-line = shared bus) → a tab switch releases the old session and establishes a new one.
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
        self.logger = logger  # optional SnapshotLogger → logs every poll to file
        self.latest: "dict" = {
            "status": "connecting", "source": self.source.name,
            "module": self._active, "mode": self._mode, "modes": self._modes,
            "signals": {}, "faults": [], "logging": {"recording": False},
            "public": self._public, "fault_watch": self._fault_watch,
            "allow_shutdown": self._allow_shutdown,
        }
        self._apply_fault_watch()  # set the fault-polling cadence on all sources
        for s in self._all_sources():  # live feedback during blocking establishment
            s.on_progress = self._connect_progress
            s.on_sleep = self._connect_sleep
        # Connection log: the whole establishment sequence + errors are written here (and to stderr)
        # so you can debug a session that "dies" shortly after connecting.
        self._conn_log_path = os.path.join(self._csv_dir, "connection.log")
        self._last_conn_status: "tuple | None" = None  # (module, status) — see _log_conn_transition
        self._last_conn_error: "str | None" = None
        self._last_phase_logged: "str | None" = None  # dedupe of identical progress lines
        # Last known engine context (rpm/speed/battery) from TD5. K-line is a shared
        # bus so we can't read the engine while SLABS is active — but a SLABS attempt
        # is almost always preceded by a TD5 session, and then the values are seconds old.
        # Without this you can't tell afterwards whether a silent init attempt was made
        # while moving (SLABS refuses comms >8–20 km/h) or at idle.
        self._engine: "dict | None" = None
        self._stop = threading.Event()
        self._commands: "queue.Queue" = queue.Queue()
        self._poller = threading.Thread(target=self._poll_loop, daemon=True)

    def _remember_engine(self, snap: "dict") -> None:
        """Save rpm/speed/battery from a TD5 snapshot (for _engine_note)."""
        sig = snap.get("signals") or {}
        if not {"rpm", "battery"} <= set(sig):
            return
        self._engine = {
            "rpm": sig["rpm"].get("v"), "battery": sig["battery"].get("v"),
            "speed": (sig.get("speed") or {}).get("v"), "t": time.monotonic(),
        }

    def _engine_note(self) -> str:
        """`· motor: rpm 761, 0 km/h, 13.9 V (12s ago)` — empty if we know nothing."""
        e = self._engine
        if not e:
            return ""
        age = time.monotonic() - e["t"]
        if age > 600:  # older than 10 min says nothing about the present
            return ""
        speed = "?" if e["speed"] is None else f"{e['speed']:.0f} km/h"
        return f" · motor: rpm {e['rpm']:.0f}, {speed}, {e['battery']:.1f} V ({age:.0f}s ago)"

    def _connect_sleep(self, seconds: float) -> None:
        """Sleep used by the establishment — interrupted by a queued command.

        The SLABS quiet period is 28 s and a full establishment can take ~90 s. Without
        this the poller thread sleeps while a module switch sits in the queue, and the UI
        times out even though the command is valid. We sleep in slices and raise
        :class:`ConnectAborted` as soon as anything is queued — the establishment is
        aborted, the queue drains, and the next poll restarts against the right module.
        """
        deadline = time.monotonic() + seconds
        while True:
            if not self._commands.empty():
                raise ConnectAborted("aborted by a queued command")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            self._stop.wait(min(0.2, remaining))
            if self._stop.is_set():
                return

    def _conn_log(self, msg: str, module: "str | None" = None) -> None:
        """Write a timestamped line to the connection log and stderr. Must never
        fell the poll loop — swallows all errors.

        ``module`` stamps the line with the module the snapshot concerns; without it
        the currently active one is used. The difference matters mid module-switch,
        where a snapshot from the old module would otherwise be labelled with the new.
        """
        line = (f"{time.strftime('%Y-%m-%d %H:%M:%S')} "
                f"[{module or self._active}/{self._mode}] {msg}")
        try:
            print(line, flush=True)  # → the task/stderr log
        except Exception:  # noqa: BLE001
            pass
        try:
            os.makedirs(os.path.dirname(self._conn_log_path), exist_ok=True)
            with open(self._conn_log_path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except Exception:  # noqa: BLE001
            pass

    def _connect_progress(self, phase: str) -> None:
        """The sources call in here during the blocking establishment (on the poller
        thread). We update ``self.latest`` immediately so the SSE thread pushes the
        phase live to the browser while poll is still blocking. Only meaningful while
        we're actually trying to connect — poll overwrites with a fresh snapshot later.

        Identical lines in a row are logged ONCE: without a cable the reconnect shouts
        "opening the cable" twice a second forever (1.9 MB of noise over one evening
        2026-08-18), which drowns out the lines you actually debug with.
        """
        if phase != self._last_phase_logged:
            ctx = self._engine_note() if phase.startswith("sending init") else ""
            self._conn_log(f"establish: {phase}{ctx}")
            self._last_phase_logged = phase
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
        """Set the fault-polling cadence on all sources: 1 = every cycle (~0.5 s,
        catches intermittent faults), otherwise every 10th (~5 s, saves bus traffic)."""
        every = 1 if self._fault_watch else 10
        for s in self._all_sources():
            if hasattr(s, "fault_every"):
                s.fault_every = every

    def set_fault_watch(self, on: bool) -> "dict":
        """Turn fast fault-polling on/off (to catch e.g. three-amigos in the moment)."""
        self._fault_watch = bool(on)
        self._apply_fault_watch()
        return {"ok": True, "fault_watch": self._fault_watch}

    def _run_inline(self, action: str, params: "dict") -> "dict":
        """Run a command that doesn't touch K-line (see :data:`_INLINE_COMMANDS`)."""
        if action == "start_csv":
            return self.start_csv()
        if action == "stop_csv":
            return self.stop_csv()
        if action == "set_fault_watch":
            return self.set_fault_watch(params.get("on"))
        if action == "shutdown":
            return self.shutdown_host(params)
        return {"ok": False, "error": f"unknown command: {action}"}

    def _spawn_poweroff(self) -> None:
        """Fire the OS poweroff after a short delay so the HTTP reply flushes to the
        browser before the box goes down. Isolated so tests can stub it. ``sudo -n``
        fails fast instead of hanging if passwordless sudo is not configured."""
        def _go() -> None:
            time.sleep(1.0)
            try:
                subprocess.Popen(["sudo", "-n", "shutdown", "-h", "now"])
            except Exception:  # noqa: BLE001 — nothing to report to; the caller already replied
                pass
        threading.Thread(target=_go, daemon=True).start()

    def shutdown_host(self, params: "dict | None" = None) -> "dict":
        """Power off the host (the Pi in the car). Guarded by --allow-shutdown so dev
        on a laptop can never trigger it. A stopgap until proper power control exists."""
        if not self._allow_shutdown:
            return {"ok": False, "error": "shutdown is not enabled on this host"}
        self._spawn_poweroff()
        return {"ok": True, "shutting_down": True}

    def enqueue_command(self, cmd: "dict", timeout: float = 8.0) -> "dict":
        """Queue a write command to the poller thread and wait for the result.

        Serialized with the polling so K-line access never collides."""
        action = cmd.get("action", "")
        if action in _INLINE_COMMANDS:
            # Immediate reply — must not get stuck behind an ongoing connection in the poller.
            try:
                return self._run_inline(action, cmd.get("params") or {})
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        holder = {"result": None, "event": threading.Event()}
        self._commands.put((cmd, holder))
        if holder["event"].wait(timeout):
            return holder["result"]
        return {"ok": False, "error": "timeout — no response from the diagnostic layer"}

    def handle_error(self, request, client_address) -> None:
        """Silence harmless client disconnects (the browser closing fetch/SSE)."""
        import sys
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, BrokenPipeError, ConnectionAbortedError)):
            return
        super().handle_error(request, client_address)

    def modules(self) -> "list[str]":
        return list(self._modules)

    def coverage(self) -> "dict":
        """Coverage per module: {module: {ok, maybe, total}} — drives the Map picker."""
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
        """Switch the active module: release the old session, activate the new one
        (established lazily on the next poll). K-line is a shared bus → only one session at a time."""
        if name not in self._modules:
            return {"ok": False, "error": f"unknown module: {name}"}
        if name != self._active:
            try:
                self.source.disconnect()  # release the K-line port/session
            except Exception:  # noqa: BLE001
                pass
            self._active = name
            self.source = self._modules[name]
            # preserve public/fault_watch/logging/modes — otherwise the UI loses public mode
            self.latest = {**self.latest, "status": "connecting", "source": self.source.name,
                           "module": name, "signals": {}, "faults": [], "connect_phase": None,
                           "error": ""}
        return {"ok": True, "message": f"module: {name}", "module": name}

    def _set_mode(self, mode: "str | None") -> "dict":
        """Switch data source mock↔live at runtime (without restart). Releases the
        active session and repoints all modules to the chosen mode's variant."""
        if not self._variants or mode not in self._modes:
            return {"ok": False, "error": f"unknown mode: {mode}"}
        if mode != self._mode:
            try:
                self.source.disconnect()  # release any K-line session before switching
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
        """Basic mode: read fault codes from all modules sequentially. Releases the
        active session first (frees the K-line port), scans, then lets normal
        polling reconnect. Runs on the poller thread → serialized with the bus."""
        try:
            self.source.disconnect()  # free the port before the sequential scan
        except Exception:  # noqa: BLE001
            pass
        from ..faultscan import read_all
        try:
            report = read_all(self._mode or "mock", self._scan_port)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return {"ok": True, "mode": self._mode or "mock", "report": report}

    def start_csv(self, path: "str | None" = None) -> "dict":
        """Start logging live data to a CSV file (for the user — following temps etc.).
        Logs the ACTIVE module's signals, one row per poll. Idempotent."""
        from .logger import CsvLogger
        with self._csv_lock:  # start/stop on the HTTP thread, log() in the poller
            if self._csv is not None:
                return {"ok": True, "file": os.path.basename(self._csv.path),
                        "message": "already recording"}
            if path is None:
                path = os.path.join(self._csv_dir,
                                    f"livedata-{time.strftime('%Y%m%d-%H%M%S')}.csv")
            self._csv = CsvLogger(path)
        return {"ok": True, "file": os.path.basename(path), "path": path, "message": "recording"}

    def stop_csv(self) -> "dict":
        """Stop the CSV logging. Returns filename + number of rows."""
        with self._csv_lock:
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
                elif action in _INLINE_COMMANDS:
                    holder["result"] = self._run_inline(action, cmd.get("params") or {})
                else:
                    holder["result"] = self.source.command(action, cmd.get("params"))
            except Exception as exc:  # noqa: BLE001
                holder["result"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            holder["event"].set()

    def _log_conn_transition(self, snap: "dict") -> None:
        """Log only when the status actually changes (connected↔error) or when
        the error text changes — otherwise a dropped cable would spam every ~0.5 s.
        Mock sources (always connected without a real session) aren't logged.

        The transition is keyed on (MODULE, status): if you switch from one connected
        module to another, the status is "connected" at both ends, and a plain status
        comparison then silences the new module's CONNECTED line. That hid a successful
        SLABS session 2026-08-18 23:08:54 ("session established" without CONNECTED) and
        made the log outright misleading during debugging.
        """
        status = snap.get("status")
        if self._mode == "mock" or type(self.source).__name__.startswith("Mock"):
            return  # mock is always "connected" without a real session → nothing to log
        err = snap.get("error") or ""
        key = (snap.get("module"), status)
        if key == self._last_conn_status and err == self._last_conn_error:
            return
        if status == "connected":
            n = len(snap.get("signals") or {})
            self._conn_log(
                f"CONNECTED — {n} signals, {len(snap.get('faults') or [])} fault codes",
                module=snap.get("module"))
        elif status == "error":
            self._conn_log(f"ERROR — {err}", module=snap.get("module"))
        self._last_conn_status = key
        self._last_conn_error = err
        self._last_phase_logged = None  # new status → the next establishment phase is logged again

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            self._drain_commands()  # writes first, serialized with poll
            active = self._active
            try:
                snap = self.source.poll()
            except Exception as exc:  # noqa: BLE001
                snap = {
                    "status": "error", "source": self.source.name,
                    "signals": {}, "faults": [], "error": f"{type(exc).__name__}: {exc}",
                }
            snap["module"] = active  # which tab the data belongs to
            snap["mode"] = self._mode  # active data-source mode (mock/live)
            snap["modes"] = self._modes  # selectable modes (for the UI toggle)
            snap["logging"] = self._csv.status() if self._csv is not None else {"recording": False}
            snap["public"] = self._public  # the UI is simplified in public mode
            snap["fault_watch"] = self._fault_watch  # fast fault-polling on/off
            snap["allow_shutdown"] = self._allow_shutdown  # Settings "Shut down Pi" button
            self._remember_engine(snap)      # save engine context for the SLABS log
            self._log_conn_transition(snap)  # log connected/error transitions
            self.latest = snap
            if self.logger is not None:
                try:
                    self.logger.log(self.latest)
                except Exception:  # noqa: BLE001 — a log error must never fell the poll loop
                    pass
            csv_log = self._csv  # local ref: stop_csv may null it mid-logging
            if csv_log is not None:
                try:
                    csv_log.log(self.latest)
                except Exception:  # noqa: BLE001 — a CSV error must never fell the poll loop
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
