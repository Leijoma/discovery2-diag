"""Serial-port resolution (core, no web/pyserial) — d2diag.ports.resolve_serial_port.

Moved out of test_web when resolve_serial_port moved from web/sources to the core
d2diag.ports module. The auto-detection tests patch the shared glob module via
d2diag.ports; a re-export smoke test still lives in test_web (proves the old import
path `d2diag.web.sources.resolve_serial_port` keeps working).
"""
import pytest

import d2diag.ports as p


def test_resolve_serial_explicit_passthrough():
    assert p.resolve_serial_port("/dev/ttyUSB3") == "/dev/ttyUSB3"


def test_resolve_serial_auto_prefers_known_chip(monkeypatch):
    mapping = {
        "/dev/serial/by-id/*": [
            "/dev/serial/by-id/usb-Prolific_PL2303-if00",
            "/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A1-if00-port0",
        ],
        "/dev/ttyUSB*": ["/dev/ttyUSB0", "/dev/ttyUSB1"],
        "/dev/ttyACM*": [],
    }
    monkeypatch.setattr(p.glob, "glob", lambda pat: mapping.get(pat, []))
    # prefers the FTDI match among the by-id links
    assert "FTDI" in p.resolve_serial_port("auto")


def test_resolve_serial_auto_macos_cu_port(monkeypatch):
    # macOS: no Linux ports, but a CH340 and an FTDI cable as cu.*
    mapping = {
        "/dev/cu.usbserial-*": ["/dev/cu.usbserial-0001"],
        "/dev/cu.wchusbserial*": ["/dev/cu.wchusbserial1420"],
    }
    monkeypatch.setattr(p.glob, "glob", lambda pat: mapping.get(pat, []))
    # just verify that a cu.* port is chosen (usbserial does not match _KKL_HINTS)
    assert p.resolve_serial_port("auto").startswith("/dev/cu.")


def test_resolve_serial_auto_mac_preferred_over_ttyusb(monkeypatch):
    mapping = {
        "/dev/cu.usbserial-*": ["/dev/cu.usbserial-FTDI99"],
        "/dev/ttyUSB*": ["/dev/ttyUSB0"],
    }
    monkeypatch.setattr(p.glob, "glob", lambda pat: mapping.get(pat, []))
    # mac cu.* (with FTDI hint) takes precedence over the generic ttyUSB fallback
    assert p.resolve_serial_port("auto") == "/dev/cu.usbserial-FTDI99"


def test_resolve_serial_auto_falls_back_to_ttyusb(monkeypatch):
    mapping = {"/dev/ttyUSB*": ["/dev/ttyUSB0"]}
    monkeypatch.setattr(p.glob, "glob", lambda pat: mapping.get(pat, []))
    assert p.resolve_serial_port("auto") == "/dev/ttyUSB0"


def test_resolve_serial_auto_none_raises(monkeypatch):
    monkeypatch.setattr(p.glob, "glob", lambda pat: [])
    with pytest.raises(FileNotFoundError):
        p.resolve_serial_port("auto")
