"""Basic mode — read fault codes from all modules sequentially.

K-line is a shared bus → one module at a time: establish → read faults → close, then
the next. Returns a normalized report ``[{module, status, faults, note}]`` where
``status`` ∈ ``ok`` (no faults) / ``faults`` / ``error`` (could not read).

TD5 and SLABS are proven and tested. Airbag (0x5B) is **experimental** (read-only,
unverified live). ACE/EAT/BCU have no comms class → listed as ``not implemented``.
"""
from __future__ import annotations

import time
from typing import Callable

# Modules that don't yet have a reading comms class (proprietary protocols).
_UNIMPLEMENTED = [
    ("ACE", "active suspension — proprietary bulk protocol, not read in code yet"),
    ("Auto Gearbox", "EAT 72-framed — ECU responds but decoding not finished"),
    ("BCU", "Valeo — no fault-code list in code yet"),
]


def _row(module: str, faults: "list[str]", *, note: str = "") -> "dict":
    return {"module": module, "status": "faults" if faults else "ok",
            "faults": faults, "note": note}


def _err(module: str, exc: "Exception", *, note: str = "") -> "dict":
    return {"module": module, "status": "error", "faults": [],
            "error": f"{type(exc).__name__}: {exc}", "note": note}


def read_all(mode: str, port: str = "auto",
             sleep: "Callable[[float], None]" = time.sleep) -> "list[dict]":
    """Read fault codes from all modules. ``mode`` = 'mock' | 'live'."""
    rows = _mock_report() if mode != "live" else _live_report(port, sleep)
    for name, note in _UNIMPLEMENTED:
        rows.append({"module": name, "status": "unimplemented", "faults": [], "note": note})
    return rows


def _mock_report() -> "list[dict]":
    """The RDL 016 baseline (proven) as demo data without a car."""
    return [
        _row("TD5", []),
        _row("SLABS", ["020: front right wheel speed sensor — output too low (Logged)",
                       "027: shuttle valve switch — electrical failure (Logged)"]),
        _row("Airbag", ["004: airbag warning lamp — open circuit intermittent",
                        "022: open circuit intermittent"], note="experimental"),
    ]


def _live_report(port: str, sleep: "Callable[[float], None]") -> "list[dict]":
    from .kline import KLine
    from .kwp2000 import KWP2000
    from .transport import SerialTransport
    from .web.sources import resolve_serial_port

    try:
        real_port = resolve_serial_port(port)
    except FileNotFoundError as exc:
        # no cable → mark all three as unread, same cause
        return [_err(m, exc) for m in ("TD5", "SLABS", "Airbag")]

    rows = []
    # --- TD5 -------------------------------------------------------------- #
    try:
        from .td5 import Td5
        t = Td5(KWP2000(KLine(SerialTransport(real_port, timeout=1.0)), tolerant=True))
        t.open()
        try:
            t.establish()
            faults = [f for f in t.read_faults() if not f.startswith("byte")]
            rows.append(_row("TD5", faults))
        finally:
            t.release()  # close the session cleanly — the next module inits on the same bus
    except Exception as exc:  # noqa: BLE001
        rows.append(_err("TD5", exc))
    sleep(0.5)  # let the bus go quiet between modules

    # --- SLABS ------------------------------------------------------------ #
    try:
        from .slabs import SLABS_ADDRESS, Slabs
        s = Slabs(KWP2000(KLine(SerialTransport(real_port, timeout=1.0), target=SLABS_ADDRESS),
                          tolerant=True))
        s.open()
        try:
            s.establish()
            f = s.read_faults()  # {"loggade":[…], "aktuella":[…]}  (logged / current)
            faults = [x + " (Logged)" for x in f.get("loggade", [])] + \
                     [x + " (Current)" for x in f.get("aktuella", [])]
            rows.append(_row("SLABS", faults))
        finally:
            s.release()  # close the session cleanly — the next module inits on the same bus
    except Exception as exc:  # noqa: BLE001
        rows.append(_err("SLABS", exc))
    sleep(0.5)

    # --- Airbag (experimentellt, read-only) ------------------------------- #
    try:
        from .airbag import AIRBAG_ADDRESS, Airbag
        a = Airbag(KWP2000(KLine(SerialTransport(real_port, timeout=1.0), target=AIRBAG_ADDRESS),
                           tolerant=True, addressed=True))
        a.open()
        try:
            a.establish()
            faults = [f"{r['number']:03d}: {r['status_text']}" for r in a.read_faults()]
            rows.append(_row("Airbag", faults, note="experimental"))
        finally:
            a.release()  # close the session cleanly — the next module inits on the same bus
    except Exception as exc:  # noqa: BLE001
        rows.append(_err("Airbag", exc, note="experimental (may need SecurityAccess we can't do)"))

    return rows
