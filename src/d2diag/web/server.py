"""HTTP + SSE-server för dashboarden (stdlib, inga externa beroenden).

En bakgrundstråd pollar datakällan och uppdaterar ``latest``; ``/events`` strömmar
den via Server-Sent Events. ``/command`` är en hook för framtida skriv-/rensa-
kommandon (ej implementerad än).
"""
from __future__ import annotations

import json
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .docs import DocLibrary
from .sources import DataSource

_DASHBOARD = Path(__file__).with_name("dashboard.html")


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
            self._json({"module": mod, "map": mp, "modules": list(self.server._menus)})
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
            result = self.server.enqueue_command(cmd)
            self._json(result, code=200 if result.get("ok") else 400)
        else:
            self.send_error(404)

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
        source: "DataSource | dict",
        host: str = "0.0.0.0",
        port: int = 8080,
        poll_interval: float = 0.5,
        stream_interval: float = 0.5,
        logger=None,
        active: "str | None" = None,
        menus: "dict | None" = None,
        docs: "DocLibrary | None" = None,
    ) -> None:
        super().__init__((host, port), _Handler)
        self._menus = menus or {}  # modul → meny-lista (Karta-fliken)
        self.docs = docs or DocLibrary()  # markdown-vy (Dokument-fliken)
        # source kan vara en enda DataSource (bakåtkompat) eller en dict
        # {modulnamn: DataSource}. Bara en modul är aktiv åt gången — K-line är
        # en delad buss, så att byta flik = släppa gammal session och etablera ny.
        if isinstance(source, dict):
            self._modules: "dict[str, DataSource]" = dict(source)
        else:
            self._modules = {source.name: source}
        self._active = active if active in self._modules else next(iter(self._modules))
        self.source = self._modules[self._active]
        self.poll_interval = poll_interval
        self.stream_interval = stream_interval
        self.logger = logger  # valfri SnapshotLogger → loggar varje poll till fil
        self.latest: "dict" = {
            "status": "connecting", "source": self.source.name,
            "module": self._active, "signals": {}, "faults": [],
        }
        self._stop = threading.Event()
        self._commands: "queue.Queue" = queue.Queue()
        self._poller = threading.Thread(target=self._poll_loop, daemon=True)

    def enqueue_command(self, cmd: "dict", timeout: float = 8.0) -> "dict":
        """Köa ett skrivkommando till pollertråden och vänta på resultatet.

        Serialiseras med pollningen så K-line-åtkomsten aldrig krockar."""
        holder = {"result": None, "event": threading.Event()}
        self._commands.put((cmd, holder))
        if holder["event"].wait(timeout):
            return holder["result"]
        return {"ok": False, "error": "timeout — inget svar från diagnostiklagret"}

    def modules(self) -> "list[str]":
        return list(self._modules)

    def _select(self, name: "str | None") -> "dict":
        """Byt aktiv modul: släpp gamla sessionen, aktivera den nya (etableras
        lazily vid nästa poll). K-line är en delad buss → bara en session åt gången."""
        if name not in self._modules:
            return {"ok": False, "error": f"okänd modul: {name}"}
        if name != self._active:
            try:
                self.source.disconnect()  # släpp K-line-porten/sessionen
            except Exception:  # noqa: BLE001
                pass
            self._active = name
            self.source = self._modules[name]
            self.latest = {"status": "connecting", "source": self.source.name,
                           "module": name, "signals": {}, "faults": []}
        return {"ok": True, "message": f"modul: {name}", "module": name}

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
                else:
                    holder["result"] = self.source.command(action, cmd.get("params"))
            except Exception as exc:  # noqa: BLE001
                holder["result"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            holder["event"].set()

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
            self.latest = snap
            if self.logger is not None:
                try:
                    self.logger.log(self.latest)
                except Exception:  # noqa: BLE001 — loggfel får aldrig fälla poll-loopen
                    pass
            self._stop.wait(self.poll_interval)

    def start_polling(self) -> None:
        if not self._poller.is_alive():
            self._poller.start()

    def stop(self) -> None:
        self._stop.set()

    def serve(self) -> None:
        self.start_polling()
        try:
            self.serve_forever()
        finally:
            self.stop()
