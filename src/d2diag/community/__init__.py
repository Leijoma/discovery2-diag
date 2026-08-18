"""Community contribution client — **opt-in, anonymous, PII-free**.

Manages a single consent choice + a random anonymous install ID, and uploads
readings to the d2diag contribution endpoint (``/register`` + ``/contribute``).

Nothing is sent unless the user has opted in. The payload is built by
**whitelist** — only protocol/reading fields and a coarse vehicle descriptor
(model/year/engine/market) leave the machine; never VIN, registration, location
or anything identifying. Runs in the local app (server-side), so the browser
never talks to the endpoint directly.
"""
from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
import uuid
from pathlib import Path


def _ssl_context():
    """Verified TLS context. Use certifi's CA bundle if present (fixes the macOS
    python.org install that ships no certs); otherwise fall back to the system
    store (Linux/Pi). Verification is NEVER disabled."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001 — certifi absent → system default context
        return None

TOOL_VERSION = "0.1.0"
DEFAULT_ENDPOINT = os.environ.get("D2DIAG_ENDPOINT", "https://www.driftwoodstudios.se/d2diag")
_VEHICLE_KEYS = ("model", "year", "engine", "market")


def _default_config_path() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "d2diag", "community.json")


def _post(url: str, payload: dict, timeout: float = 8.0) -> dict:
    """POST JSON, return the decoded response (or an ``{ok:False,error}`` dict).
    Network failures never raise — sharing must never crash the app."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as r:  # noqa: S310
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read() or b"{}")
        except ValueError:
            return {"ok": False, "error": f"http {exc.code}"}
    except Exception as exc:  # noqa: BLE001 — offline / DNS / timeout
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _clean_vehicle(v) -> "dict | None":
    if not isinstance(v, dict):
        return None
    out = {k: str(v[k])[:40] for k in _VEHICLE_KEYS if v.get(k) not in (None, "")}
    return out or None


class Community:
    """Local consent + anonymous install ID + opt-in uploader."""

    def __init__(self, config_path: "str | None" = None,
                 endpoint: str = DEFAULT_ENDPOINT, poster=_post) -> None:
        self.path = config_path or _default_config_path()
        self.endpoint = endpoint.rstrip("/")
        self._post = poster
        self._cfg = self._load()

    # ---- persistence ---------------------------------------------------- #
    def _load(self) -> dict:
        try:
            return json.loads(Path(self.path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        p = Path(self.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self._cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- state ---------------------------------------------------------- #
    def install_id(self) -> str:
        """Random anonymous UUID, generated once and persisted (only *sent* on opt-in)."""
        iid = self._cfg.get("install_id")
        if not iid:
            iid = str(uuid.uuid4())
            self._cfg["install_id"] = iid
            self._save()
        return iid

    @property
    def consent(self):
        return self._cfg.get("consent")  # None = never chosen, True, or False

    def state(self) -> dict:
        return {"consent": self.consent, "vehicle": self._cfg.get("vehicle"),
                "endpoint": self.endpoint, "install": self.install_id()[:8],
                "registered": bool(self._cfg.get("registered"))}

    # ---- consent + upload ----------------------------------------------- #
    def set_consent(self, consent: bool, vehicle: "dict | None" = None) -> dict:
        """Record the opt-in/out. On opt-in, register the anonymous install."""
        self._cfg["consent"] = bool(consent)
        if vehicle is not None:
            self._cfg["vehicle"] = _clean_vehicle(vehicle)
        self._save()
        if self._cfg["consent"]:
            return {"ok": True, "consent": True, **self._register()}
        return {"ok": True, "consent": False}

    def _register(self) -> dict:
        res = self._post(self.endpoint + "/register", {
            "install_id": self.install_id(), "tool_version": TOOL_VERSION,
            "vehicle": self._cfg.get("vehicle")})
        if res.get("ok"):
            self._cfg["registered"] = True
            self._save()
        return {"registered": bool(res.get("ok")), "register_error": res.get("error")}

    def contribute(self, record: dict) -> dict:
        """Upload one reading — only if the user opted in. PII-free by whitelist."""
        if not self.consent:
            return {"ok": False, "error": "sharing not enabled"}
        return self._post(self.endpoint + "/contribute", self._payload(record))

    def _payload(self, r: dict) -> dict:
        return {
            "install_id": self.install_id(),
            "tool_version": TOOL_VERSION,
            "vehicle": self._cfg.get("vehicle"),
            "module": r.get("module"),
            "lid": r.get("lid"),
            "offset": r.get("offset"),
            "kind": r.get("kind"),
            "raw": r.get("raw"),
            "our_name": r.get("name") or r.get("our_name"),
            "our_value": r.get("our_value"),
            "our_confidence": r.get("confidence") or r.get("our_confidence"),
            "answer": r.get("answer") or {},
        }
