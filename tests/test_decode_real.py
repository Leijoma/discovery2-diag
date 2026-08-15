"""Avkodningstester mot VERKLIGA captures från bilen (RDL 016, 2026-08-03).

Två märkta referenspunkter — tändning på/motor AV och motor IGÅNG (tomgång) —
används som facit för skalningen. Databytes = fältet efter `61 <lid>`.
"""
import pytest

from d2diag.td5 import decode_lid


def _d(hexstr: str) -> bytes:
    return bytes.fromhex(hexstr.replace(" ", ""))


# --------------------------------------------------------------------------- #
# MOTOR AV (tändning på): rpm 0, batteri ~11.7 V, injektorbalans 0
# --------------------------------------------------------------------------- #
def test_off_temps_1a():
    v = decode_lid(0x1A, _d("0c fc 04 f1 0c b1 05 eb 10 88 00 04 0c 95 06 51"))
    assert round(v["coolant_temp"], 1) == 59.2
    assert round(v["air_temp"], 1) == 51.7
    assert round(v["fuel_temp"], 1) == 48.9
    assert round(v["ext_temp"], 1) == 150.0  # oansluten givare = konstant default


def test_off_battery_10():
    v = decode_lid(0x10, _d("2d 94 2d af"))
    assert round(v["battery"], 2) == 11.67


def test_off_manifold_and_maf_1c():
    v = decode_lid(0x1C, _d("27 07 27 1c 00 32 00 5b"))
    assert round(v["manifold_press"], 2) == 1.00
    assert v["maf_raw"] == 50  # rått fält (ingen MAF-givare), ej luftmassa


# --------------------------------------------------------------------------- #
# MOTOR IGÅNG (tomgång): rpm ~759, batteri ~13.8 V
# --------------------------------------------------------------------------- #
def test_running_rpm_09():
    assert decode_lid(0x09, _d("02 f7"))["rpm"] == 759


def test_running_battery_10():
    assert round(decode_lid(0x10, _d("35 fa 36 1a"))["battery"], 2) == 13.82


def test_running_temps_1a():
    v = decode_lid(0x1A, _d("0c f2 05 0f 0c 89 06 82 10 88 00 04 0c a4 06 17"))
    assert round(v["coolant_temp"], 1) == 58.2
    assert round(v["air_temp"], 1) == 47.7
    assert round(v["fuel_temp"], 1) == 50.4
    assert round(v["ext_temp"], 1) == 150.0  # samma default → bekräftar oansluten


def test_running_rpm_error_21():
    assert decode_lid(0x21, _d("00 05"))["rpm_error"] == 5


def test_running_injector_balance_40():
    v = decode_lid(0x40, _d("00 01 00 00 ff ff 00 00 00 00"))
    assert v["balance_1"] == 1
    assert v["balance_2"] == 0
    assert v["balance_3"] == -1  # ff ff = −1 (korrekt tvåkomplement, inte −2)


# --------------------------------------------------------------------------- #
# LID 1B — accelerator-pedalgivare. reference tool: Accel. Way 1/2/3 (V) + Supply (V).
# 4 spänningsfält (foten av pedalen → way3 = 0 V). SNIFFAT 2026-08-08.
# --------------------------------------------------------------------------- #
def test_accel_1b_four_voltage_ways():
    v = decode_lid(0x1B, _d("02 86 11 1c 00 00 13 92"))
    assert round(v["accel_way1"], 3) == 0.646
    assert round(v["accel_way2"], 3) == 4.380
    assert round(v["accel_way3"], 2) == 0.0     # reference tool "Way 3 (V)", foten av → 0 V
    assert round(v["accel_supply"], 2) == 5.01  # 5V-referens
    assert len(v) == 4  # exakt fyra fält (Way 1/2/3 + Supply)
