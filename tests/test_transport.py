"""Tester för transportlagret. Körs utan hårdvara via pyserials ``loop://``."""
from d2diag.transport import LoggingTransport, SerialTransport


def test_slow_init_bits_frame():
    # 5-baud init-ram för adress 0x33 (klassisk ISO 9141): start, 7 databitar
    # LSB-först, udda paritet (samma logik som muki01/exempelkod), stopp.
    bits = SerialTransport.slow_init_bits(0x33)
    assert len(bits) == 10
    assert bits[0] == 0 and bits[9] == 1              # start / stopp
    assert bits[1:8] == [1, 1, 0, 0, 1, 1, 0]         # 0x33 LSB-först
    assert bits[8] == 0                                # paritetsbit per referensen
    # adress 0x13 (motorn använder visserligen fast init, men testa bitmönstret)
    b13 = SerialTransport.slow_init_bits(0x13)
    assert b13[0] == 0 and b13[9] == 1
    assert b13[1:8] == [1, 1, 0, 0, 1, 0, 0]          # 0x13 = 0010011 LSB-först


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


def test_serial_fast_init_low_restores_baud_and_flushes_echo():
    # Baud-drop-pulsen: sänk baud, skicka 0x00, återställ baud, töm ekot.
    with SerialTransport(url="loop://", baudrate=10400, timeout=0.3) as t:
        t.fast_init_low(0.025)
        assert t.baudrate == 10400          # baud återställd efteråt
        assert t.receive(1, timeout=0.05) == b""  # ekot av puls-byten tömt


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
