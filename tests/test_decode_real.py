"""Decoding tests against REAL captures from the car (RDL 016, 2026-08-03).

Two marked reference points — ignition on/engine OFF and engine RUNNING (idle) —
are used as the ground truth for the scaling. Data bytes = the field after `61 <lid>`.
"""
import pytest

from d2diag.td5 import decode_lid


def _d(hexstr: str) -> bytes:
    return bytes.fromhex(hexstr.replace(" ", ""))


# --------------------------------------------------------------------------- #
# ENGINE OFF (ignition on): rpm 0, battery ~11.7 V, injector balance 0
# --------------------------------------------------------------------------- #
def test_off_temps_1a():
    v = decode_lid(0x1A, _d("0c fc 04 f1 0c b1 05 eb 10 88 00 04 0c 95 06 51"))
    assert round(v["coolant_temp"], 1) == 59.2
    assert round(v["air_temp"], 1) == 51.7
    assert round(v["fuel_temp"], 1) == 48.9
    assert round(v["ext_temp"], 1) == 150.0  # unconnected sensor = constant default


def test_off_battery_10():
    v = decode_lid(0x10, _d("2d 94 2d af"))
    assert round(v["battery"], 2) == 11.67


def test_off_manifold_and_maf_1c():
    v = decode_lid(0x1C, _d("27 07 27 1c 00 32 00 5b"))
    assert round(v["manifold_press"], 2) == 1.00
    # 1C@4 is no longer mapped: it is NOT air mass (reads 0 while running). The real MAF
    # lives in 1D u16@4 (proven vs rpm*MAP); see test on LID 0x1D.
    assert "maf_raw" not in v


# --------------------------------------------------------------------------- #
# ENGINE RUNNING (idle): rpm ~759, battery ~13.8 V
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
    assert round(v["ext_temp"], 1) == 150.0  # same default → confirms unconnected


def test_running_rpm_error_21():
    assert decode_lid(0x21, _d("00 05"))["rpm_error"] == 5


def test_running_injector_balance_40():
    v = decode_lid(0x40, _d("00 01 00 00 ff ff 00 00 00 00"))
    assert v["balance_1"] == 1
    assert v["balance_2"] == 0
    assert v["balance_3"] == -1  # ff ff = −1 (correct two's complement, not −2)


# --------------------------------------------------------------------------- #
# LID 1B — accelerator pedal sensor. reference tool: Accel. Way 1/2/3 (V) + Supply (V).
# 4 voltage fields (foot of the pedal → way3 = 0 V). SNIFFED 2026-08-08.
# --------------------------------------------------------------------------- #
def test_accel_1b_four_voltage_ways():
    v = decode_lid(0x1B, _d("02 86 11 1c 00 00 13 92"))
    assert round(v["accel_way1"], 3) == 0.646
    assert round(v["accel_way2"], 3) == 4.380
    assert round(v["accel_way3"], 2) == 0.0     # reference tool "Way 3 (V)", foot off → 0 V
    assert round(v["accel_supply"], 2) == 5.01  # 5V reference
    assert len(v) == 4  # exactly four fields (Way 1/2/3 + Supply)
