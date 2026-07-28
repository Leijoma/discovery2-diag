"""Tester för Td5 identifier-avkodning och skalning."""
from d2diag.td5.identifiers import decode_lid


def test_rpm_u16():
    assert decode_lid(0x09, bytes([0x03, 0x52])) == {"rpm": 850}


def test_battery_scaled_to_volts():
    v = decode_lid(0x10, bytes([0x30, 0xD4]))["battery"]  # 12500 mV
    assert abs(v - 12.5) < 1e-9


def test_temp_kelvin_times_ten_offset():
    # kylvätska 20,0 °C = (20 + 273,2) * 10 = 2932 = 0x0B74
    data = bytes([0x0B, 0x74, 0, 0, 0x0B, 0x74, 0, 0, 0x0B, 0x74, 0, 0, 0x0B, 0x74])
    out = decode_lid(0x1A, data)
    assert abs(out["coolant_temp"] - 20.0) < 1e-6
    assert abs(out["air_temp"] - 20.0) < 1e-6
    assert abs(out["fuel_temp"] - 20.0) < 1e-6


def test_rpm_error_signed():
    assert decode_lid(0x21, bytes([0xFF, 0xF6]))["rpm_error"] == -10


def test_injector_balance_signed():
    out = decode_lid(0x40, bytes([0x00, 0x05, 0xFF, 0xFB, 0, 0, 0, 0, 0, 0]))
    assert out["balance_1"] == 5
    assert out["balance_2"] == -5


def test_short_data_skips_signals_that_dont_fit():
    out = decode_lid(0x1A, bytes([0x0B, 0x74]))  # bara plats för kylvätska
    assert set(out) == {"coolant_temp"}
