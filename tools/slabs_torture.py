#!/usr/bin/env python3
"""SLABS torture (gentle): measure what actually affects the connection.

`slabs_probe.py` answers "are we getting in right now?". This script answers
"WHAT makes us get in?" — by running many short attempts and varying ONE thing at
a time:

  * **quiet period before init** (``--gaps``) — how long must the bus be silent?
  * **TD5 session first** (``--td5 both``) — does the engine session warm up the bus?
  * **address mode** — physical/F7, functional/F1, functional/F7

The order is **shuffled** (seeded, the seed is logged) so that time, temperature and
battery drain don't coincide with a particular state — otherwise you're measuring
the clock instead of the hypothesis.

Gentle on the car: no actuators, short hold periods, and every session ends cleanly
with ``82`` (StopCommunication) so the next attempt isn't met with ``7F 81 10``.

Results are written as JSONL (one line per attempt) + a summary per factor:

    PYTHONPATH=src python3 tools/slabs_torture.py --rounds 3
    PYTHONPATH=src python3 tools/slabs_torture.py --gaps 0,5,15,30 --hold 15
    PYTHONPATH=src python3 tools/slabs_torture.py --td5 both --rounds 4

Run STATIONARY.

**Data accumulates across runs.** Each run writes its own JSONL, and ``--summary``
merges them. So prefer several SHORT blocks over one long one — the engine
shouldn't idle for twenty minutes. With ``--max-minutes`` the script stops on its
own and summarizes what it managed.

The statistics need roughly 50 attempts per power mode to distinguish 30 % from
7 % (Fisher's exact test on the 2026-08-19 material gave p = 0.27 — not
significant). That's ~3 blocks of 5 minutes per mode.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import random
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from d2diag.kline import KLine, encode  # noqa: E402
from d2diag.kline.kline import KLineTimeout  # noqa: E402
from d2diag.kwp2000 import KWP2000  # noqa: E402
from d2diag.slabs import SLABS_ADDRESS, Slabs  # noqa: E402
from d2diag.td5 import Td5  # noqa: E402
from d2diag.transport import LoggingTransport, SerialTransport  # noqa: E402
from d2diag.web.sources import resolve_serial_port  # noqa: E402

# (functional mode, tester address, target address). The init frame is
# <fmt> <target> <source> 81 <cs>, where fmt = 0x81 physical / 0xC1 functional and
# the checksum is the sum of the four preceding bytes. The question we measure: must
# it be ONE specific sequence, or do several work?
#
# State 2026-08-19: physical/F7, functional/F1 and functional/F7 have all made
# contact at least once — so no single specific sequence is required. physical/F1 has
# never succeeded (0 of 8 attempts), and broadcast to 0x33 is untested: it's the
# frame the muki01 reference uses (C1 33 F1 81 66) and it addresses all OBD modules
# functionally instead of SLABS's physical address 0x29.
VARIANTS = {
    "fysisk/F7":          (False, 0xF7, SLABS_ADDRESS),
    "funktionell/F1":     (True,  0xF1, SLABS_ADDRESS),
    "funktionell/F7":     (True,  0xF7, SLABS_ADDRESS),
    "fysisk/F1":          (False, 0xF1, SLABS_ADDRESS),
    "broadcast/33/F1":    (True,  0xF1, 0x33),   # muki01: C1 33 F1 81 66
    "broadcast/33/F7":    (True,  0xF7, 0x33),
}


def frame_for(variant: str) -> bytes:
    functional, source, target = VARIANTS[variant]
    return encode(b"\x81", target, source, addressed=True, functional=functional)


_log_fh = None
_jsonl = None


def say(msg: str) -> None:
    line = f"{dt.datetime.now().strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    if _log_fh:
        _log_fh.write(line + "\n")
        _log_fh.flush()


def record(**row) -> None:
    row["t"] = dt.datetime.now().isoformat(timespec="seconds")
    _jsonl.write(json.dumps(row, ensure_ascii=False) + "\n")
    _jsonl.flush()


def quiet(seconds: float) -> None:
    """Wait WITHOUT sending anything — every byte resets the module's wait."""
    if seconds > 0:
        time.sleep(seconds)


def td5_context(transport) -> "dict":
    """Short TD5 session: read rpm/speed/battery, end cleanly WITHOUT closing the port."""
    td5 = Td5(KWP2000(KLine(transport, target=0x13), tolerant=True))
    ctx: "dict" = {}
    try:
        td5.establish(attempts=2)
        vals = td5.read_all()
        ctx = {k: vals.get(k) for k in ("rpm", "speed", "battery")}
    except Exception as exc:  # noqa: BLE001
        ctx = {"td5_error": f"{type(exc).__name__}"}
    finally:
        try:
            td5.end_session()  # 20 + 82, the port is shared with the SLABS attempts
        except Exception:  # noqa: BLE001
            pass
    return ctx


def attempt(transport, variant: str, hold: float) -> "dict":
    """One init attempt + short hold period. Returns the measurement result as a dict."""
    functional, source, target = VARIANTS[variant]
    # Init goes to the target address (0x29 or broadcast 0x33); the session afterwards
    # is unaddressed, so the SLABS object talks to whichever module responded.
    kwp = KWP2000(KLine(transport, target=target), tolerant=True)
    slabs = Slabs(kwp)
    try:
        kwp.start_communication(tolerant=True, functional=functional, source=source)
    except KLineTimeout:
        return {"result": "silent"}
    except Exception as exc:  # noqa: BLE001
        return {"result": "local_error", "error": f"{type(exc).__name__}: {exc}"}
    # Acknowledgement: a C1 could be our own echo or noise. 1A 8A settles it.
    try:
        slabs.read_ecu_id(0x8A)
    except Exception:  # noqa: BLE001
        return {"result": "false_c1"}

    reads = misses = 0
    t0 = time.monotonic()
    while time.monotonic() - t0 < hold:
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
        else:
            misses += 1
            if misses >= 3:
                break
    try:
        slabs.end_session()  # 82 — don't leave the link open into the next attempt
    except Exception:  # noqa: BLE001
        pass
    return {"result": "hit", "reads": reads, "misses": misses,
            "held": round(time.monotonic() - t0, 1)}


def summarise(paths: "list[str]") -> int:
    """Read several runs together and cross-tabulate hit rate per power mode.

    The point of three modes (engine running / ignition with charger / ignition
    without): the charger gives high voltage WITHOUT the engine running, which
    separates voltage from engine status — the one question the 2026-08-19
    measurement couldn't answer.
    """
    rows = []
    for pattern in paths:
        for path in sorted(glob.glob(pattern)):
            with open(path, encoding="utf-8") as fh:
                rows += [json.loads(line) for line in fh if line.strip()]
    if not rows:
        print("no rows found")
        return 1

    # Back-compat: runs before 2026-08-21 wrote the result codes in Swedish. Map
    # them to the current English codes so older JSONL still summarises correctly.
    _LEGACY = {"träff": "hit", "tyst": "silent",
               "lokalt_fel": "local_error", "falsk_c1": "false_c1"}
    for r in rows:
        r["result"] = _LEGACY.get(r.get("result"), r.get("result"))

    def rate(rs):
        hits = sum(1 for r in rs if r.get("result") == "hit")
        return f"{hits:3}/{len(rs):-3} ({100 * hits / len(rs):3.0f}%)"

    print(f"{len(rows)} attempts from {len(paths)} patterns\n")
    for key, title in (("label", "power mode"), ("gap", "quiet period"),
                       ("variant", "variant"), ("td5_first", "TD5 first")):
        groups = defaultdict(list)
        for r in rows:
            groups[r.get(key)].append(r)
        if len(groups) < 2:
            continue
        print(f"  per {title}:")
        for k in sorted(groups, key=str):
            v = [r["battery"] for r in groups[k] if r.get("battery")]
            volt = f"   battery {min(v):.2f}–{max(v):.2f} V" if v else ""
            print(f"    {str(k):16} {rate(groups[k])}{volt}")
        print()
    return 0


def main() -> int:
    global _log_fh, _jsonl
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--serial", default="auto")
    ap.add_argument("--rounds", type=int, default=3, help="passes through the whole matrix")
    ap.add_argument("--gaps", default="5,15,30",
                    help="quiet periods to test, seconds (default 5,15,30)")
    ap.add_argument("--hold", type=float, default=15.0,
                    help="hold period on a hit, seconds (default 15)")
    ap.add_argument("--variants", default="fysisk/F7,funktionell/F1,funktionell/F7",
                    help=f"comma-separated. Available: {', '.join(VARIANTS)}")
    ap.add_argument("--td5", choices=("never", "always", "both"), default="both",
                    help="TD5 session before SLABS: never / always / both (default both)")
    ap.add_argument("--seed", type=int, default=None, help="seed for the order")
    ap.add_argument("--max-minutes", type=float, default=None,
                    help="stop after this many minutes (the engine shouldn't idle "
                         "unnecessarily). The result is summarized anyway.")
    ap.add_argument("--td5-every", type=int, default=5,
                    help="read engine context every Nth attempt instead of every one (default 5). "
                         "Saves ~7 s per attempt; the age of the context is logged.")
    ap.add_argument("--label", default="",
                    help="power mode for the run, e.g. engine / charger / ignition. "
                         "Saved on each row so the runs can be compared afterwards.")
    ap.add_argument("--summary", nargs="+", metavar="JSONL",
                    help="summarize earlier runs instead of measuring")
    args = ap.parse_args()

    if args.summary:
        return summarise(args.summary)

    gaps = [float(g) for g in args.gaps.split(",") if g.strip()]
    variants = [v.strip() for v in args.variants.split(",") if v.strip() in VARIANTS]
    td5_modes = {"never": [False], "always": [True], "both": [False, True]}[args.td5]
    seed = args.seed if args.seed is not None else int(time.time())
    rng = random.Random(seed)

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    os.makedirs("logs", exist_ok=True)
    _log_fh = open(f"logs/slabs_torture-{stamp}.log", "w", encoding="utf-8")
    _jsonl = open(f"logs/slabs_torture-{stamp}.jsonl", "w", encoding="utf-8")

    trials = [(g, v, t) for g in gaps for v in variants for t in td5_modes] * args.rounds
    rng.shuffle(trials)   # shuffled order: time/temperature shouldn't track the state

    # rough estimate: quiet period + init + optional hold period + breathing, plus the
    # TD5 context which is now only read every Nth attempt
    per_td5 = 7.0 / max(1, args.td5_every)
    est = sum(g + 2 + args.hold * 0.3 + 1 + per_td5 for g, _, t in trials) / 60
    say(f"SLABS torture {stamp} — seed {seed}" + (f" — mode: {args.label}" if args.label else ""))
    say(f"{len(trials)} attempts · gap {gaps} · variants {variants} · TD5 {td5_modes}")
    budget = f" (stops after {args.max_minutes:.0f} min)" if args.max_minutes else ""
    say(f"estimated time: ~{est:.0f} min{budget}. Stationary. Ctrl-C saves the result.")

    try:
        port = resolve_serial_port(args.serial)
    except FileNotFoundError as exc:
        say(f"no cable: {exc}")
        return 1
    transport = LoggingTransport(SerialTransport(port, timeout=1.0),
                                 logfile=f"logs/slabs_torture-{stamp}.raw.log")
    try:
        transport.open()
    except Exception as exc:  # noqa: BLE001
        say(f"could not open {port}: {exc}")
        return 1

    results = []
    t_start = time.monotonic()
    last_ctx: "dict" = {}
    last_ctx_at = 0.0
    try:
        for i, (gap, variant, use_td5) in enumerate(trials, 1):
            if args.max_minutes and (time.monotonic() - t_start) / 60 >= args.max_minutes:
                say(f"\ntime budget ({args.max_minutes:.0f} min) spent — stopping here. "
                    f"Run more blocks later and merge with --summary.")
                break
            # The engine context costs ~7 s. Read it every Nth attempt and reuse it
            # in between — the voltage moves slowly, and the age is logged.
            if use_td5 and (i == 1 or (i - 1) % max(1, args.td5_every) == 0):
                last_ctx = td5_context(transport)
                last_ctx_at = time.monotonic()
            ctx = dict(last_ctx) if use_td5 else {}
            if ctx:
                ctx["ctx_age"] = round(time.monotonic() - last_ctx_at, 1)
            quiet(gap)
            r = attempt(transport, variant, args.hold)
            row = {"n": i, "label": args.label, "gap": gap, "variant": variant,
                   "td5_first": use_td5, **ctx, **r}
            results.append(row)
            record(**row)
            rpm = ctx.get("rpm")
            motor = "?" if rpm is None else ("running" if rpm else "off")
            say(f"[{i:3}/{len(trials)}] gap {gap:4.0f}s · {variant:15} · td5 "
                f"{'yes' if use_td5 else 'no '} · engine {motor:7} → {r['result']}"
                + (f"  ({r.get('reads')} reads)" if r.get("result") == "hit" else ""))
            if r["result"] == "local_error":
                say(f"   ✗ aborting: {r.get('error')}")
                break
            quiet(1.0)  # let the bus breathe between attempts
    except KeyboardInterrupt:
        say("\naborted — summarizing what we managed to measure")
    finally:
        try:
            transport.close()
        except Exception:  # noqa: BLE001
            pass

    say("\n=== SUMMARY ===")
    if not results:
        return 1

    def rate(rows):
        hits = sum(1 for r in rows if r["result"] == "hit")
        return f"{hits}/{len(rows)} ({100 * hits / len(rows):.0f}%)"

    for label, key in (("quiet period", "gap"), ("variant", "variant"),
                       ("TD5 first", "td5_first")):
        groups = defaultdict(list)
        for r in results:
            groups[r[key]].append(r)
        say(f"\n  per {label}:")
        for k in sorted(groups, key=str):
            say(f"    {str(k):16} {rate(groups[k])}")

    with_rpm = [r for r in results if r.get("rpm") is not None]
    if with_rpm:
        say("\n  per engine mode (attempts with TD5 context only):")
        for on in (True, False):
            rows = [r for r in with_rpm if bool(r["rpm"]) is on]
            if rows:
                v = [r["battery"] for r in rows if r.get("battery")]
                volt = f"  battery {min(v):.2f}–{max(v):.2f} V" if v else ""
                say(f"    {'running' if on else 'off':16} {rate(rows)}{volt}")

    held = [r for r in results if r["result"] == "hit"]
    if held:
        say(f"\n  stability: {sum(r['reads'] for r in held)} reads, "
            f"{sum(r['misses'] for r in held)} dropped in {len(held)} sessions")
    say(f"\nraw data: logs/slabs_torture-{stamp}.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
