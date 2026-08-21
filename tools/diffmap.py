"""Active differential mapping — read → change ONE thing → read → auto-diff → save.

Requires a TRANSMITTING cable. The tool **only reads** (``21 xx`` + establish +
keepalive) via a read-only proxy (:class:`ReadOnlyEcu`) — the operator provokes
the input themselves (press the brake, lift a corner, toggle transport mode).
Actuators/clear/writes are unreachable here by construction (so airbag pyro and
BCU 3B cannot be triggered by accident).

Flow per field:
  1. read N baseline readings of a candidate LID set
  2. the operator changes one physical thing and presses Enter
  3. ``stable_diff`` shows which byte/bit moved (stable-then-changed)
  4. the operator labels it (a numeric value, or a state text)
  5. ``automap.solve`` → mapping → save as a candidate in the signal store

    PYTHONPATH=src python3 tools/diffmap.py slabs /dev/cu.usbserial-XXXX
    PYTHONPATH=src python3 tools/diffmap.py td5   /dev/cu.usbserial-XXXX --lids 1e,36
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from d2diag.sniff import automap  # noqa: E402
from d2diag.signals import upsert_field  # noqa: E402

# Read-only candidate LIDs per module (input/switch/settings — never actuators).
_CANDIDATES = {
    "slabs": [0x53, 0x54, 0x55, 0x43, 0x44, 0x49, 0x50, 0x57,
              0x42, 0x48, 0x56, 0x58, 0x45, 0x46, 0x59],
    "td5": [0x1E, 0x36, 0x1D, 0x30, 0x32, 0x3D],
}


# --------------------------------------------------------------------------- #
# Pure logic (unit-tested — no I/O)
# --------------------------------------------------------------------------- #
def moved(baselines, after, lids):
    """Stable-then-changed bytes (noise-hardened). ``lids`` = list of hex keys."""
    return automap.stable_diff(baselines, after, lids)


def solve_label(samples, lids, name="signal", unit=""):
    """Run automap.solve on labeled readings → mapping proposal."""
    return automap.solve(samples, lids, name, unit)


def build_record(res, name, unit="", confidence="kandidat", source=""):
    """Build a signal-store record from an ``automap.solve`` result."""
    rec = {"name": name, "lid": res["lid"], "offset": int(res["offset"]),
           "unit": unit, "confidence": confidence, "source": source}
    if res.get("mode") == "state" or "mapping" in res:
        # mapping: {state label: raw value} → states: {raw value: label}
        states = {int(v): k for k, v in res["mapping"].items()}
        if res.get("bit") is not None:
            rec.update(kind="bit", bit=int(res["bit"]), states=states)
        else:
            rec.update(kind="u8", states=states)
    else:
        rec.update(kind=res["kind"], scale=float(res["scale"]),
                   bias=float(res.get("bias", 0.0)))
    return rec


# --------------------------------------------------------------------------- #
# Read-only proxy — safety boundary
# --------------------------------------------------------------------------- #
class ReadOnlyEcu:
    """Exposes ONLY reading: establish/read_block/read_local/tester_present/
    open/close. Everything else (actuators, clear, 3B write) raises AttributeError → a
    future edit cannot sneak in a write path via the harness."""

    _ALLOWED = ("establish", "read_block", "read_local", "tester_present", "open", "close")

    def __init__(self, session) -> None:
        object.__setattr__(self, "_s", session)

    def __getattr__(self, name):
        if name in self._ALLOWED:
            return getattr(self._s, name)
        raise AttributeError(f"ReadOnlyEcu does not allow {name!r} (read-only harness)")


# --------------------------------------------------------------------------- #
# I/O + interactive CLI
# --------------------------------------------------------------------------- #
def _open_session(module: str, port: str) -> ReadOnlyEcu:
    from d2diag.kline import KLine
    from d2diag.kwp2000 import KWP2000
    from d2diag.transport import SerialTransport

    tp = SerialTransport(port, timeout=1.0)
    if module == "slabs":
        from d2diag.slabs import SLABS_ADDRESS, Slabs
        sess = Slabs(KWP2000(KLine(tp, target=SLABS_ADDRESS), tolerant=True))
    else:
        from d2diag.td5 import Td5
        sess = Td5(KWP2000(KLine(tp), tolerant=True))
    ro = ReadOnlyEcu(sess)
    ro.open()
    ro.establish()
    return ro


def _read_baselines(ecu: ReadOnlyEcu, lids, n: int) -> "list[dict]":
    out = []
    for _ in range(n):
        out.append({"raws": ecu.read_block(lids)})
        ecu.tester_present()
    return out


def _hexkeys(lids) -> "list[str]":
    return [f"{x:02x}" for x in lids]


def run(module: str, port: str, lids, baselines: int) -> int:
    keys = _hexkeys(lids)
    print(f"{module.upper()}: connecting (read-only) on {port} …")
    ecu = _open_session(module, port)
    print(f"  ✓ connected. Candidate LIDs: {' '.join(keys)}")
    print("  The harness WRITES nothing — you provoke the input yourself.\n")
    try:
        while True:
            name = input("Field name (empty = quit): ").strip()
            if not name:
                break
            unit = input("Unit (e.g. V, mm — empty for a state field): ").strip()
            input(f"Keep everything still. Enter for {baselines} baseline reads …")
            bases = _read_baselines(ecu, lids, baselines)
            samples = []
            while True:
                input("Change ONE thing, hold it, press Enter (reads) …")
                after = {"raws": ecu.read_block(lids)}
                mv = moved(bases, after, keys)
                if mv:
                    print("  moved:", ", ".join(
                        f"21{m['lid']} byte{m['byte']} {m['baseline']}→{m['after']}" for m in mv))
                else:
                    print("  (nothing stable moved — try again or a clearer input)")
                label = input("  Value/state read in reference tool (empty = done with the field): ").strip()
                if not label:
                    break
                samples.append({"text": label, "raws": after["raws"]})
            if not samples:
                continue
            res = solve_label(samples, keys, name, unit)
            if not res.get("ok"):
                print("  ✗", res.get("error", "could not solve"), "\n")
                continue
            if res.get("mode") == "numeric":
                print(f"  → {name}: 21{res['lid']} @{res['offset']} {res['kind']} "
                      f"×{res['scale']} +{res['bias']} (R²={res.get('r2', 0):.3f})")
            else:
                print(f"  → {name}: {res.get('rule', '')}")
            if input("  Save as a candidate in the store? [y/n]: ").strip().lower() in ("y", "yes", "j", "ja"):
                rec = build_record(res, name, unit, "kandidat",
                                   source=f"diffmap {module}: differential, {len(samples)} readings")
                upsert_field(module, rec)
                print(f"  ✓ saved to signals/{module}.json\n")
            else:
                print()
    finally:
        ecu.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Active differential mapping (read-only)")
    ap.add_argument("module", choices=["td5", "slabs"])
    ap.add_argument("port")
    ap.add_argument("--lids", help="comma-separated hex LIDs (otherwise the module default set)")
    ap.add_argument("--baselines", type=int, default=3, help="number of baseline reads (default 3)")
    args = ap.parse_args()
    lids = [int(x, 16) for x in args.lids.split(",")] if args.lids else _CANDIDATES[args.module]
    try:
        return run(args.module, args.port, lids, args.baselines)
    except (KeyboardInterrupt, EOFError):
        print("\naborted.")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"\nERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("Check: right port? ignition on? transmitting cable? vehicle stationary?", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
