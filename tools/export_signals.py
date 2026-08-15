"""Migrering: dumpa nuvarande td5.identifiers-literal → signals/td5.json.

Engångs- (och idempotent) devverktyg. Läser den handkodade ``SIGNALS``/``LIMITS``
och skriver den deklarativa storen, med kurerad konfidens/källa per fält (det som
tidigare låg i kodkommentarer). Kör en gång; därefter är JSON:en sanningskällan.

    PYTHONPATH=src python3 tools/export_signals.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from d2diag.td5.identifiers import LIMITS, SIGNALS  # noqa: E402

# Kurerad konfidens + källa per signal (ur kodkommentarer/loggverifiering).
# Default om ej listad: ("kandidat", "").
ANNOT: "dict[str, tuple[str, str]]" = {
    "rpm":            ("belagt", "fuelling verifierat mot bilen (RDL 016)"),
    "speed":          ("belagt", "fuelling verifierat mot bilen"),
    "battery":        ("belagt", "u16/1000 V, verifierat mot bilen"),
    "coolant_temp":   ("belagt", "21 1A@0 u16/10−273.2; verifierat 2026-08-03 (59.2 °C)"),
    "air_temp":       ("belagt", "21 1A@4, samma temp-skala"),
    "ext_temp":       ("kandidat", "givare EJ monterad → konstant 0x1088=150 °C (oansluten)"),
    "fuel_temp":      ("belagt", "21 1A@12, samma temp-skala"),
    "accel_way1":     ("belagt", "21 1B@0 u16/1000 V; sniffat 2026-08-08"),
    "accel_way2":     ("belagt", "21 1B@2 u16/1000 V"),
    "accel_way3":     ("kandidat", "21 1B@4; tredje spänningsspår, skala ej bekräftad (0 V i fångst)"),
    "accel_supply":   ("belagt", "21 1B@6 u16/1000 V (5V-referens)"),
    "manifold_press": ("belagt", "21 1C@0 u16/10000 bar; BEKRÄFTAT 2026-08-03 (1.0→1.2 bar)"),
    "maf_raw":        ("kandidat", "21 1C@4; ingen MAF på tidig ROM — rått fält, tolka ej som mg"),
    "rpm_error":      ("kandidat", "21 21@0 s16; idle-reglerfel"),
    "ambient_press_1": ("belagt", "21 23@0 u16/10000 bar"),
    "ambient_press_2": ("belagt", "21 23@2 u16/10000 bar"),
    "balance_1":      ("kandidat", "21 40@0 s16; cylinderbalans 1"),
    "balance_2":      ("kandidat", "21 40@2 s16; cylinderbalans 2"),
    "balance_3":      ("kandidat", "21 40@4 s16; cylinderbalans 3"),
    "balance_4":      ("kandidat", "21 40@6 s16; cylinderbalans 4"),
    "balance_5":      ("kandidat", "21 40@8 s16; cylinderbalans 5"),
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
    print(f"skrev {len(rows)} signaler → {os.path.relpath(out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
