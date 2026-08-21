#!/usr/bin/env python3
"""SLABS probe: test init variants systematically and log EVERYTHING.

The dashboard is the wrong tool for debugging the connection — it reconnects,
switches modules and overwrites the context. This script does the opposite: one
controlled sequence, one variant at a time, with raw TX/RX to file.

Background (see references/slabs_protocol.md):
  * The reference tool inits PHYSICALLY with tester address 0xF7: ``81 29 F7 81 22``.
  * Our own address hunt 2026-08-05 got a response from 0x29 ONLY in FUNCTIONAL mode
    with tester address 0xF1: ``C1 29 F1 81 5c`` → ``C1 57 8F``.
  * The muki01 reference (confirmed correct) inits functionally: ``C1 33 F1 81 66``.
  * In the sniff the init only succeeds after 25–28 s WITHOUT traffic to the module.

The script therefore measures both address modes with quiet periods in between, and
reads engine context (rpm/speed/battery) before the test so a silent attempt can be
interpreted afterwards — SLABS refuses comms >8–20 km/h.

Run stationary with ignition on:

    PYTHONPATH=src python3 tools/slabs_probe.py                  # auto-detect cable
    PYTHONPATH=src python3 tools/slabs_probe.py --quiet 30 --hold 120
    PYTHONPATH=src python3 tools/slabs_probe.py --no-td5 --rounds 2
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from d2diag.kline import KLine, encode  # noqa: E402
from d2diag.kline.kline import KLineTimeout  # noqa: E402
from d2diag.kwp2000 import KWP2000  # noqa: E402
from d2diag.slabs import SLABS_ADDRESS, Slabs  # noqa: E402
from d2diag.td5 import Td5  # noqa: E402
from d2diag.transport import LoggingTransport, SerialTransport  # noqa: E402
from d2diag.web.sources import resolve_serial_port  # noqa: E402

# (name, functional, tester address) — the order is the test order.
VARIANTS = (
    ("physical/F7  (reference tool)", False, 0xF7),
    ("functional/F1 (hunt+muki01)", True, 0xF1),
    ("functional/F7", True, 0xF7),
    ("physical/F1", False, 0xF1),
)

_log_fh = None


def say(msg: str) -> None:
    line = f"{dt.datetime.now().strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    if _log_fh:
        _log_fh.write(line + "\n")
        _log_fh.flush()


def quiet(seconds: float, why: str = "quiet period") -> None:
    """Wait WITHOUT sending anything. Every byte resets the module's wait."""
    if seconds <= 0:
        return
    say(f"  … {why} {seconds:.0f}s")
    time.sleep(seconds)


def engine_context(transport, sleep_after: float) -> "dict | None":
    """Read rpm/speed/battery from TD5 and release the session cleanly (20 + 82).

    Gives interpretable context to a silent SLABS attempt: was the car stationary?
    Was the engine running? What was the voltage?
    """
    td5 = Td5(KWP2000(KLine(transport, target=0x13), tolerant=True))
    try:
        td5.establish()
    except Exception as exc:  # noqa: BLE001
        say(f"  TD5 didn't respond ({type(exc).__name__}) — cable/ignition?")
        return None
    try:
        vals = td5.read_all()
        ctx = {k: vals.get(k) for k in ("rpm", "speed", "battery")}
        say(f"  TD5: rpm {ctx.get('rpm')}, speed {ctx.get('speed')} km/h, "
            f"battery {ctx.get('battery')} V")
        # Measured 2026-08-19 (8 runs): engine running gave 3 hits out of 4, engine off
        # only 1 out of 4. No sharp voltage threshold, but clearly the strongest factor.
        if not ctx.get("rpm"):
            say("  ⚠️  ENGINE IS OFF. SLABS responded in only 1 of 4 runs — "
                "start the engine for the best chance (SLS's normal operating case).")
        if (ctx.get("speed") or 0) > 5:
            say("  ⚠️  THE CAR IS ROLLING. SLABS refuses comms >8–20 km/h — stop first.")
        return ctx
    except Exception as exc:  # noqa: BLE001
        say(f"  TD5 read error: {type(exc).__name__}: {exc}")
        return None
    finally:
        # end_session() = 20 + 82. NOT release()/close(): the port is shared with
        # the SLABS attempts, and a closed port makes every following init "fail"
        # without a single byte having gone out on the bus.
        try:
            td5.end_session()
        except Exception:  # noqa: BLE001
            pass
        quiet(sleep_after, "let the bus fall silent after TD5")


def try_init(transport, name: str, functional: bool, source: int,
             write_gap: float = 0.0, init_high: float = 0.025,
             init_idle: float = 0.0) -> "Slabs | None":
    """A single init attempt with a given variant. Returns a live Slabs or None.

    ``write_gap`` is P4 — the inter-byte time in our request. ISO 14230-2 specifies
    5–20 ms and the muki01 reference uses 5 ms, whereas we've always sent the whole
    frame in one sweep. It's an untested hypothesis for why the reference tool gets in
    on the first attempt and we need several.
    """
    frame = encode(b"\x81", SLABS_ADDRESS, source, addressed=True, functional=functional)
    tags = ("" if not write_gap else f" · P4 {write_gap*1000:.0f}ms") + \
           ("" if abs(init_high - 0.025) < 1e-9 else f" · high {init_high*1000:.0f}ms")
    say(f"  → {name}{tags}: {frame.hex(' ')}")
    kline = KLine(transport, target=SLABS_ADDRESS, write_gap=write_gap,
                  init_high=init_high, init_idle=init_idle)
    kwp = KWP2000(kline, tolerant=True)
    slabs = Slabs(kwp)
    try:
        c1 = kwp.start_communication(tolerant=True, functional=functional, source=source)
    except KLineTimeout as exc:
        # Show what the pulse ACTUALLY was — nominal values say nothing about a USB port.
        say(f"     silent · pulse {kline.last_pulse} ({exc})")
        return None
    except Exception as exc:  # noqa: BLE001
        # Everything else is OUR fault (closed port, broken cable). It must never
        # be reported as "silent" — that would read a test failure as a module response.
        say(f"     ✗ LOCAL ERROR, nothing was sent: {type(exc).__name__}: {exc}")
        raise
    say(f"     C1! {c1[:4].hex(' ')} · pulse {kline.last_pulse}")
    # Acknowledgement: the reference tool always sends 1A 8A first — and the response
    # tells a real session apart from a C1 that was just noise on the bus.
    try:
        ident = slabs.read_ecu_id(0x8A)
        say(f"     ack 1A 8A → {ident[:8].hex(' ')}")
    except Exception as exc:  # noqa: BLE001
        say(f"     NO ack on 1A 8A ({type(exc).__name__}) — probably a false positive")
        return None
    return slabs


def hold(slabs: Slabs, seconds: float) -> None:
    """Hold the session at 1 Hz (the reference tool's rate) and log every read."""
    say(f"  holding the session for {seconds:.0f}s at 1 Hz …")
    t0 = time.monotonic()
    reads = misses = 0
    try:
        faults = slabs.read_faults()
        say(f"  fault codes: {faults}")
    except Exception as exc:  # noqa: BLE001
        say(f"  fault-code read failed: {type(exc).__name__}")
    while time.monotonic() - t0 < seconds:
        time.sleep(1.0)
        try:
            slabs.tester_present()
        except Exception:  # noqa: BLE001
            pass
        try:
            raw = slabs.read_data(0x54)
        except Exception:  # noqa: BLE001
            raw = b""
        if raw:
            reads += 1
            if reads % 10 == 1 or misses:
                say(f"   {time.monotonic() - t0:5.0f}s  heights {raw[0]}/{raw[1]}"
                    f"  ({reads} ok, {misses} dropped)")
            misses = 0
        else:
            misses += 1
            say(f"   {time.monotonic() - t0:5.0f}s  SILENT ({misses} in a row)")
            if misses >= 5:
                say("  ✗ session lost")
                return
    say(f"  ✓ held the whole period: {reads} successful reads")


def main() -> int:
    global _log_fh
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--serial", default="auto", help="serial port (default: auto-detect)")
    ap.add_argument("--quiet", type=float, default=30.0,
                    help="quiet period between attempts in seconds (default 30)")
    ap.add_argument("--hold", type=float, default=120.0,
                    help="hold the session this long on a hit (default 120 s)")
    ap.add_argument("--rounds", type=int, default=1, help="number of passes through the matrix")
    ap.add_argument("--no-td5", action="store_true",
                    help="skip the TD5 context (no rpm/speed/battery in the log)")
    ap.add_argument("--init-idle", type=float, default=0.0,
                    help="W5 — guaranteed bus idle in ms before each init pulse "
                         "(ISO: 300). 0 = off. Use 1000 to eliminate W5 as a "
                         "variable during debugging.")
    ap.add_argument("--init-highs", default="25",
                    help="TiniH in ms — how long K-line is held HIGH after the low pulse "
                         "before StartCommunication is sent (ISO: 25 ms ± 1). "
                         "Comma-separated to sweep, e.g. 15,25,35.")
    ap.add_argument("--write-gaps", default="0,5",
                    help="P4 values to test in ms (default 0,5). 0 = whole frame in one "
                         "sweep as so far, 5 = muki01's inter-byte delay.")
    ap.add_argument("--order", choices=("shuffle", "fixed"), default="shuffle",
                    help="variant order. SHUFFLE (default) is required to separate the "
                         "variant's effect from the attempt number — with a fixed order "
                         "they're perfectly confounded (proven 2026-08-19).")
    ap.add_argument("--seed", type=int, default=None, help="seed for the order")
    args = ap.parse_args()

    seed = args.seed if args.seed is not None else int(time.time())
    rng = random.Random(seed)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    os.makedirs("logs", exist_ok=True)
    raw_path = f"logs/slabs_probe-{stamp}.raw.log"
    _log_fh = open(f"logs/slabs_probe-{stamp}.log", "w", encoding="utf-8")

    try:
        port = resolve_serial_port(args.serial)
    except FileNotFoundError as exc:
        say(f"no cable found: {exc}")
        return 1

    say(f"SLABS probe {stamp} — port {port} — order {args.order} (seed {seed})")
    say(f"raw TX/RX → {raw_path}")
    say("Run STATIONARY with ignition on. SLABS refuses comms >8–20 km/h.")

    transport = LoggingTransport(SerialTransport(port, timeout=1.0), logfile=raw_path)
    try:
        transport.open()
    except Exception as exc:  # noqa: BLE001 — a broken/busy port should give an answer, not a trace
        say(f"could not open {port}: {type(exc).__name__}: {exc}")
        say("is the cable plugged in? is anything else (the dashboard) using the port at the same time?")
        return 1
    results: "list[tuple[str, str]]" = []
    try:
        if not args.no_td5:
            say("\n[context] reading the engine first (and releasing the session cleanly)")
            engine_context(transport, args.quiet)

        if not transport.is_open:   # property, not a method
            say("the port is closed after the context phase — aborting (that would be no measurement)")
            return 1

        wgaps = [float(g) / 1000 for g in args.write_gaps.split(",") if g.strip()]
        highs = [float(h) / 1000 for h in args.init_highs.split(",") if h.strip()]
        for rnd in range(1, args.rounds + 1):
            combos = [(n, f, s, w, h) for (n, f, s) in VARIANTS for w in wgaps for h in highs]
            if args.order == "shuffle":
                rng.shuffle(combos)
            say(f"\n[matrix] pass {rnd}/{args.rounds} — {len(combos)} combinations")
            for name, functional, source, wgap, high in combos:
                label = f"{name} · P4 {wgap*1000:.0f}ms · high {high*1000:.0f}ms"
                slabs = try_init(transport, name, functional, source, wgap, high,
                                 args.init_idle / 1000)
                results.append((label, "HIT" if slabs else "silent"))
                if slabs is not None:
                    hold(slabs, args.hold)
                    try:
                        slabs.release()  # 82 — don't leave the link open
                    except Exception:  # noqa: BLE001
                        pass
                    say("\n=== SUMMARY ===")
                    for n, r in results:
                        say(f"  {r:6} {n}")
                    return 0
                quiet(args.quiet)
    except KeyboardInterrupt:
        say("\naborted")
    finally:
        try:
            transport.close()
        except Exception:  # noqa: BLE001
            pass

    say("\n=== SUMMARY ===")
    for n, r in results:
        say(f"  {r:6} {n}")
    say("no variant made contact — see the raw log for exact bursts")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
