"""Tester för transportlagret. Körs utan hårdvara via pyserials ``loop://``."""
from d2diag.transport import LoggingTransport, SerialTransport


def test_slow_init_bits_frame():
    # 5-baud init-ram: startbit(0), 8 databitar LSB-först, stoppbit(1) — 8N1.
    for addr in (0x33, 0x13, 0x29, 0x34, 0x00, 0xFF):
        bits = SerialTransport.slow_init_bits(addr)
        assert len(bits) == 10
        assert bits[0] == 0 and bits[9] == 1          # start / stopp
        data = bits[1:9]                               # 8 databitar LSB-först
        assert sum(b << i for i, b in enumerate(data)) == addr
    # regressionsvakt: 0x29 skickas nu som 0x29 (inte 0xA9 som med gamla paritetsbuggen)
    assert SerialTransport.slow_init_bits(0x29)[1:9] == [1, 0, 0, 1, 0, 1, 0, 0]


def test_parse_slow_init():
    # 0x55 sync + KW1 KW2 → (KW1, KW2); annars None
    assert SerialTransport.parse_slow_init(b"\x55\x8f\xea\x15") == (0x8F, 0xEA)
    assert SerialTransport.parse_slow_init(b"\x55\x01\x02") == (0x01, 0x02)
    assert SerialTransport.parse_slow_init(b"") is None
    assert SerialTransport.parse_slow_init(b"\x00\x8f\xea") is None  # ingen 0x55
    assert SerialTransport.parse_slow_init(b"\x55\x8f") is None       # för kort


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
        raise AssertionError("förväntade RuntimeError när transporten är stängd")


def test_logging_transport_writes_tx_and_rx(tmp_path):
    log = tmp_path / "raw.log"
    with LoggingTransport(SerialTransport(url="loop://", timeout=1.0), logfile=log) as t:
        t.send(b"\x81\x0c")
        assert t.receive(2, timeout=1.0) == b"\x81\x0c"
    text = log.read_text(encoding="utf-8")
    assert "TX 81 0C" in text
    assert "RX 81 0C" in text


def test_logging_transport_is_a_transport():
    # Ett högre lager ska kunna ta emot LoggingTransport utan att veta något.
    from d2diag.transport import Transport

    assert isinstance(LoggingTransport(SerialTransport(url="loop://")), Transport)


def test_serial_fast_init_low_restores_baud_and_flushes_echo(monkeypatch):
    # Baud-drop-pulsen (macOS-vägen): sänk baud, skicka 0x00, återställ baud, töm ekot.
    # Tvinga icke-Linux så baud-tricket testas oavsett värdplattform.
    import d2diag.transport.serial_transport as st
    monkeypatch.setattr(st.sys, "platform", "darwin")
    with SerialTransport(url="loop://", baudrate=10400, timeout=0.3) as t:
        t.fast_init_low(0.025)
        assert t.baudrate == 10400          # baud återställd efteråt
        assert t.receive(1, timeout=0.05) == b""  # ekot av puls-byten tömt


def test_serial_fast_init_low_uses_break_on_linux(monkeypatch):
    # På Linux (Raspberry Pi/FTDI) klarar inte hårdvaran 360 baud → låg-pulsen
    # måste komma från en OS-timad break i stället. Belagt i bilen 2026-08-21.
    import d2diag.transport.serial_transport as st
    monkeypatch.setattr(st.sys, "platform", "linux")
    calls = {}
    with SerialTransport(url="loop://", baudrate=10400, timeout=0.3) as t:
        monkeypatch.setattr(t, "send_break", lambda d=0.025: calls.__setitem__("dur", d))
        already_high = t.fast_init_low(0.025)
    assert calls.get("dur") == 0.025    # låg-pulsen kom via break
    assert already_high == 0.0          # ingen stoppbit att kompensera för
    assert t.baudrate == 10400          # baud orörd


def test_logging_transport_delegates_serial_hooks():
    # send_break/reset_input_buffer måste nå den inre transporten, annars döljer
    # wrappern dem för K-Line-lagrets fast init.
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
