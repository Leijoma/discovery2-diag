"""Tests for Td5 identifier decoding and scaling."""
from d2diag.td5.identifiers import decode_lid


def test_rpm_u16():
    assert decode_lid(0x09, bytes([0x03, 0x52])) == {"rpm": 850}


def test_battery_scaled_to_volts():
    v = decode_lid(0x10, bytes([0x30, 0xD4]))["battery"]  # 12500 mV
    assert abs(v - 12.5) < 1e-9


def test_temp_kelvin_times_ten_offset():
    # coolant 20.0 °C = (20 + 273.2) * 10 = 2932 = 0x0B74
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
    out = decode_lid(0x1A, bytes([0x0B, 0x74]))  # only room for coolant
    assert set(out) == {"coolant_temp"}


def test_signal_status_flags_physically_impossible_as_suspect():
    # Motorway 2026-08-21: the KKL cable threw spikes (MAP 4.5 bar, coolant 429°,
    # throttle 41 V) that pass framing but are garbage. Values outside the range by
    # more than its WHOLE span → 'suspect'; genuine high/low values keep low/high.
    from d2diag.td5.identifiers import signal_status as st
    assert st("coolant_temp", 429) == "suspect"   # spike
    assert st("coolant_temp", 106) == "high"       # genuine overheating, not a spike
    assert st("coolant_temp", 88) == "ok"
    assert st("manifold_press", 4.54) == "suspect"
    assert st("accel_way1", 41) == "suspect"
    assert st("air_temp", 5398) == "suspect"
    assert st("air_temp", 120) == "high"           # fixed sensor = high, not suspect
    assert st("maf_raw", 51080) is None            # no limits → no flag
