"""Interactive differential INPUT mapper (read-only).

Wiggle-watch: connect to a module, poll a set of switch/input LIDs continuously, and print a
change event whenever a bit flips — so you toggle a physical input (open a door, turn the key)
and see exactly which `LID byteN bitM` moves. Continuous polling keeps the session alive (no
"press Enter" that would time it out). On Ctrl-C it lists every bit that moved and lets you label
them; labels are written to the signal store as `kandidat`.

    PYTHONPATH=src python3 tools/map_inputs.py bcu   /dev/cu.usbserial-0001 --esp
    PYTHONPATH=src python3 tools/map_inputs.py td5   /dev/cu.usbserial-XXXX
    PYTHONPATH=src python3 tools/map_inputs.py slabs /dev/cu.usbserial-XXXX --lids 56,42,48,58

Read-only: sends only `21 xx` reads, never a write. See references/input_mapper_design.md.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from d2diag.kline import KLine  # noqa: E402
from d2diag.kwp2000 import KWP2000  # noqa: E402
from d2diag.signals import upsert_field  # noqa: E402
from d2diag.transport import EspTransport, SerialTransport  # noqa: E402

# Default input/switch LID sets per module (hex). Overridable with --lids.
_DEFAULT_LIDS = {
    "bcu": list(range(0x20, 0x2A)) + [0x2C, 0x2D] + list(range(0xD8, 0xEA)),  # inputs (valeo doc)
    "td5": [0x1E, 0x1F, 0x20, 0x36],                                          # switch bitfields
    "slabs": [0x56, 0x42, 0x48, 0x58],                                        # ABS/SLS switches
}


# ---- pure logic (testable without hardware) -------------------------------- #
def bits_of(frame: "dict[str, bytes]") -> "dict[tuple, int]":
    """Explode a frame ``{lid_hex: bytes}`` into ``{(lid, offset, bit): 0|1}``."""
    out = {}
    for lid, data in frame.items():
        for off, byte in enumerate(data):
            for bit in range(8):
                out[(lid, off, bit)] = (byte >> bit) & 1
    return out


def volatile_bits(samples: "list[dict[str, bytes]]") -> "set[tuple]":
    """Bits that are NOT constant across the baseline samples → counters/analog noise, masked."""
    if not samples:
        return set()
    exploded = [bits_of(s) for s in samples]
    keys = set(exploded[0])
    for e in exploded[1:]:
        keys &= set(e)
    return {k for k in keys if len({e[k] for e in exploded}) > 1}


def stable_bits(samples: "list[dict[str, bytes]]", mask: "set[tuple]") -> "dict[tuple, int]":
    """Debounced value per bit = the mode over the samples, excluding masked/absent bits."""
    if not samples:
        return {}
    exploded = [bits_of(s) for s in samples]
    keys = set(exploded[0])
    for e in exploded[1:]:
        keys &= set(e)
    out = {}
    for k in keys - mask:
        ones = sum(e[k] for e in exploded)
        out[k] = 1 if ones * 2 > len(exploded) else 0
    return out


def changed_bits(ref: "dict[tuple, int]", cur: "dict[tuple, int]") -> "list[tuple]":
    """(lid, offset, bit, ref, cur) for bits present in both that differ."""
    return [(lid, off, bit, ref[(lid, off, bit)], v)
            for (lid, off, bit), v in cur.items()
            if (lid, off, bit) in ref and ref[(lid, off, bit)] != v]


# ---- I/O ------------------------------------------------------------------- #
def _transport(port: str, esp: bool):
    return EspTransport(port, ready_timeout=30.0) if esp else SerialTransport(port, timeout=1.0)


def _establish(module: str, port: str, esp: bool):
    """Return an established module session with read_block()."""
    t = _transport(port, esp)
    if module == "td5":
        from d2diag.td5 import Td5
        s = Td5(KWP2000(KLine(t), tolerant=True))
    elif module == "slabs":
        from d2diag.slabs import SLABS_ADDRESS, Slabs
        s = Slabs(KWP2000(KLine(t, target=SLABS_ADDRESS), tolerant=True))
    elif module == "bcu":
        from d2diag.bcu import BCU_ADDRESS, Bcu
        s = Bcu(KWP2000(KLine(t, target=BCU_ADDRESS), tolerant=True))
    else:
        raise SystemExit(f"unknown module {module!r}")
    s.open()
    print(f"{module.upper()}: establishing…", file=sys.stderr)
    s.establish()
    print("  ✓ established", file=sys.stderr)
    return s


def main() -> int:
    ap = argparse.ArgumentParser(description="Interactive differential input mapper (read-only)")
    ap.add_argument("module", choices=sorted(_DEFAULT_LIDS))
    ap.add_argument("port")
    ap.add_argument("--esp", action="store_true", help="talk over an ESP32 in cable mode")
    ap.add_argument("--lids", help="comma-separated hex LIDs to poll (overrides the default set)")
    ap.add_argument("--baseline", type=float, default=3.0, help="seconds of quiet baseline (default 3)")
    ap.add_argument("--period", type=float, default=0.4, help="poll period, seconds (default 0.4)")
    args = ap.parse_args()

    lids = ([int(x, 16) for x in args.lids.replace(" ", "").split(",")]
            if args.lids else _DEFAULT_LIDS[args.module])

    s = _establish(args.module, args.port, args.esp)
    seen: "dict[tuple, list]" = {}   # (lid,off,bit) -> [event strings], for labelling at the end
    try:
        # Baseline: sample while the operator touches nothing, then mask self-changing bits.
        print(f"\nBaseline ({args.baseline:.0f}s) — leave everything at rest, don't touch anything…")
        base = []
        t0 = time.time()
        while time.time() - t0 < args.baseline:
            base.append(s.read_block(lids))
            time.sleep(args.period)
        mask = volatile_bits(base)
        ref = stable_bits(base, mask)
        print(f"  masked {len(mask)} noisy bit(s); watching {len(ref)} stable bit(s) across "
              f"{len(lids)} LIDs.\n")
        print("WIGGLE something (open a door, turn the key…). Ctrl-C when done.\n")

        # Watch: continuous poll (keeps the session alive), debounced change events.
        window: "list[dict[str, bytes]]" = []
        while True:
            window.append(s.read_block(lids))
            window = window[-3:]                       # 3-frame debounce
            cur = stable_bits(window, mask)
            for lid, off, bit, was, now in changed_bits(ref, cur):
                key = (lid, off, bit)
                ev = f"21 {lid.upper()} byte{off} bit{bit}: {was}->{now}"
                print(f"  [t+{time.time()-t0:5.1f}s] {ev}")
                seen.setdefault(key, []).append(f"{was}->{now}")
                ref[key] = now                          # track new resting level → catch the return too
            time.sleep(args.period)
    except KeyboardInterrupt:
        print("\n\nstopped.")
    finally:
        s.close()

    if not seen:
        print("No bits changed — nothing to label.")
        return 0

    # Label + write. Session is closed now, so a slow prompt can't time it out.
    print(f"\n{len(seen)} bit(s) moved. Label them (blank = skip):")
    for (lid, off, bit), events in sorted(seen.items()):
        roundtrip = any("0->1" in events) and any("1->0" in events)
        tag = "round-trip ✓" if roundtrip else "one-way only"
        name = input(f"  21 {lid.upper()} byte{off} bit{bit} [{' '.join(events)}] ({tag}) name: ").strip()
        if not name:
            continue
        upsert_field(args.module, {
            "name": name, "lid": lid, "offset": off, "kind": "bit", "bit": bit,
            "scale": 1.0, "bias": 0.0, "unit": "", "confidence": "kandidat",
            "states": {"0": "off", "1": "on"},
            "source": f"differential map ({' '.join(events)}"
                      f"{'; round-trip' if roundtrip else ''}) — {args.module} 21 {lid.upper()} b{off}.{bit}",
        })
        print(f"    → wrote '{name}' to {args.module}.json (kandidat)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
