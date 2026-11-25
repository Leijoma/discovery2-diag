"""tools/v8_probe.py: frame builders, reply classification and the read-only guard.

No hardware: the end-to-end test drives the 5-baud path against a scripted ISO 9141-2 ECU
that answers like a generic OBD-II engine ECU would (ISO 15031-5 response headers)."""
import pytest

import tools.v8_probe as p


def test_iso9141_frame_matches_the_standard_example():
    # ISO 15031-5 / every ELM327 trace: 01 00 → 68 6A F1 01 00 C4
    assert p.iso9141_frame(b"\x01\x00") == bytes.fromhex("686af10100c4")
    assert p.iso9141_frame(b"\x03") == bytes.fromhex("686af103c6")


def test_ds2_frame_xor_checksum():
    # BMW DS2 DME ident: 12 04 00 16
    assert p.ds2_frame(0x12, b"\x00") == bytes.fromhex("12040016")


@pytest.mark.parametrize("kw,expect", [((0x08, 0x08), "ISO 9141-2"), ((0x94, 0x94), "ISO 9141-2"),
                                       ((0xE9, 0x8F), "KWP2000"), ((0x01, 0x02), "unknown")])
def test_interpret_keybytes(kw, expect):
    assert expect in p.interpret_keybytes(*kw)


def test_classify_and_echo_strip():
    req = p.iso9141_frame(b"\x01\x00")
    burst = req + bytes.fromhex("486b104100be3ea81184")
    reply = p.strip_echo(burst, req)
    assert reply[0] == 0x48
    assert p.classify(reply, b"\x01\x00") == "positive"
    assert p.classify(bytes.fromhex("83f1107f2111"), b"\x21\x01") == "negative"
    assert p.classify(b"", b"\x03") == "silent"


@pytest.mark.parametrize("sid", sorted(p._FORBIDDEN_SIDS))
def test_guard_refuses_write_services(sid):
    with pytest.raises(RuntimeError):
        p._guard(bytes([sid, 0x00]))


def test_every_request_the_probe_sends_passes_the_guard():
    for data, _ in p.GENERIC_OBD + p.PHYSICAL_READS + [(b"\x82", "")]:
        p._guard(data)


class _Iso9141Ecu:
    """Half-duplex scripted ECU: 5-baud key bytes 08 08, then answers 01 00 / 01 01 / 03."""
    ANSWERS = {bytes.fromhex("686af10100c4"): bytes.fromhex("486b104100be3ea81184"),
               bytes.fromhex("686af10101c5"): bytes.fromhex("486b104101000765000027"),
               bytes.fromhex("686af103c6"): bytes.fromhex("486b104300000000000000ee")}

    def __init__(self):
        self.tx, self.rx = bytearray(), bytearray()

    def open(self): pass
    def close(self): pass
    def reset_input_buffer(self): self.rx.clear()

    def slow_init(self, address):
        assert address == 0x33
        return bytes.fromhex("550808f7cc")

    @staticmethod
    def parse_slow_init(raw):
        return (raw[1], raw[2]) if raw[:1] == b"\x55" else None

    def send(self, data):
        self.tx += data
        self.rx += data  # echo
        for req, ans in self.ANSWERS.items():
            if self.tx.endswith(req):
                self.rx += ans
                self.tx.clear()
        return len(data)

    def receive(self, size=1, timeout=None):
        out = bytes(self.rx[:size])
        del self.rx[:size]
        return out


def test_slow_init_path_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(p.time, "sleep", lambda s: None)
    probe = p.Probe.__new__(p.Probe)
    probe.port, probe.t, probe.results = "fake", _Iso9141Ecu(), []
    probe.log = open(tmp_path / "log.txt", "w", encoding="utf-8")
    probe.slow_init_33()
    probe.log.close()
    got = dict(probe.results)
    assert "ISO 9141-2" in got["5-baud 0x33"]
    assert got["5-baud 01 00 supported PIDs"] == "positive"
    assert got["5-baud 03 stored DTCs"] == "positive"
