"""Basic mode — läs felkoder från samtliga moduler sekventiellt.

K-line är en delad buss → en modul åt gången: etablera → läs fel → stäng, sedan
nästa. Returnerar en normaliserad rapport ``[{module, status, faults, note}]`` där
``status`` ∈ ``ok`` (inga fel) / ``faults`` / ``error`` (kunde inte läsa).

TD5 och SLABS är belagda och testade. Airbag (0x5B) är **experimentellt** (read-only,
overifierat live). ACE/EAT/BCU saknar comms-klass → listas som ``ej implementerad``.
"""
from __future__ import annotations

import time
from typing import Callable

# Moduler som ännu inte har en läsande comms-klass (proprietära protokoll).
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
    """Läs felkoder från alla moduler. ``mode`` = 'mock' | 'live'."""
    rows = _mock_report() if mode != "live" else _live_report(port, sleep)
    for name, note in _UNIMPLEMENTED:
        rows.append({"module": name, "status": "unimplemented", "faults": [], "note": note})
    return rows


def _mock_report() -> "list[dict]":
    """RDL 016-baslinjen (belagt) som demodata utan bil."""
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
        # ingen kabel → markera alla tre som ej lästa, samma orsak
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
            t.release()  # stäng sessionen rent — nästa modul initar på samma buss
    except Exception as exc:  # noqa: BLE001
        rows.append(_err("TD5", exc))
    sleep(0.5)  # låt bussen tystna mellan moduler

    # --- SLABS ------------------------------------------------------------ #
    try:
        from .slabs import SLABS_ADDRESS, Slabs
        s = Slabs(KWP2000(KLine(SerialTransport(real_port, timeout=1.0), target=SLABS_ADDRESS),
                          tolerant=True))
        s.open()
        try:
            s.establish()
            f = s.read_faults()  # {"loggade":[…], "aktuella":[…]}
            faults = [x + " (Logged)" for x in f.get("loggade", [])] + \
                     [x + " (Current)" for x in f.get("aktuella", [])]
            rows.append(_row("SLABS", faults))
        finally:
            s.release()  # stäng sessionen rent — nästa modul initar på samma buss
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
            a.release()  # stäng sessionen rent — nästa modul initar på samma buss
    except Exception as exc:  # noqa: BLE001
        rows.append(_err("Airbag", exc, note="experimental (may need SecurityAccess we can't do)"))

    return rows
