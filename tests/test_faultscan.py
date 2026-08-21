"""Basic mode — read fault codes from all modules (mock + live orchestration)."""
import d2diag.faultscan as fs


def test_mock_report_has_all_modules_and_baseline():
    rows = fs.read_all("mock")
    by = {r["module"]: r for r in rows}
    # the three readable + the three not implemented
    assert {"TD5", "SLABS", "Airbag"} <= set(by)
    assert by["TD5"]["status"] == "ok"                      # no faults
    assert by["SLABS"]["status"] == "faults" and len(by["SLABS"]["faults"]) == 2
    assert by["Airbag"]["status"] == "faults"               # 004 + 022
    assert by["ACE"]["status"] == "unimplemented"


def test_live_no_cable_marks_modules_error(monkeypatch):
    # resolve_serial_port raises FileNotFoundError → all three marked error, not a crash.
    import d2diag.web.sources as sources

    def _boom(_spec):
        raise FileNotFoundError("no cable")

    monkeypatch.setattr(sources, "resolve_serial_port", _boom)
    rows = fs.read_all("live", "auto", sleep=lambda *_: None)
    readable = {r["module"]: r for r in rows if r["status"] != "unimplemented"}
    assert set(readable) == {"TD5", "SLABS", "Airbag"}
    assert all(r["status"] == "error" for r in readable.values())


def test_live_reads_modules_over_fake(monkeypatch):
    # Simulate the car: TD5 with no faults, SLABS with baseline faults, airbag with 004/022.
    import d2diag.transport as transport_pkg
    import d2diag.web.sources as sources
    from d2diag.kline import encode
    from tests import fakes

    def _f(d):
        return encode(d, addressed=False)                    # unaddressed session frame

    def _a_req(d):
        return encode(d, 0x5B, 0xF7, addressed=True)         # tester → airbag

    def _a_resp(d):
        return encode(d, 0xF7, 0x5B, addressed=True)         # airbag → tester

    slabs_logged = bytes.fromhex("00000010000000000000100000000000")  # 020 + 027

    responses = {
        # TD5 (target 0x13): fast init → session → security → 21 3B (zero block = no faults)
        encode(b"\x81", 0x13, 0xF7, addressed=True): _f(b"\xc1\x57\x8f"),
        _f(b"\x10\xa0"): _f(b"\x50"),
        _f(b"\x27\x01"): _f(b"\x67\x01\x10\xe6"),
        _f(b"\x27\x02\x90\x86"): _f(b"\x67\x02"),             # keygen(10,e6)→90 86 (test_tolerant)
        _f(b"\x21\x3b"): _f(b"\x61\x3b" + bytes(35)),
        # SLABS (target 0x29): fast init → 21 11 (logged) + 21 47 (current empty).
        # Slabs tries FUNCTIONAL addressing first (see _init_variants) — answer that,
        # otherwise the establishment sleeps 28 s per failed attempt before it falls
        # back on the physical frame.
        encode(b"\x81", 0x29, 0xF1, addressed=True, functional=True): _f(b"\xc1\x57\x8f"),
        encode(b"\x81", 0x29, 0xF7, addressed=True): _f(b"\xc1\x57\x8f"),
        _f(b"\x21\x11"): _f(b"\x61\x11" + slabs_logged),
        _f(b"\x21\x47"): _f(b"\x61\x47" + bytes(16)),
        # Airbag (target 0x5B, addressed): slow init (the fake) → 10 81 → 21 02
        _a_req(b"\x10\x81"): _a_resp(b"\x50\x81"),
        _a_req(b"\x21\x02"): _a_resp(b"\x61\x02\x90\x04\x90\x16" + bytes(8)),
    }

    def _fake_transport(port, timeout=1.0):
        return fakes.FakeKLineEcu(responses)                 # fresh instance per module

    monkeypatch.setattr(transport_pkg, "SerialTransport", _fake_transport)
    monkeypatch.setattr(sources, "resolve_serial_port", lambda spec: "FAKE")

    rows = fs.read_all("live", "auto", sleep=lambda *_: None)
    by = {r["module"]: r for r in rows}
    assert by["TD5"]["status"] == "ok"                       # zero block → no faults
    assert by["SLABS"]["status"] == "faults"                 # 020 + 027
    assert any(x.startswith("020") for x in by["SLABS"]["faults"])
    assert by["Airbag"]["status"] == "faults"                # 004 + 022
    assert any("004" in x for x in by["Airbag"]["faults"])


def test_live_stops_td5_session_before_next_module_inits(monkeypatch):
    # Shared bus: the TD5 session must be ended (20 → 60) BEFORE SLABS opens its
    # transport and inits, otherwise StartCommunication answers 7F 81 10.
    import d2diag.transport as transport_pkg
    import d2diag.web.sources as sources
    from d2diag.kline import encode
    from d2diag.session import EcuSession
    from tests import fakes

    # Speed it up: skip bus idle/retry sleep (5 s for Td5). Cannot be patched via
    # time.sleep — establish binds its sleep as a default argument at def time.
    _real_establish = EcuSession._establish

    def _no_idle(self, after=None, *, idle, attempts, retry_sleep, sleep=None, progress=None):
        return _real_establish(self, after, idle=0, attempts=attempts, retry_sleep=0,
                               sleep=lambda *_: None, progress=progress)

    monkeypatch.setattr(EcuSession, "_establish", _no_idle)

    def _f(d):
        return encode(d, addressed=False)

    def _a_req(d):
        return encode(d, 0x5B, 0xF7, addressed=True)

    def _a_resp(d):
        return encode(d, 0xF7, 0x5B, addressed=True)

    responses = {
        encode(b"\x81", 0x13, 0xF7, addressed=True): _f(b"\xc1\x57\x8f"),
        _f(b"\x10\xa0"): _f(b"\x50"),
        _f(b"\x27\x01"): _f(b"\x67\x01\x10\xe6"),
        _f(b"\x27\x02\x90\x86"): _f(b"\x67\x02"),
        _f(b"\x21\x3b"): _f(b"\x61\x3b" + bytes(35)),
        _f(b"\x20"): _f(b"\x60"),                     # StopDiagnosticSession
        encode(b"\x81", 0x29, 0xF7, addressed=True): _f(b"\xc1\x57\x8f"),
        _f(b"\x21\x11"): _f(b"\x61\x11" + bytes(16)),
        _f(b"\x21\x47"): _f(b"\x61\x47" + bytes(16)),
        # the airbag answers too, otherwise its retries burn seconds in the test
        _a_req(b"\x10\x81"): _a_resp(b"\x50\x81"),
        _a_req(b"\x21\x02"): _a_resp(b"\x61\x02" + bytes(12)),
    }

    events: "list[str]" = []

    class _Recording(fakes.FakeKLineEcu):
        def send(self, data):
            if bytes(data) == _f(b"\x20"):
                events.append("td5-stop")
            return super().send(data)

    def _fake_transport(port, timeout=1.0):
        events.append("new-transport")
        return _Recording(responses)

    monkeypatch.setattr(transport_pkg, "SerialTransport", _fake_transport)
    monkeypatch.setattr(sources, "resolve_serial_port", lambda spec: "FAKE")

    fs.read_all("live", "auto", sleep=lambda *_: None)
    # order: TD5 transport → … → td5-stop → SLABS transport
    assert "td5-stop" in events
    assert events.index("td5-stop") < events.index("new-transport", 1)
