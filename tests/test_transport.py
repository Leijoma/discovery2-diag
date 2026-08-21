"""Tests for the transport layer. Runs without hardware via pyserial's ``loop://``."""
from d2diag.transport import LoggingTransport, SerialTransport


def test_slow_init_bits_frame():
    # 5-baud init frame: start bit(0), 8 data bits LSB-first, stop bit(1) — 8N1.
    for addr in (0x33, 0x13, 0x29, 0x34, 0x00, 0xFF):
        bits = SerialTransport.slow_init_bits(addr)
        assert len(bits) == 10
        assert bits[0] == 0 and bits[9] == 1          # start / stop
        data = bits[1:9]                               # 8 data bits LSB-first
        assert sum(b << i for i, b in enumerate(data)) == addr
    # regression guard: 0x29 is now sent as 0x29 (not 0xA9 as with the old parity bug)
    assert SerialTransport.slow_init_bits(0x29)[1:9] == [1, 0, 0, 1, 0, 1, 0, 0]


def test_parse_slow_init():
    # 0x55 sync + KW1 KW2 → (KW1, KW2); otherwise None
    assert SerialTransport.parse_slow_init(b"\x55\x8f\xea\x15") == (0x8F, 0xEA)
    assert SerialTransport.parse_slow_init(b"\x55\x01\x02") == (0x01, 0x02)
    assert SerialTransport.parse_slow_init(b"") is None
    assert SerialTransport.parse_slow_init(b"\x00\x8f\xea") is None  # no 0x55
    assert SerialTransport.parse_slow_init(b"\x55\x8f") is None       # too short


def test_serial_loopback_send_receive():
    with SerialTransport(url="loop://", timeout=1.0) as t:
        payload = b"\x81\x13\xf7\x81\x0c"
        assert t.send(payload) == len(payload)
        assert t.receive(len(payload), timeout=1.0) == payload


def test_receive_timeout_returns_empty():
    with SerialTransport(url="loop://", timeout=0.1) as t:
        assert t.receive(1, timeout=0.1) == b""


def test_send_before_open_raises():
    t = SerialTransport(url="loop://")
    try:
        t.send(b"\x00")
    except RuntimeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError when the transport is closed")


def test_logging_transport_writes_tx_and_rx(tmp_path):
    log = tmp_path / "raw.log"
    with LoggingTransport(SerialTransport(url="loop://", timeout=1.0), logfile=log) as t:
        t.send(b"\x81\x0c")
        assert t.receive(2, timeout=1.0) == b"\x81\x0c"
    text = log.read_text(encoding="utf-8")
    assert "TX 81 0C" in text
    assert "RX 81 0C" in text


def test_logging_transport_is_a_transport():
    # A higher layer should be able to accept LoggingTransport without knowing anything.
    from d2diag.transport import Transport

    assert isinstance(LoggingTransport(SerialTransport(url="loop://")), Transport)


def test_serial_fast_init_low_restores_baud_and_flushes_echo(monkeypatch):
    # The baud-drop pulse (the macOS path): lower baud, send 0x00, restore baud, flush the echo.
    # Force non-Linux so the baud trick is tested regardless of host platform.
    import d2diag.transport.serial_transport as st
    monkeypatch.setattr(st.sys, "platform", "darwin")
    with SerialTransport(url="loop://", baudrate=10400, timeout=0.3) as t:
        t.fast_init_low(0.025)
        assert t.baudrate == 10400          # baud restored afterwards
        assert t.receive(1, timeout=0.05) == b""  # the echo of the pulse byte flushed


def test_serial_fast_init_low_uses_break_on_linux(monkeypatch):
    # On Linux (Raspberry Pi/FTDI) the hardware can't do 360 baud → the low pulse
    # must come from an OS-timed break instead. Confirmed in the car 2026-08-21.
    import d2diag.transport.serial_transport as st
    monkeypatch.setattr(st.sys, "platform", "linux")
    calls = {}
    with SerialTransport(url="loop://", baudrate=10400, timeout=0.3) as t:
        monkeypatch.setattr(t, "send_break", lambda d=0.025: calls.__setitem__("dur", d))
        already_high = t.fast_init_low(0.025)
    assert calls.get("dur") == 0.025    # the low pulse came via break
    assert already_high == 0.0          # no stop bit to compensate for
    assert t.baudrate == 10400          # baud untouched


def test_logging_transport_delegates_serial_hooks():
    # send_break/reset_input_buffer must reach the inner transport, otherwise the
    # wrapper hides them from the K-Line layer's fast init.
    from d2diag.transport import Transport

    class _Inner(Transport):
        def __init__(self):
            self.broke = None

        def open(self):
            self._is_open = True

        def close(self):
            self._is_open = False

        def send(self, data):
            return len(data)

        def receive(self, size=1, timeout=None):
            return b""

        def send_break(self, duration=0.025):
            self.broke = duration

    inner = _Inner()
    LoggingTransport(inner).send_break(0.025)
    assert inner.broke == 0.025
