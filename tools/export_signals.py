"""Migration: dump the current td5.identifiers literal → signals/td5.json.

One-shot (and idempotent) dev tool. Reads the hand-coded ``SIGNALS``/``LIMITS``
and writes the declarative store, with curated confidence/source per field (what
used to live in code comments). Run once; after that the JSON is the source of truth.

    PYTHONPATH=src python3 tools/export_signals.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from d2diag.td5.identifiers import LIMITS, SIGNALS  # noqa: E402

# Curated confidence + source per signal (from code comments/log verification).
# Default if not listed: ("kandidat", "").
ANNOT: "dict[str, tuple[str, str]]" = {
    "rpm":            ("belagt", "fuelling verified against the car (RDL 016)"),
    "speed":          ("belagt", "fuelling verified against the car"),
    "battery":        ("belagt", "u16/1000 V, verified against the car"),
    "coolant_temp":   ("belagt", "21 1A@0 u16/10−273.2; verified 2026-08-03 (59.2 °C)"),
    "air_temp":       ("belagt", "21 1A@4, same temp scale"),
    "ext_temp":       ("kandidat", "sensor NOT fitted → constant 0x1088=150 °C (unconnected)"),
    "fuel_temp":      ("belagt", "21 1A@12, same temp scale"),
    "accel_way1":     ("belagt", "21 1B@0 u16/1000 V; sniffed 2026-08-08"),
    "accel_way2":     ("belagt", "21 1B@2 u16/1000 V"),
    "accel_way3":     ("kandidat", "21 1B@4; third voltage track, scale not confirmed (0 V in capture)"),
    "accel_supply":   ("belagt", "21 1B@6 u16/1000 V (5V reference)"),
    "manifold_press": ("belagt", "21 1C@0 u16/10000 bar; CONFIRMED 2026-08-03 (1.0→1.2 bar)"),
    "maf_raw":        ("kandidat", "21 1C@4; no MAF on early ROM — raw field, do not interpret as mg"),
    "rpm_error":      ("kandidat", "21 21@0 s16; idle control error"),
    "ambient_press_1": ("belagt", "21 23@0 u16/10000 bar"),
    "ambient_press_2": ("belagt", "21 23@2 u16/10000 bar"),
    "balance_1":      ("kandidat", "21 40@0 s16; cylinder balance 1"),
    "balance_2":      ("kandidat", "21 40@2 s16; cylinder balance 2"),
    "balance_3":      ("kandidat", "21 40@4 s16; cylinder balance 3"),
    "balance_4":      ("kandidat", "21 40@6 s16; cylinder balance 4"),
    "balance_5":      ("kandidat", "21 40@8 s16; cylinder balance 5"),
}


def main() -> int:
    rows = []
    for s in SIGNALS:
        conf, src = ANNOT.get(s.name, ("kandidat", ""))
        rows.append({
            "name": s.name,
            "lid": f"{s.lid:02X}",
            "offset": s.offset,
            "kind": s.kind,
            "scale": s.scale,
            "bias": s.bias,
            "unit": s.unit,
            "confidence": conf,
            "limits": list(LIMITS[s.name]) if s.name in LIMITS else None,
            "source": src,
        })
    out = os.path.join(os.path.dirname(__file__), "..", "src", "d2diag", "signals", "td5.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"wrote {len(rows)} signals → {os.path.relpath(out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
