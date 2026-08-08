"""Passiv sniff-kalibrering: frame-parsning, LID-lager och skala/offset-solver."""
from __future__ import annotations

from d2diag.sniff import LidStore, parse_hex_line, solve_linear, suggest_signal
from d2diag.sniff.automap import solve as automap_solve


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


def test_slabs_any_door_decoded():
    st = LidStore()
    st.ingest_line("[ 1] 81 29 f7 81 22")
    st.ingest_line("[ 2] 00 06 61 56 01 0f 0f 0f ed")   # byte0 bit0 = 1 → öppen
    door = next(s for l in st.snapshot()["lids"] if l["lid"] == "56" for s in l["decode"] if s["name"] == "any_door")
    assert door["value"] == "öppen"
    st.ingest_line("[ 3] 00 06 61 56 00 0f 0f 0f ec")   # byte0 bit0 = 0 → stängd
    door = next(s for l in st.snapshot()["lids"] if l["lid"] == "56" for s in l["decode"] if s["name"] == "any_door")
    assert door["value"] == "stängd"


def test_menu_items_carry_lid_bindings():
    from d2diag.menus import MENUS
    fuel = next(g for g in MENUS["td5"] if "Fuelling" in g["cat"])
    rpm = next(i for i in fuel["items"] if i["name"].endswith("Engine Speed (rpm)"))
    assert rpm["lid"] == "09" and rpm["sig"] == "rpm"
    door = next(i for g in MENUS["slabs"] if "Switchar" in g["cat"] for i in g["items"] if i["name"].startswith("Any Door"))
    assert door["lid"] == "56" and door["sig"] == "any_door"


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


def test_automap_numeric_finds_battery_field():
    # två klartext-avläsningar (motor av / igång) + råblock för LID 10
    r = automap_solve(
        [{"text": "11.67", "raws": {"10": "2d 94 2d af"}},
         {"text": "13.82", "raws": {"10": "35 fa 36 1a"}}],
        ["10"], name="battery", unit="V",
    )
    assert r["ok"] and r["mode"] == "numeric"
    assert r["lid"] == "10" and r["offset"] == 0 and r["kind"] == "u16"
    assert abs(r["scale"] - 0.001) < 1e-6 and r["r2"] > 0.999
    assert r["signal"] == 'Signal("battery", 0x10, 0, scale=1 / 1000, unit="V")'


def test_automap_numeric_finds_temperature_with_bias():
    # kylvätsketemp ur 21 1A@0: (u16/10 − 273.2). 59.2 °C vs 58.2 °C
    r = automap_solve(
        [{"text": "59.2", "raws": {"1a": "0c fc 04 f1 0c b1 05 eb 10 88 00 04 0c 95 06 51"}},
         {"text": "58.2", "raws": {"1a": "0c f2 05 0f 0c 89 06 82 10 88 00 04 0c a4 06 17"}}],
        ["1a"], name="coolant_temp", unit="°C",
    )
    assert r["ok"] and r["offset"] == 0 and r["kind"] == "u16"
    assert abs(r["scale"] - 0.1) < 1e-6 and abs(r["bias"] + 273.2) < 0.5


def test_automap_state_finds_door_bit():
    r = automap_solve(
        [{"text": "öppen", "raws": {"56": "01 0f 0f 0f"}},
         {"text": "stängd", "raws": {"56": "00 0f 0f 0f"}}],
        ["56"],
    )
    assert r["ok"] and r["mode"] == "state"
    assert r["lid"] == "56" and r["offset"] == 0 and r["bit"] == 0
    assert r["mapping"] == {"öppen": 1, "stängd": 0}


def test_automap_single_reading_guesses_clean_scale():
    r = automap_solve([{"text": "13.74", "raws": {"10": "35 ab 35 da"}}], ["10"], "battery", "V")
    assert r["ok"] and abs(r["scale"] - 0.001) < 1e-6 and r["how"] == "guess"


def test_suggest_signal_formats_common_fraction():
    s = suggest_signal("battery", 0x10, 0, "u16", 0.001, 0.0, "V")
    assert s == 'Signal("battery", 0x10, 0, scale=1 / 1000, unit="V")'
    s2 = suggest_signal("speed", 0x0D, 0, "u8", 1.0, 0.0, "km/h")
    assert s2 == 'Signal("speed", 0x0D, 0, "u8", unit="km/h")'
