"""EspTransport — the ESP32 bridge used as a Transport (protocol mapping, no hardware).

Proven live on the ESP over USB; these lock the send/receive/fast-init mapping so the
line protocol can't drift from the bridge section of esp32/kline_node/kline_node.ino.
"""
from d2diag.transport import EspTransport


class _FakeSer:
    def __init__(self):
        self.written = []
        self.replies = []

    def reset_input_buffer(self):
        pass

    def write(self, b):
        self.written.append(bytes(b))
        return len(b)

    def flush(self):
        pass

    def readline(self):
        return self.replies.pop(0) if self.replies else b""

    def close(self):
        pass


def _wired() -> "tuple[EspTransport, _FakeSer]":
    t = EspTransport("x")
    t._ser = _FakeSer()
    t._is_open = True
    return t, t._ser


def test_send_maps_to_tx_and_buffers_rx():
    t, ser = _wired()
    ser.replies = [b"RX 61 09 02 EE\n"]
    assert t.send(bytes.fromhex("022109")) == 3
    assert ser.written[0] == b"TX 02 21 09\n"
    # the returned burst is buffered and drained by receive()
    assert t.receive(64) == bytes.fromhex("610902EE")
    assert t.receive(64) == b""


def test_fast_init_fuses_pulse_and_first_frame_into_INIT():
    t, ser = _wired()
    ser.replies = [b"RX 03 C1 57 8F AA\n"]
    assert t.fast_init_low() == 0.0                 # defers the pulse
    t.send(bytes.fromhex("8113F78100"))             # StartCommunication → fused
    assert ser.written[0] == b"INIT 81 13 F7 81 00\n"
    assert t.receive(64) == bytes.fromhex("03C1578FAA")
    # subsequent sends are plain TX again
    ser.replies = [b"RX\n"]
    t.send(b"\x02\x10\xA0")
    assert ser.written[1] == b"TX 02 10 A0\n"
    assert t.receive(64) == b""                     # "RX" with no bytes → empty


def test_ping():
    t, ser = _wired()
    ser.replies = [b"PONG\n"]
    assert t.ping() is True


def test_wait_ready_returns_on_pong():
    t, ser = _wired()
    ser.replies = [b"PONG\n"]
    t._wait_ready(timeout=1.0)              # returns (no raise) as soon as the bridge answers


def test_wait_ready_raises_without_pong():
    import pytest
    t, _ = _wired()                        # FakeSer has no replies → PING never answered
    with pytest.raises(RuntimeError):
        t._wait_ready(timeout=0.05)
