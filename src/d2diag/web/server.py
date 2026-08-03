"""HTTP + SSE-server för dashboarden (stdlib, inga externa beroenden).

En bakgrundstråd pollar datakällan och uppdaterar ``latest``; ``/events`` strömmar
den via Server-Sent Events. ``/command`` är en hook för framtida skriv-/rensa-
kommandon (ej implementerad än).
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

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
        else:
            self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/command":
            # Framtida läs/skriv av specifika fält (radera felkoder, skriv settings).
            self._json(
                {"ok": False, "error": "skrivkommandon ej implementerade än"}, code=501
            )
        else:
            self.send_error(404)

    # ---- svar ---------------------------------------------------------- #
    def _html(self) -> None:
        body = _DASHBOARD.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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
        source: DataSource,
        host: str = "0.0.0.0",
        port: int = 8080,
        poll_interval: float = 0.5,
        stream_interval: float = 0.5,
    ) -> None:
        super().__init__((host, port), _Handler)
        self.source = source
        self.poll_interval = poll_interval
        self.stream_interval = stream_interval
        self.latest: "dict" = {
            "status": "connecting", "source": source.name, "signals": {}, "faults": []
        }
        self._stop = threading.Event()
        self._poller = threading.Thread(target=self._poll_loop, daemon=True)

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.latest = self.source.poll()
            except Exception as exc:  # noqa: BLE001
                self.latest = {
                    "status": "error", "source": self.source.name,
                    "signals": {}, "faults": [], "error": f"{type(exc).__name__}: {exc}",
                }
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
