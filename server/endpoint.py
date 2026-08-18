"""d2diag community contribution endpoint.

A tiny, dependency-free service (stdlib ``http.server`` + ``sqlite3``) that receives
**anonymous, PII-free** contributions from the diagnostic app and shows a maintainer
admin view. Runs on the maintainer's own server behind Caddy at
``https://www.driftwoodstudios.se/d2diag`` (Caddy strips the ``/d2diag`` prefix, so
this service sees ``/register`` / ``/contribute`` / ``/admin``).

Design principles:
- **No PII stored.** Payloads are whitelisted to protocol/reading fields; any known
  personal key (VIN, registration, IP, GPS, email …) is rejected. The client IP is
  never recorded.
- **Anonymous install ID** (a random UUID the app generates on opt-in) lets us count
  unique installs and separate *registered* from *contributing* — without identity.
- Contributions land in SQLite for the maintainer to review and (manually) promote
  ``kandidat → belagt`` in the app's signal store. Nothing is auto-published.

Run: ``python3 server/endpoint.py --db data/d2diag.sqlite --port 8090``
Admin auth: put Caddy ``basic_auth`` on ``/d2diag/admin`` (recommended). As
defense-in-depth, if ``ADMIN_TOKEN`` is set the ``/admin`` page also requires
``?token=…`` (or an ``X-Admin-Token`` header).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# Keys that must never be stored — reject the whole payload if any appears.
_PII_KEYS = {
    "vin", "registration", "reg", "regno", "plate", "numberplate", "licenseplate",
    "ip", "ipaddr", "gps", "lat", "lon", "latitude", "longitude", "location", "geo",
    "email", "mail", "name", "fullname", "phone", "tel", "address", "user", "owner",
}
_INSTALL_RE = re.compile(r"^[A-Za-z0-9._-]{8,64}$")   # UUID-ish, anonymous


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Validation (pure — unit-tested)
# --------------------------------------------------------------------------- #
def _has_pii(obj) -> bool:
    """Recursively detect any blacklisted personal key in a payload."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in _PII_KEYS or _has_pii(v):
                return True
    elif isinstance(obj, list):
        return any(_has_pii(x) for x in obj)
    return False


def _clean_vehicle(v) -> "dict | None":
    """Keep only the coarse, non-identifying descriptor fields."""
    if not isinstance(v, dict):
        return None
    out = {k: str(v[k])[:40] for k in ("model", "year", "engine", "market")
           if v.get(k) not in (None, "")}
    return out or None


def _install_id(p: dict) -> str:
    iid = str(p.get("install_id", ""))
    if not _INSTALL_RE.match(iid):
        raise ValueError("invalid or missing install_id (anonymous UUID expected)")
    return iid


def validate_register(p: dict) -> dict:
    if _has_pii(p):
        raise ValueError("payload contains disallowed personal fields")
    return {
        "install_id": _install_id(p),
        "tool_version": str(p.get("tool_version", ""))[:40],
        "vehicle": _clean_vehicle(p.get("vehicle")),
    }


def validate_contribution(p: dict) -> dict:
    if _has_pii(p):
        raise ValueError("payload contains disallowed personal fields")
    iid = _install_id(p)
    if not p.get("module"):
        raise ValueError("module required")
    ans = p.get("answer") or {}
    av = ans.get("value")
    ov = p.get("our_value")
    return {
        "install_id": iid,
        "tool_version": str(p.get("tool_version", ""))[:40],
        "vehicle": _clean_vehicle(p.get("vehicle")),
        "module": str(p.get("module"))[:32],
        "lid": str(p.get("lid", ""))[:8],
        "offset": p.get("offset") if isinstance(p.get("offset"), int) else None,
        "kind": str(p.get("kind", ""))[:16],
        "raw": str(p.get("raw", ""))[:200],
        "our_name": str(p.get("our_name", ""))[:64],
        "our_value": None if ov is None else str(ov)[:64],
        "our_confidence": str(p.get("our_confidence", ""))[:16],
        "answer_type": str(ans.get("type", ""))[:16],     # confirm / correct / unknown
        "answer_value": None if av is None else str(av)[:64],
        "answer_unit": str(ans.get("unit", ""))[:16],
    }


# --------------------------------------------------------------------------- #
# Storage (SQLite)
# --------------------------------------------------------------------------- #
class Store:
    def __init__(self, path: str) -> None:
        self.path = path
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        self._init()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        return c

    def _init(self) -> None:
        with self._conn() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS installs(
                    install_id TEXT PRIMARY KEY, first_seen TEXT, last_seen TEXT,
                    tool_version TEXT, vehicle TEXT);
                CREATE TABLE IF NOT EXISTS contributions(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, install_id TEXT, received_at TEXT,
                    tool_version TEXT, vehicle TEXT, module TEXT, lid TEXT, "offset" INTEGER,
                    kind TEXT, raw TEXT, our_name TEXT, our_value TEXT, our_confidence TEXT,
                    answer_type TEXT, answer_value TEXT, answer_unit TEXT);
                """
            )

    def _touch_install(self, c, install_id, tool_version, vehicle_json) -> None:
        now = _now()
        c.execute(
            """INSERT INTO installs(install_id, first_seen, last_seen, tool_version, vehicle)
               VALUES(?,?,?,?,?)
               ON CONFLICT(install_id) DO UPDATE SET last_seen=excluded.last_seen,
                 tool_version=excluded.tool_version,
                 vehicle=COALESCE(excluded.vehicle, installs.vehicle)""",
            (install_id, now, now, tool_version, vehicle_json),
        )

    def register(self, rec: dict) -> None:
        veh = json.dumps(rec["vehicle"], ensure_ascii=False) if rec["vehicle"] else None
        with self._conn() as c:
            self._touch_install(c, rec["install_id"], rec["tool_version"], veh)

    def add_contribution(self, rec: dict) -> None:
        veh = json.dumps(rec["vehicle"], ensure_ascii=False) if rec["vehicle"] else None
        row = {**rec, "received_at": _now(), "vehicle": veh}
        with self._conn() as c:
            self._touch_install(c, rec["install_id"], rec["tool_version"], veh)
            c.execute(
                """INSERT INTO contributions(install_id, received_at, tool_version, vehicle,
                     module, lid, "offset", kind, raw, our_name, our_value, our_confidence,
                     answer_type, answer_value, answer_unit)
                   VALUES(:install_id,:received_at,:tool_version,:vehicle,:module,:lid,:offset,
                     :kind,:raw,:our_name,:our_value,:our_confidence,:answer_type,:answer_value,
                     :answer_unit)""",
                row,
            )

    def stats(self) -> dict:
        with self._conn() as c:
            one = lambda q: c.execute(q).fetchone()["n"]  # noqa: E731
            rows = lambda q, n=50: [dict(r) for r in c.execute(q).fetchall()][:n]  # noqa: E731
            return {
                "installs": one("SELECT COUNT(*) n FROM installs"),
                "contributing": one("SELECT COUNT(DISTINCT install_id) n FROM contributions"),
                "total": one("SELECT COUNT(*) n FROM contributions"),
                "by_module": rows(
                    "SELECT module, COUNT(*) n FROM contributions GROUP BY module ORDER BY n DESC"),
                "by_confidence": rows(
                    "SELECT COALESCE(NULLIF(our_confidence,''),'?') conf, COUNT(*) n "
                    "FROM contributions GROUP BY conf ORDER BY n DESC"),
                "by_vehicle": rows(
                    "SELECT COALESCE(vehicle,'?') vehicle, COUNT(*) n FROM contributions "
                    "GROUP BY vehicle ORDER BY n DESC LIMIT 20"),
            }

    def recent(self, n: int = 50) -> list:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                """SELECT received_at, install_id, module, lid, our_name, our_value,
                          answer_type, answer_value, answer_unit
                   FROM contributions ORDER BY id DESC LIMIT ?""", (n,)).fetchall()]


# --------------------------------------------------------------------------- #
# Admin HTML (self-contained, no external deps)
# --------------------------------------------------------------------------- #
def render_admin(stats: dict, recent: list) -> str:
    def table(title, rows, cols):
        head = "".join(f"<th>{escape(c)}</th>" for c in cols)
        body = "".join(
            "<tr>" + "".join(f"<td>{escape(str(r.get(c, '')))}</td>" for c in cols) + "</tr>"
            for r in rows) or f'<tr><td colspan="{len(cols)}">—</td></tr>'
        return f"<h2>{escape(title)}</h2><table><tr>{head}</tr>{body}</table>"

    for r in recent:
        r["install"] = (r.get("install_id") or "")[:8]  # short, anonymous
    cards = (
        f'<div class="c"><b>{stats["installs"]}</b><span>installs (opted in)</span></div>'
        f'<div class="c"><b>{stats["contributing"]}</b><span>contributing</span></div>'
        f'<div class="c"><b>{stats["total"]}</b><span>contributions</span></div>'
    )
    return (
        "<!doctype html><meta charset=utf-8><title>d2diag — contributions</title>"
        "<style>body{font:14px system-ui;margin:24px;max-width:900px;color:#111}"
        "h1{font-size:18px}.cards{display:flex;gap:12px;margin:12px 0}"
        ".c{background:#f4f5f7;border-radius:10px;padding:12px 16px;flex:1}"
        ".c b{display:block;font-size:26px}.c span{color:#666;font-size:12px}"
        "table{border-collapse:collapse;width:100%;margin:6px 0 18px;font-size:13px}"
        "th,td{border:1px solid #e2e4e8;padding:5px 8px;text-align:left}"
        "th{background:#f4f5f7}h2{font-size:14px;margin-top:18px}</style>"
        "<h1>d2diag — community contributions</h1>"
        f'<div class="cards">{cards}</div>'
        + table("By module", stats["by_module"], ["module", "n"])
        + table("By confidence", stats["by_confidence"], ["conf", "n"])
        + table("By vehicle", stats["by_vehicle"], ["vehicle", "n"])
        + table("Recent", recent,
                ["received_at", "install", "module", "lid", "our_name", "our_value",
                 "answer_type", "answer_value", "answer_unit"])
    )


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # quiet
        pass

    def _json(self, obj, code=200) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw or b"{}")

    def _admin_ok(self) -> bool:
        token = os.environ.get("ADMIN_TOKEN")
        if not token:
            return True  # rely on Caddy basic_auth in front
        q = parse_qs(urlparse(self.path).query)
        return q.get("token", [None])[0] == token or self.headers.get("X-Admin-Token") == token

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        if path == "/health":
            self._json({"ok": True})
        elif path == "/admin":
            if not self._admin_ok():
                self._json({"ok": False, "error": "unauthorized"}, 401)
                return
            self._html(render_admin(self.server.store.stats(), self.server.store.recent()))
        else:
            self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        try:
            payload = self._body()
        except (ValueError, TypeError):
            self._json({"ok": False, "error": "bad json"}, 400)
            return
        try:
            if self.path == "/register":
                self.server.store.register(validate_register(payload))
                self._json({"ok": True})
            elif self.path == "/contribute":
                self.server.store.add_contribution(validate_contribution(payload))
                self._json({"ok": True})
            else:
                self.send_error(404)
        except ValueError as exc:
            self._json({"ok": False, "error": str(exc)}, 400)


class ContribServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, store: Store, host: str = "127.0.0.1", port: int = 8090) -> None:
        super().__init__((host, port), _Handler)
        self.store = store


def main() -> int:
    ap = argparse.ArgumentParser(description="d2diag community contribution endpoint")
    ap.add_argument("--db", default="data/d2diag.sqlite", help="SQLite path")
    ap.add_argument("--host", default="127.0.0.1", help="bind host (behind Caddy → localhost)")
    ap.add_argument("--port", type=int, default=8090)
    args = ap.parse_args()
    srv = ContribServer(Store(args.db), host=args.host, port=args.port)
    print(f"d2diag endpoint on http://{args.host}:{args.port}  (db: {args.db})")
    print("Routes: POST /register, POST /contribute, GET /admin, GET /health")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
