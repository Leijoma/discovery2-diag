#!/usr/bin/env python3
"""Generate the ESP32 decode table from the signal store — one source of truth.

The ESP firmware used to hand-copy `signals/td5.json` into a C `FIELDS[]` array. That
duplication is exactly what drifted during the MAF remap (the store said one thing, the
sketch another). This tool emits `esp32/kline_node/signals_td5.h` from the store, so the
ESP's offsets/scales/bias always track `signals/td5.json`.

The ESP logs a curated subset under short, Influx-friendly keys (e.g. `coolant_c` for the
store's `coolant_temp`); that mapping lives in `_FIELDS` below. Everything else — lid,
offset, kind, scale, bias — comes from the store.

    python3 tools/gen_signal_header.py            # write the header
    python3 tools/gen_signal_header.py --check     # fail if the header is stale (CI/tests)
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from d2diag.signals import load_signals  # noqa: E402

_HEADER_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "esp32", "kline_node", "signals_td5.h")

# ESP key  <-  store signal name. Order = the order fields appear in the C table.
# The ESP logs this curated subset; the sweep LIDs (1E/1F/20/36) are raw-only, not here.
_FIELDS = [
    ("rpm",           "rpm"),
    ("speed",         "speed"),
    ("battery",       "battery"),
    ("coolant_c",     "coolant_temp"),
    ("air_c",         "air_temp"),
    ("fuel_c",        "fuel_temp"),
    ("throttle_v",    "accel_way1"),
    ("map_bar",       "manifold_press"),
    ("maf",           "maf"),
    ("inj_mg",        "injection_qty"),
    ("egr_pct",       "egr_modulator"),
    ("wastegate_pct", "wastegate_modulator"),
    ("rpm_error",     "rpm_error"),
    ("ambient_bar",   "ambient_press_1"),
    ("balance_1",     "balance_1"),
    ("balance_2",     "balance_2"),
    ("balance_3",     "balance_3"),
    ("balance_4",     "balance_4"),
    ("balance_5",     "balance_5"),
]

_KIND = {"u8": "U8", "u16": "U16", "s16": "S16"}


def _fmt_float(v: float) -> str:
    """Compact but faithful C float literal (always has a '.' so it's not read as `1f`)."""
    s = f"{v:.9g}"
    if "." not in s and "e" not in s and "E" not in s:
        s += ".0"
    return s + "f"


def build_header() -> str:
    # Fuel-computer constants live with the Python _FuelComputer; emit them so the ESP's
    # on-node fuel calc can't drift from it (the header-match test guards this).
    from d2diag.web.sources import _INJ_PER_REV, _DIESEL_G_PER_L
    by_name = {s.name: s for s in load_signals("td5")}
    rows = []
    lids: "list[int]" = []
    for key, store_name in _FIELDS:
        sig = by_name.get(store_name)
        if sig is None:
            raise SystemExit(f"gen_signal_header: '{store_name}' not in signals/td5.json")
        if sig.kind not in _KIND:
            raise SystemExit(f"gen_signal_header: kind '{sig.kind}' ({store_name}) unsupported")
        rows.append(
            f'  {{ "{key}", 0x{sig.lid:02X}, {sig.offset:2d}, {_KIND[sig.kind]:3s}, '
            f'{_fmt_float(sig.scale):>13s}, {_fmt_float(sig.bias):>10s} }},')
        if sig.lid not in lids:
            lids.append(sig.lid)
    lid_list = ", ".join(f"0x{l:02X}" for l in sorted(lids))
    body = "\n".join(rows)
    return (
        "// AUTO-GENERATED from src/d2diag/signals/td5.json by tools/gen_signal_header.py.\n"
        "// DO NOT EDIT. Regenerate: python3 tools/gen_signal_header.py\n"
        "// The ESP decode table is derived from the signal store so the two never drift.\n"
        "// Requires `enum Kind { U8, U16, S16 };` and `struct Field { … };` before include.\n"
        "\n"
        "static const Field FIELDS[] = {\n"
        f"{body}\n"
        "};\n"
        "static const size_t NFIELDS = sizeof FIELDS / sizeof FIELDS[0];\n"
        "\n"
        "// Unique LIDs to read each cycle (derived from FIELDS above).\n"
        f"static const uint8_t LIDS[] = {{ {lid_list} }};\n"
        "static const size_t  NLIDS  = sizeof LIDS / sizeof LIDS[0];\n"
        "\n"
        "// Fuel-computer constants — kept in sync with _FuelComputer (src/d2diag/web/sources.py).\n"
        f"#define INJ_PER_REV    {_fmt_float(_INJ_PER_REV)}   // injections per crank rev (5-cyl 4-stroke)\n"
        f"#define DIESEL_G_PER_L {_fmt_float(_DIESEL_G_PER_L)}   // diesel density\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero if the on-disk header differs from freshly generated")
    args = ap.parse_args()
    generated = build_header()
    path = os.path.normpath(_HEADER_PATH)
    if args.check:
        current = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
        if current != generated:
            print(f"STALE: {path} differs from signals/td5.json — run tools/gen_signal_header.py")
            return 1
        print(f"ok: {path} matches the signal store")
        return 0
    with open(path, "w", encoding="utf-8") as f:
        f.write(generated)
    print(f"wrote {path} ({len(_FIELDS)} fields)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
