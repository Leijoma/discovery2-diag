"""Passiv sniff-kalibrering: frame-parsning, LID-lager och skala/offset-solver."""
from __future__ import annotations

from d2diag.sniff import LidStore, parse_hex_line, solve_linear, suggest_signal


def test_parse_hex_line_and_markers():
    assert parse_hex_line("[    56921] 02 21 09 2c 04 61 09 02 fa 6a") == \
        [0x02, 0x21, 0x09, 0x2c, 0x04, 0x61, 0x09, 0x02, 0xfa, 0x6a]
    assert parse_hex_line(">>> read fuelling") is None
    assert parse_hex_line("=== SESSION ... ===") is None


def test_lidstore_tracks_module_and_decodes_td5():
    st = LidStore()
    st.ingest_line("[  8773] 81 13 f7 81 0c")          # TD5 fast init
    st.ingest_line("[ 56921] 02 21 09 2c 04 61 09 02 fa 6a")  # 21 09 → rpm
    snap = st.snapshot()
    assert snap["module"] == "td5"
    lid09 = next(l for l in snap["lids"] if l["lid"] == "09")
    assert lid09["raw"] == "02 fa"
    rpm = next(s for s in lid09["decode"] if s["name"] == "rpm")
    assert rpm["value"] == 762


def test_lidstore_switches_to_slabs():
    st = LidStore()
    st.ingest_line("[ 100] 81 29 f7 81 22")            # SLABS fast init
    st.ingest_line("[ 200] 02 21 54 79 04 61 54 07 08 aa")  # 21 54 → höjder
    snap = st.snapshot()
    assert snap["module"] == "slabs"
    lid54 = next(l for l in snap["lids"] if l["lid"] == "54")
    hl = next(s for s in lid54["decode"] if s["name"] == "height_left")
    assert hl["value"] == 0x07


def test_solve_linear_battery_points():
    # rå 0x35ab=13739 → 13.739 V ; rå 0x2d94=11668 → 11.67 V  (skala ~1/1000)
    fit = solve_linear([(13739, 13.739), (11668, 11.668)])
    assert fit is not None
    assert abs(fit["scale"] - 0.001) < 1e-5
    assert abs(fit["bias"]) < 1e-3
    assert fit["r2"] > 0.999


def test_solve_linear_needs_two_distinct():
    assert solve_linear([(5, 1.0)]) is None
    assert solve_linear([(5, 1.0), (5, 2.0)]) is None  # samma rå → ingen lutning


def test_suggest_signal_formats_common_fraction():
    s = suggest_signal("battery", 0x10, 0, "u16", 0.001, 0.0, "V")
    assert s == 'Signal("battery", 0x10, 0, scale=1 / 1000, unit="V")'
    s2 = suggest_signal("speed", 0x0D, 0, "u8", 1.0, 0.0, "km/h")
    assert s2 == 'Signal("speed", 0x0D, 0, "u8", unit="km/h")'
