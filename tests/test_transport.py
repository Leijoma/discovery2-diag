"""Tester för transportlagret. Körs utan hårdvara via pyserials ``loop://``."""
from d2diag.transport import LoggingTransport, SerialTransport


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
