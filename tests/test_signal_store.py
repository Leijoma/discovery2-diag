"""Tests for the declarative signal store (d2diag.signals).

The parity test is **the safety net for the migration**: the frozen reference table
below is the hand-coded td5.identifiers literal as it looked before the flip.
``load_signals("td5")`` must reproduce it exactly (name/lid/offset/type/scale/
bias/unit + limits) — otherwise the store has silently changed a scale.
"""
import json

import pytest

from d2diag import signals as store
from d2diag.signals import Signal, load_signals, upsert_field

# (name, lid, offset, kind, scale, bias, unit) — frozen reference from the old literal.
_SPEC = [
    ("rpm", 0x09, 0, "u16", 1.0, 0.0, "rpm"),
    ("speed", 0x0D, 0, "u8", 1.0, 0.0, "km/h"),
    ("battery", 0x10, 0, "u16", 0.001, 0.0, "V"),
    ("coolant_temp", 0x1A, 0, "u16", 0.1, -273.2, "°C"),
    ("air_temp", 0x1A, 4, "u16", 0.1, -273.2, "°C"),
    ("ext_temp", 0x1A, 8, "u16", 0.1, -273.2, "°C"),
    ("fuel_temp", 0x1A, 12, "u16", 0.1, -273.2, "°C"),
    ("accel_way1", 0x1B, 0, "u16", 0.001, 0.0, "V"),
    ("accel_way2", 0x1B, 2, "u16", 0.001, 0.0, "V"),
    ("accel_way3", 0x1B, 4, "u16", 0.001, 0.0, "V"),
    ("accel_supply", 0x1B, 6, "u16", 0.001, 0.0, "V"),
    ("manifold_press", 0x1C, 0, "u16", 0.0001, 0.0, "bar"),
    ("maf", 0x1D, 4, "u16", 0.1, -515.0, "kg/hr"),
    ("injection_qty", 0x1D, 6, "u16", 0.01, 0.0, "mg/stroke"),
    ("egr_modulator", 0x1D, 15, "u8", 100 / 255, 0.0, "%"),
    ("wastegate_modulator", 0x1D, 17, "u8", 100 / 255, 0.0, "%"),
    ("rpm_error", 0x21, 0, "s16", 1.0, 0.0, "rpm"),
    ("ambient_press_1", 0x23, 0, "u16", 0.0001, 0.0, "bar"),
    ("ambient_press_2", 0x23, 2, "u16", 0.0001, 0.0, "bar"),
    ("balance_1", 0x40, 0, "s16", 1.0, 0.0, ""),
    ("balance_2", 0x40, 2, "s16", 1.0, 0.0, ""),
    ("balance_3", 0x40, 4, "s16", 1.0, 0.0, ""),
    ("balance_4", 0x40, 6, "s16", 1.0, 0.0, ""),
    ("balance_5", 0x40, 8, "s16", 1.0, 0.0, ""),
]

_SPEC_LIMITS = {
    "rpm": (0, 4800), "speed": (0, 200), "battery": (11.5, 15.5),
    "coolant_temp": (-40, 105), "air_temp": (-30, 80), "fuel_temp": (-30, 90),
    "ext_temp": (-40, 50),        # ghost: 150°C → suspect (sensor not fitted)
    "maf": (0, 700),              # kg/hr; u16@4, WOT peak ~667 (kandidat scale)
    "injection_qty": (0, 90),     # mg/stroke (candidate)
    "egr_modulator": (0, 100),        # % duty (candidate, 1D@15)
    "wastegate_modulator": (0, 100),  # % duty (candidate, 1D@17); 1D@16 is a dead/reserved byte
    "manifold_press": (0.8, 2.6), "ambient_press_1": (0.8, 1.1),
    "ambient_press_2": (0.8, 1.1), "rpm_error": (-300, 300),
    "accel_way1": (0.0, 5.1), "accel_way2": (0.0, 5.1), "accel_way3": (0.0, 5.1),
    "accel_supply": (4.9, 5.1),   # reference tool: 5.0 V ±0.1 rock-solid (2026-08-19)
    "balance_1": (-12, 12), "balance_2": (-12, 12), "balance_3": (-12, 12),
    "balance_4": (-12, 12), "balance_5": (-12, 12),
}


def test_td5_store_reproduces_literal_exactly():
    loaded = {s.name: s for s in load_signals("td5")}
    assert set(loaded) == {r[0] for r in _SPEC}
    for name, lid, off, kind, scale, bias, unit in _SPEC:
        s = loaded[name]
        assert (s.lid, s.offset, s.kind, s.scale, s.bias, s.unit) == (lid, off, kind, scale, bias, unit), name


def test_td5_store_limits_match_literal():
    lim = {s.name: s.limits for s in load_signals("td5") if s.limits}
    assert lim == _SPEC_LIMITS


def test_identifiers_public_api_intact():
    # Downstream importers (sources/decoder/td5) rely on these names.
    from d2diag.td5.identifiers import BY_NAME, LIDS, LIMITS, SIGNALS, decode_lid
    assert len(SIGNALS) == len(_SPEC)
    assert BY_NAME["rpm"].lid == 0x09
    assert 0x1A in LIDS
    assert LIMITS["battery"] == (11.5, 15.5)
    # 21 1A response (real car): coolant offset0 u16/10−273.2
    data = bytes.fromhex("0cfc04f10cb105eb108800040c950651")
    assert round(decode_lid(0x1A, data)["coolant_temp"], 1) == 59.2


# ---- extended types (u16le/s16le/bit/states) ---------------------------- #
def test_u16le_and_s16le_decode():
    d = bytes.fromhex("00 80".replace(" ", ""))
    assert Signal("x", 1, 0, "u16le").decode(d) == 0x8000
    assert Signal("x", 1, 0, "s16le").decode(d) == 0x8000 - 0x10000  # LE: 0x8000 → -32768


def test_bit_decode_numeric_and_named():
    s = Signal("any_door", 0x56, 0, "bit", bit=0, states={0: "closed", 1: "open"})
    assert s.decode(b"\x01") == 1.0
    assert s.decode(b"\x00") == 0.0
    assert s.decode_named(b"\x01") == "open"
    assert s.decode_named(b"\x00") == "closed"


# ---- write-back round-trip (isolerad temp-dir) -------------------------- #
def test_upsert_field_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_DIR", tmp_path)
    store._CACHE.clear()
    (tmp_path / "demo.json").write_text("[]", encoding="utf-8")

    upsert_field("demo", {"name": "boost", "lid": "1C", "offset": 0, "kind": "u16",
                          "scale": 0.0001, "unit": "bar"})
    sigs = load_signals("demo")
    assert len(sigs) == 1
    assert sigs[0].name == "boost" and sigs[0].lid == 0x1C
    assert sigs[0].confidence == "kandidat"  # default when not specified

    # same (lid, offset, name) → replaced, not duplicated
    upsert_field("demo", {"name": "boost", "lid": "1C", "offset": 0, "kind": "u16",
                          "scale": 0.0001, "unit": "bar", "confidence": "belagt"})
    sigs = load_signals("demo")
    assert len(sigs) == 1 and sigs[0].confidence == "belagt"

    # new field → append
    upsert_field("demo", {"name": "other", "lid": "0D", "offset": 0, "kind": "u8"})
    assert len(load_signals("demo")) == 2
    # LID is normalised to 2-hex uppercase on disk
    rows = json.loads((tmp_path / "demo.json").read_text(encoding="utf-8"))
    assert {r["lid"] for r in rows} == {"1C", "0D"}


def test_slabs_store_has_belagt_heights_and_door():
    by = {s.name: s for s in load_signals("slabs")}
    assert by["height_left"].confidence == "belagt"
    assert by["height_right"].confidence == "belagt"
    assert by["any_door"].kind == "bit" and by["any_door"].states == {0: "closed", 1: "open"}
