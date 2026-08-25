"""Tests for the web dashboard: the mock source's shape + that the server serves."""
import json
import threading
import time
import urllib.request

import pytest

from d2diag.web import MockDataSource
from d2diag.web.server import DiagServer


def test_mock_source_shape():
    d = MockDataSource().poll()
    assert d["status"] == "connected"
    assert d["source"] == "mock"
    assert "rpm" in d["signals"]
    assert set(d["signals"]["rpm"]) == {"v", "u", "s", "c"}   # c = confidence (trust view)
    assert d["signals"]["battery"]["u"] == "V"
    assert d["signals"]["rpm"]["c"] == "belagt"                # rpm is verified
    # rpm_error and balance_1..5 were promoted to proven 2026-08-19 (labeled_captures
    # 21/40 = "correct", values vary across captures). The remaining TD5 candidates
    # (maf_raw, accel_way3, ext_temp) are not emitted by the mock, so the confidence
    # filter is tested separately in test_conf_of_reads_store.
    assert d["signals"]["rpm_error"]["c"] == "belagt"
    assert isinstance(d["faults"], list) and d["faults"]


def test_signal_status_ranges():
    from d2diag.td5.identifiers import signal_status
    assert signal_status("battery", 13.5) == "ok"
    assert signal_status("battery", 10.0) == "low"
    assert signal_status("coolant_temp", 120) == "high"
    assert signal_status("ext_temp", 150) == "suspect"  # ghost constant, sensor not fitted → struck through
    assert signal_status("maf_raw", 999) is None
    assert signal_status("unknown", 1) is None


def test_mock_signals_include_status_and_flag_iat():
    d = MockDataSource().poll()
    assert "s" in d["signals"]["rpm"]
    assert d["signals"]["air_temp"]["s"] == "high"   # mock IAT 120 °C → high
    assert d["signals"]["battery"]["s"] == "ok"


def test_logger_records_anomalies(tmp_path):
    from d2diag.web.logger import SnapshotLogger
    p = tmp_path / "a.jsonl"
    lg = SnapshotLogger(str(p), min_interval=999)
    lg.log({"status": "connected", "faults": [], "signals": {
        "air_temp": {"v": 120, "u": "°C", "s": "high"},
        "battery": {"v": 13.5, "u": "V", "s": "ok"}}})
    row = json.loads(p.read_text(encoding="utf-8").strip())
    assert row["anom"] == ["air_temp"]


def test_snapshot_logger_throttle_and_fault_change(tmp_path):
    from d2diag.web.logger import SnapshotLogger

    p = tmp_path / "log.jsonl"
    lg = SnapshotLogger(str(p), min_interval=999)  # high throttle → only fault change/first log
    snap = {"status": "connected",
            "signals": {"rpm": {"v": 800, "u": "rpm"}},
            "faults": ["air flow circuit (Current)"]}
    lg.log(snap)               # first → written
    lg.log(snap)               # unchanged + throttled → NOT written
    snap2 = dict(snap, faults=snap["faults"] + ["road speed missing (Logged)"])
    lg.log(snap2)              # fault change → written despite throttle

    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    r0, r1 = json.loads(lines[0]), json.loads(lines[1])
    assert r0["signals"]["rpm"] == 800
    assert r0["faults"] == ["air flow circuit (Current)"]
    assert r1.get("fault_change") is True
    assert "road speed missing (Logged)" in r1["faults"]


def test_resolve_serial_explicit_passthrough():
    from d2diag.web.sources import resolve_serial_port
    assert resolve_serial_port("/dev/ttyUSB3") == "/dev/ttyUSB3"


def test_resolve_serial_auto_prefers_known_chip(monkeypatch):
    import d2diag.web.sources as s

    mapping = {
        "/dev/serial/by-id/*": [
            "/dev/serial/by-id/usb-Prolific_PL2303-if00",
            "/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A1-if00-port0",
        ],
        "/dev/ttyUSB*": ["/dev/ttyUSB0", "/dev/ttyUSB1"],
        "/dev/ttyACM*": [],
    }
    monkeypatch.setattr(s.glob, "glob", lambda pat: mapping.get(pat, []))
    # prefers the FTDI match among the by-id links
    assert "FTDI" in s.resolve_serial_port("auto")


def test_resolve_serial_auto_macos_cu_port(monkeypatch):
    import d2diag.web.sources as s
    # macOS: no Linux ports, but a CH340 and an FTDI cable as cu.*
    mapping = {
        "/dev/cu.usbserial-*": ["/dev/cu.usbserial-0001"],
        "/dev/cu.wchusbserial*": ["/dev/cu.wchusbserial1420"],
    }
    monkeypatch.setattr(s.glob, "glob", lambda pat: mapping.get(pat, []))
    # prefers a known KKL chip (does usbserial match _KKL_HINTS "usb-serial"? no —
    # but "usbserial" does not; just verify that a cu.* port is chosen)
    assert s.resolve_serial_port("auto").startswith("/dev/cu.")


def test_resolve_serial_auto_mac_preferred_over_ttyusb(monkeypatch):
    import d2diag.web.sources as s
    mapping = {
        "/dev/cu.usbserial-*": ["/dev/cu.usbserial-FTDI99"],
        "/dev/ttyUSB*": ["/dev/ttyUSB0"],
    }
    monkeypatch.setattr(s.glob, "glob", lambda pat: mapping.get(pat, []))
    # mac cu.* (with FTDI hint) takes precedence over the generic ttyUSB fallback
    assert s.resolve_serial_port("auto") == "/dev/cu.usbserial-FTDI99"


def test_resolve_serial_auto_falls_back_to_ttyusb(monkeypatch):
    import d2diag.web.sources as s
    mapping = {"/dev/ttyUSB*": ["/dev/ttyUSB0"]}
    monkeypatch.setattr(s.glob, "glob", lambda pat: mapping.get(pat, []))
    assert s.resolve_serial_port("auto") == "/dev/ttyUSB0"


def test_resolve_serial_auto_none_raises(monkeypatch):
    import d2diag.web.sources as s
    import pytest
    monkeypatch.setattr(s.glob, "glob", lambda pat: [])
    with pytest.raises(FileNotFoundError):
        s.resolve_serial_port("auto")


def test_signal_upsert_and_list_round_trip(tmp_path, monkeypatch):
    from d2diag import signals as store
    from d2diag.web.server import _signal_upsert, _signals_list

    monkeypatch.setattr(store, "_DIR", tmp_path)
    store._CACHE.clear()
    (tmp_path / "slabs.json").write_text("[]", encoding="utf-8")

    ok = _signal_upsert({"module": "slabs", "record": {
        "name": "transport_mode", "lid": "45", "offset": 0, "kind": "bit", "bit": 3,
        "states": {"0": "off", "1": "on"}}})
    assert ok["ok"] and ok["module"] == "slabs"

    listing = _signals_list("slabs")
    assert [s["name"] for s in listing["signals"]] == ["transport_mode"]
    assert listing["signals"][0]["confidence"] == "kandidat"  # default


def test_fields_list_motor_maps_to_td5():
    from d2diag.web.server import _fields_list
    d = _fields_list("motor")                    # UI module "motor" → store "td5"
    names = {f["name"] for f in d["fields"]}
    assert d["module"] == "motor"
    assert {"rpm", "coolant_temp"} <= names       # lets the UI show the layout with no cable
    rpm = next(f for f in d["fields"] if f["name"] == "rpm")
    assert rpm["unit"] == "rpm" and rpm["c"] == "belagt"


def test_signal_upsert_validation():
    from d2diag.web.server import _signal_upsert
    assert not _signal_upsert({"module": "nope", "record": {"name": "x", "lid": "1", "offset": 0}})["ok"]
    assert not _signal_upsert({"module": "td5", "record": {"lid": "1"}})["ok"]  # missing name/offset


def test_read_block_command_returns_hex():
    from d2diag.kline import KLine, encode
    from d2diag.kwp2000 import KWP2000
    from d2diag.slabs import Slabs
    from d2diag.web.sources import SlabsDataSource
    from tests.fakes import FakeKLineEcu

    def _f(d):
        return encode(d, addressed=False)

    resp = {_f(b"\x21\x54"): _f(b"\x61\x54\x91\x9c")}
    src = SlabsDataSource(port="x", read_faults=False)
    src._slabs = Slabs(KWP2000(KLine(FakeKLineEcu(resp))))
    src._slabs.open()
    out = src.command("read_block", {"lids": ["54"]})
    assert out["ok"] and out["raws"] == {"54": "919c"}


def test_read_block_command_not_connected():
    from d2diag.web.sources import SlabsDataSource
    src = SlabsDataSource(port="x", read_faults=False)
    assert not src.command("read_block", {"lids": ["54"]})["ok"]  # _slabs is None


class _FakeSlabs:
    """Minimal SLABS stub that controls what read_data(0x54) returns (empty = silent bus)."""
    def __init__(self, height=b""): self._height = height
    def tester_present(self): pass
    def read_data(self, lid): return self._height
    def read_faults(self): return {"loggade": [], "aktuella": []}
    def close(self): pass


def test_slabs_empty_read_grace_keeps_session_then_reconnects(monkeypatch):
    # A silent poll cycle should NOT tear down the session immediately (full reconnect ~20 s).
    # The session is kept during the grace period and shows the last known values ("stale"),
    # only after _SLABS_EMPTY_GRACE empties in a row is it given up.
    from d2diag.web.sources import SlabsDataSource, _SLABS_EMPTY_GRACE
    src = SlabsDataSource(port="x", read_faults=False)
    src._slabs = _FakeSlabs(b"")           # the bus never responds (21 54 → empty)
    src._last_signals = {"height_left": {"v": 42, "u": "", "s": "ok", "c": "belagt"}}

    for _ in range(_SLABS_EMPTY_GRACE - 1):  # grace polls: connected+stale, session kept
        src._last_bus = 0.0                  # open the 1 Hz throttle: we want to reach the bus
        d = src.poll()
        assert d["status"] == "connected" and d.get("stale") is True
        assert d["signals"] == src._last_signals
        assert src._slabs is not None

    # Block reconnect (no hardware) so we see that the session is actually torn down.
    monkeypatch.setattr(src, "_connect", lambda: (_ for _ in ()).throw(RuntimeError("no cable")))
    src._last_bus = 0.0
    d = src.poll()                          # grace over → tear down + try to reconnect (fails)
    assert d["status"] == "error"
    assert src._slabs is None


def test_slabs_successful_read_resets_empty_streak():
    from d2diag.web.sources import SlabsDataSource
    src = SlabsDataSource(port="x", read_faults=False)
    src._slabs = _FakeSlabs(b"")                # silent bus
    src._last_bus = 0.0
    src.poll(); assert src._empty_streak == 1   # one empty cycle
    src._slabs = _FakeSlabs(b"\x91\x9c")        # the bus responds again (heights)
    src._last_bus = 0.0
    d = src.poll()
    assert d["status"] == "connected" and not d.get("stale")
    assert d["signals"]["height_left"]["v"] == 0x91
    assert src._empty_streak == 0               # reset by a successful read


def test_mode_toggle_switches_variant():
    from d2diag.web import MockDataSource, MockSlabsDataSource
    from d2diag.web.server import DiagServer

    mock_motor, live_motor = MockDataSource(), MockDataSource()
    variants = {"motor": {"mock": mock_motor, "live": live_motor},
                "slabs": {"mock": MockSlabsDataSource(), "live": MockSlabsDataSource()}}
    srv = DiagServer(host="127.0.0.1", port=0, variants=variants, mode="mock", active="motor")
    try:
        assert srv._mode == "mock" and srv._modes == ["live", "mock"]
        assert srv.source is mock_motor
        r = srv._set_mode("live")
        assert r["ok"] and srv._mode == "live" and srv.source is live_motor
        assert srv.latest["mode"] == "live" and srv.latest["modes"] == ["live", "mock"]
        assert not srv._set_mode("nope")["ok"]   # unknown mode rejected
    finally:
        srv.server_close()


def test_read_all_faults_command_mock():
    from d2diag.web import MockDataSource, MockSlabsDataSource
    from d2diag.web.server import DiagServer

    variants = {"motor": {"mock": MockDataSource(), "live": MockDataSource()},
                "slabs": {"mock": MockSlabsDataSource(), "live": MockSlabsDataSource()}}
    srv = DiagServer(host="127.0.0.1", port=0, variants=variants, mode="mock", active="motor")
    try:
        r = srv._read_all_faults()
        assert r["ok"] and r["mode"] == "mock"
        mods = {x["module"] for x in r["report"]}
        assert {"TD5", "SLABS", "Airbag"} <= mods
    finally:
        srv.server_close()


def test_fault_watch_sets_source_cadence():
    from d2diag.web import MockDataSource, MockSlabsDataSource
    from d2diag.web.server import DiagServer
    from d2diag.web.sources import SlabsDataSource, Td5DataSource

    variants = {"motor": {"mock": MockDataSource(), "live": Td5DataSource("x")},
                "slabs": {"mock": MockSlabsDataSource(), "live": SlabsDataSource("x")}}
    srv = DiagServer(host="127.0.0.1", port=0, variants=variants, mode="mock")
    try:
        assert variants["motor"]["live"].fault_every == 10        # default: ~5s
        r = srv.set_fault_watch(True)
        assert r["ok"] and r["fault_watch"] is True
        assert variants["motor"]["live"].fault_every == 1         # now every cycle
        assert variants["slabs"]["live"].fault_every == 1
        srv.set_fault_watch(False)
        assert variants["slabs"]["live"].fault_every == 10        # back to ~5s
    finally:
        srv.server_close()


def test_single_source_has_no_mode_toggle():
    from d2diag.web import MockDataSource
    from d2diag.web.server import DiagServer

    srv = DiagServer(MockDataSource(), host="127.0.0.1", port=0)   # backwards compat
    try:
        assert srv._modes == [] and srv.latest["modes"] == []
        assert not srv._set_mode("live")["ok"]
    finally:
        srv.server_close()


def test_slabs_source_light_poll_reads_heights_only():
    # LIGHT baseline poll (sniff 2026-08-07): the SLABS poll reads ONLY heights (21 54).
    # Store-driven block reading of many LIDs destabilised the session (~7×
    # bus traffic) and has been deliberately removed — see slabs_protocol.md.
    from d2diag.kline import KLine, encode
    from d2diag.kwp2000 import KWP2000
    from d2diag.slabs import Slabs
    from d2diag.web.sources import SlabsDataSource
    from tests.fakes import FakeKLineEcu

    def _f(d):
        return encode(d, addressed=False)

    resp = {
        _f(b"\x3e"): _f(b"\x7e"),                          # bare 3E keepalive (no sub)
        _f(b"\x21\x54"): _f(b"\x61\x54\x91\x9c\x0f\x0f"),   # heights 145/156
    }
    src = SlabsDataSource(port="x", read_faults=False)
    src._slabs = Slabs(KWP2000(KLine(FakeKLineEcu(resp))))
    src._slabs.open()
    out = src.poll()

    assert out["status"] == "connected"
    sig = out["signals"]
    assert sig["height_left"]["v"] == 145 and sig["height_right"]["v"] == 156
    # No heavy store-driven fields any more — only the four height fields are kept light.
    assert set(sig) == {"height_left", "height_right", "height_left_mm", "height_right_mm"}


def test_mock_clear_faults_command():
    src = MockDataSource()
    assert src.poll()["faults"]  # has faults from the start
    assert src.command("clear_faults")["ok"] is True
    assert src.poll()["faults"] == []  # empty right after the clear
    out = {}
    for _ in range(5):  # after a few polls the ACTIVE fault comes back
        out = src.poll()
    assert any("Current" in f for f in out["faults"])


def test_mock_unknown_command_fails():
    assert MockDataSource().command("frobnicate")["ok"] is False


def test_server_command_endpoint_clears():
    srv = DiagServer(MockDataSource(), host="127.0.0.1", port=0,
                     poll_interval=0.05, stream_interval=0.05)
    port = srv.server_address[1]
    srv.start_polling()
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        time.sleep(0.1)
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/command",
            data=json.dumps({"action": "clear_faults"}).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        d = json.loads(urllib.request.urlopen(req, timeout=3).read())
        assert d["ok"] is True
    finally:
        srv.shutdown()
        srv.server_close()
        srv.stop()


def test_server_serves_snapshot_and_html():
    srv = DiagServer(MockDataSource(), host="127.0.0.1", port=0,
                     poll_interval=0.05, stream_interval=0.05)
    port = srv.server_address[1]
    srv.start_polling()
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        time.sleep(0.2)  # let the background poller run at least once
        snap = json.loads(
            urllib.request.urlopen(f"http://127.0.0.1:{port}/snapshot", timeout=2).read()
        )
        assert snap["status"] == "connected"
        assert "rpm" in snap["signals"]
        html = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2).read().decode()
        assert "<title>" in html and "EventSource" in html
        assert "D2 Diag" in html  # "/" now serves v2, not v1
    finally:
        srv.shutdown()
        srv.server_close()
        srv.stop()


def _serve(srv):
    port = srv.server_address[1]
    srv.start_polling()
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    time.sleep(0.1)
    return port


def test_admin_gate_requires_password_when_set():
    import base64
    import urllib.error

    srv = DiagServer(MockDataSource(), host="127.0.0.1", port=0,
                     poll_interval=0.05, stream_interval=0.05,
                     admin_password="hemligt")
    base = f"http://127.0.0.1:{_serve(srv)}"
    try:
        # "/" (v2) is open, no auth
        assert "D2 Diag" in urllib.request.urlopen(base + "/", timeout=2).read().decode()
        # /admin without password → 401
        with pytest.raises(urllib.error.HTTPError) as ei:
            urllib.request.urlopen(base + "/admin", timeout=2)
        assert ei.value.code == 401
        # /admin with the correct password → same v2 app (admin mode reveals mapping tabs)
        cred = base64.b64encode(b"x:hemligt").decode()
        req = urllib.request.Request(base + "/admin", headers={"Authorization": f"Basic {cred}"})
        assert "D2 Diag" in urllib.request.urlopen(req, timeout=2).read().decode()
        # /v1 with the correct password → the old console (kept as reference)
        req1 = urllib.request.Request(base + "/v1", headers={"Authorization": f"Basic {cred}"})
        assert "Discovery 2" in urllib.request.urlopen(req1, timeout=2).read().decode()
        # gated mapping POST without password → 401
        with pytest.raises(urllib.error.HTTPError) as ei2:
            urllib.request.urlopen(
                urllib.request.Request(base + "/signal", data=b"{}", method="POST"), timeout=2)
        assert ei2.value.code == 401
    finally:
        srv.shutdown()
        srv.server_close()
        srv.stop()


def test_raw_log_wraps_transport(tmp_path):
    from d2diag.transport import LoggingTransport, SerialTransport
    from d2diag.web.sources import (SlabsDataSource, Td5DataSource, _raw_log_path,
                                    _transport)

    # off by default
    assert _raw_log_path("td5", None) is None
    assert Td5DataSource("auto")._raw_log_path is None
    # on when a dir is given
    p = _raw_log_path("td5", str(tmp_path))
    assert p and p.endswith(".log") and "raw-td5-" in p
    # _transport wraps in LoggingTransport only when a path is set
    assert isinstance(_transport("loop://", None), SerialTransport)
    assert isinstance(_transport("loop://", str(tmp_path / "r.log")), LoggingTransport)
    # both live sources pick up raw_log_dir
    assert Td5DataSource("auto", raw_log_dir=str(tmp_path))._raw_log_path
    assert SlabsDataSource("auto", raw_log_dir=str(tmp_path))._raw_log_path


def test_admin_ungated_without_password():
    srv = DiagServer(MockDataSource(), host="127.0.0.1", port=0,
                     poll_interval=0.05, stream_interval=0.05)  # no password set
    base = f"http://127.0.0.1:{_serve(srv)}"
    try:
        # without a password /admin is open (local dev / backwards compatible) — serves v2
        assert "D2 Diag" in urllib.request.urlopen(base + "/admin", timeout=2).read().decode()
    finally:
        srv.shutdown()
        srv.server_close()
        srv.stop()


class _RecordingSession:
    """Stub that distinguishes release() (clean module switch) from close() (error path)."""
    def __init__(self): self.calls = []
    def release(self): self.calls.append("release")
    def close(self): self.calls.append("close")


def test_td5_disconnect_releases_session_not_just_close():
    # Module switch on a shared bus: the TD5 session should be ended cleanly (StopDiagnosticSession)
    # before the port is released, otherwise SLABS gets 7F 81 10 on its init.
    from d2diag.web.sources import Td5DataSource
    src = Td5DataSource(port="x", read_faults=False)
    sess = _RecordingSession()
    src._td5 = sess
    src.disconnect()
    assert sess.calls == ["release"]
    assert src._td5 is None and not src.is_connected()


def test_slabs_disconnect_releases_session():
    from d2diag.web.sources import SlabsDataSource
    src = SlabsDataSource(port="x", read_faults=False)
    sess = _RecordingSession()
    src._slabs = sess
    src.disconnect()
    assert sess.calls == ["release"]   # no-op for SLABS (no session), but symmetric
    assert src._slabs is None


def test_module_switch_disconnects_previous_source():
    # DiagServer._select should release the old session before the new module is selected.
    from d2diag.web.server import DiagServer
    from d2diag.web.sources import MockDataSource, MockSlabsDataSource

    td5, slabs = MockDataSource(), MockSlabsDataSource()
    dropped = []
    td5.disconnect = lambda: dropped.append("td5")  # type: ignore[method-assign]

    srv = DiagServer({"td5": td5, "slabs": slabs}, host="127.0.0.1", port=0, active="td5")
    try:
        assert srv._select("slabs")["ok"] is True
        assert dropped == ["td5"]                  # the old module released
        assert srv.source is slabs and srv.latest["status"] == "connecting"
    finally:
        srv.server_close()


def test_fault_watch_command_runs_inline():
    # set_fault_watch only writes attributes on the sources → should not be queued behind an
    # ongoing connection in the poll thread (no poller runs in the test).
    from d2diag.web.server import DiagServer
    from d2diag.web.sources import MockDataSource

    srv = DiagServer(MockDataSource(), host="127.0.0.1", port=0)
    try:
        r = srv.enqueue_command({"action": "set_fault_watch", "params": {"on": True}})
        assert r["ok"] and r["fault_watch"] is True
        assert srv._commands.empty()
        assert srv.enqueue_command({"action": "set_fault_watch",
                                    "params": {"on": False}})["fault_watch"] is False
    finally:
        srv.server_close()


def test_shutdown_is_guarded_and_inline():
    # The Settings "Shut down Pi" button posts {action:"shutdown"}. It runs INLINE
    # (never queued behind K-line) and is refused unless --allow-shutdown was set,
    # so dev on a laptop can never power off the host.
    from d2diag.web.server import DiagServer
    from d2diag.web.sources import MockDataSource

    off = DiagServer(MockDataSource(), host="127.0.0.1", port=0)  # allow_shutdown default False
    try:
        r = off.enqueue_command({"action": "shutdown"})
        assert not r["ok"] and "not enabled" in r["error"]
        assert off._commands.empty()               # inline — never touched the poll queue
        assert off.latest["allow_shutdown"] is False
    finally:
        off.server_close()

    on = DiagServer(MockDataSource(), host="127.0.0.1", port=0, allow_shutdown=True)
    calls = []
    on._spawn_poweroff = lambda: calls.append(True)  # stub — must NOT power off the test host
    try:
        r = on.enqueue_command({"action": "shutdown"})
        assert r["ok"] and r["shutting_down"] is True and calls == [True]
        assert on._commands.empty()
        assert on.latest["allow_shutdown"] is True
    finally:
        on.server_close()


def test_ecu_commands_still_go_through_the_poll_queue():
    # The opposite: anything touching K-line MUST be serialized with the poll. Without a poller
    # the queue is never drained → the command times out (short timeout here).
    from d2diag.web.server import DiagServer
    from d2diag.web.sources import MockDataSource

    srv = DiagServer(MockDataSource(), host="127.0.0.1", port=0)
    try:
        r = srv.enqueue_command({"action": "clear_faults"}, timeout=0.2)
        assert r["ok"] is False and "timeout" in r["error"]
        assert not srv._commands.empty()          # stays in the queue for the poller
    finally:
        srv.server_close()


def test_connect_sleep_aborts_when_a_command_is_queued():
    # The SLABS silent period is 28 s and a full establishment ~90 s. If the poll thread sleeps
    # through it while a module switch is queued, the UI times out despite a valid command.
    from d2diag.web.server import ConnectAborted, DiagServer
    from d2diag.web.sources import MockDataSource

    srv = DiagServer(MockDataSource(), host="127.0.0.1", port=0)
    try:
        srv._connect_sleep(0.05)                    # empty queue → sleeps to completion
        srv._commands.put(({"action": "select_module"}, {}))
        with pytest.raises(ConnectAborted):
            srv._connect_sleep(30)                  # queued command → aborts immediately
    finally:
        srv.server_close()


def test_sources_get_the_interruptible_sleep_hook():
    from d2diag.web.server import DiagServer
    from d2diag.web.sources import MockDataSource

    src = MockDataSource()
    srv = DiagServer(src, host="127.0.0.1", port=0)
    try:
        assert src.on_sleep == srv._connect_sleep
    finally:
        srv.server_close()


class _CountingSlabs(_FakeSlabs):
    """Counts bus calls so the throttling can be measured."""
    def __init__(self, height=b"\x91\x9c"):
        super().__init__(height)
        self.calls = 0
    def tester_present(self): self.calls += 1
    def read_data(self, lid):
        self.calls += 1
        return self._height


def test_slabs_poll_reads_store_lids_by_rotation():
    # The experimental mode should show more than heights: the poll reads 21 54 every cycle and
    # rotates ONE extra store LID per cycle (keeps traffic at ~1 Hz). Over several
    # cycles all store fields are filled in without any single cycle block-reading.
    from d2diag.kline import KLine, encode
    from d2diag.kwp2000 import KWP2000
    from d2diag.slabs import Slabs
    from d2diag.web.sources import SlabsDataSource
    from tests.fakes import FakeKLineEcu

    def _f(d):
        return encode(d, addressed=False)

    resp = {
        _f(b"\x3e"): _f(b"\x7e"),
        _f(b"\x21\x54"): _f(b"\x61\x54\x95\xa4\x0f\x0f"),   # heights 149/164
        _f(b"\x21\x56"): _f(b"\x61\x56\x01\x0f\x0f\x0f"),   # any_door bit0=1
        _f(b"\x21\x43"): _f(b"\x61\x43\x7c\x00\x7c\x00\x7c\x00\x7c\x00"),  # 4×wheel u16le=124
        _f(b"\x21\x50"): _f(b"\x61\x50\x72\x73\x73\x72"),   # abs_sensor_fr=0x72
        _f(b"\x21\x44"): _f(b"\x61\x44" + bytes(12) + b"\xe0\xdc"),  # battery 0xe0*0.0625=14.0
    }
    src = SlabsDataSource(port="x", read_faults=False)
    src._slabs = Slabs(KWP2000(KLine(FakeKLineEcu(resp))))
    src._extra_lids = [0x43, 0x44, 0x50, 0x56]   # as _connect would set

    seen = {}
    for _ in range(6):                # 6 cycles → all 4 extra LIDs get read
        src._last_bus = 0.0           # open the 1 Hz throttle
        out = src.poll()
        seen.update(out["signals"])
    assert out["status"] == "connected"
    assert seen["height_left"]["v"] == 149 and seen["height_right"]["v"] == 164
    assert seen["any_door"]["v"] == 1.0
    assert seen["wheel_speed_fr"]["v"] == 124   # u16le of 7c 00
    assert round(seen["battery"]["v"], 1) == 14.0
    # confidence flows from the store
    assert seen["height_left"]["c"] == "belagt"
    assert seen["wheel_speed_fr"]["c"] == "kandidat"


def test_slabs_poll_is_throttled_to_one_hz():
    # The server polls at 2 Hz but SLABS can't take it: the reference tool ran ~1 Hz
    # (keepalive was every ~1048 ms). Extra polls should return cached values WITHOUT
    # touching the bus — otherwise we send 4 frames/s and the session dies (~21 s in the car).
    from d2diag.web.sources import SlabsDataSource, _SLABS_BUS_PERIOD
    src = SlabsDataSource(port="x", read_faults=False)
    sess = _CountingSlabs()
    src._slabs = sess

    first = src.poll()                       # the first poll reaches the bus
    assert sess.calls == 2                   # 3E + 21 54
    assert first["signals"]["height_left"]["v"] == 0x91

    cached = src.poll()                      # right away again → no traffic
    assert sess.calls == 2
    assert cached["status"] == "connected"
    assert cached["signals"] == first["signals"]

    src._last_bus -= _SLABS_BUS_PERIOD       # pretend a second has passed
    src.poll()
    assert sess.calls == 4                   # the bus is reached again


def test_slabs_faults_are_read_on_a_slow_clock():
    # Fault codes cost two extra frames → their own cadence in seconds, independent of
    # fault_watch (which otherwise sets fault_every=1 on all sources).
    from d2diag.web.sources import SlabsDataSource, _SLABS_FAULT_PERIOD
    src = SlabsDataSource(port="x", read_faults=True)
    reads = []

    class _S(_CountingSlabs):
        def read_faults(self):
            reads.append(1)
            return {"loggade": [], "aktuella": []}

    src._slabs = _S()
    src.fault_every = 1                      # fault watch on → should NOT affect SLABS
    src.poll()
    assert len(reads) == 1                   # the first poll reads once
    src._last_bus = 0.0
    src.poll()
    assert len(reads) == 1                   # but not again right away
    src._last_bus = 0.0
    src._last_fault -= _SLABS_FAULT_PERIOD   # pretend 30 s has passed
    src.poll()
    assert len(reads) == 2


def test_connection_log_notes_each_module_separately(tmp_path):
    # Switching from one connected module to another: status is "connected" at both
    # ends. If the transition is keyed only on status the new module's row falls silent — that
    # hid a successful SLABS session 2026-08-18 23:08:54.
    from d2diag.web.server import DiagServer
    from d2diag.web.sources import MockDataSource

    class _Liveish(MockDataSource):              # the name must not start with "Mock"
        name = "motor"

    srv = DiagServer(_Liveish(), host="127.0.0.1", port=0, csv_dir=str(tmp_path))
    try:
        srv._mode = "live"                       # mock sources are otherwise not logged
        srv._log_conn_transition({"module": "motor", "status": "connected", "signals": {"rpm": 1}})
        srv._log_conn_transition({"module": "slabs", "status": "connected", "signals": {"h": 1}})
        srv._log_conn_transition({"module": "slabs", "status": "connected", "signals": {"h": 1}})
        lines = (tmp_path / "connection.log").read_text().strip().splitlines()
    finally:
        srv.server_close()
    assert len(lines) == 2                       # one row per module, no repetition
    assert "[motor/live]" in lines[0] and "[slabs/live]" in lines[1]


def test_repeated_connect_phase_is_logged_once(tmp_path):
    # Without a cable the reconnect shouts "opening the cable" 2×/s forever
    # (1.9 MB of noise in an evening) and drowns out the lines you're debugging with.
    from d2diag.web.server import DiagServer
    from d2diag.web.sources import MockDataSource

    srv = DiagServer(MockDataSource(), host="127.0.0.1", port=0, csv_dir=str(tmp_path))
    try:
        for _ in range(5):
            srv._connect_progress("opening the cable")
        srv._connect_progress("sending init (try 1/3)")   # new text → new row
        lines = (tmp_path / "connection.log").read_text().strip().splitlines()
    finally:
        srv.server_close()
    assert len(lines) == 2


def test_init_lines_carry_the_last_known_engine_context(tmp_path):
    # K-line is shared: we can't read the engine while SLABS is active. Without the
    # last known context there's no way to tell afterwards whether a silent
    # init attempt was made while moving (SLABS refuses comms >8–20 km/h) or stationary.
    from d2diag.web.server import DiagServer
    from d2diag.web.sources import MockDataSource

    srv = DiagServer(MockDataSource(), host="127.0.0.1", port=0, csv_dir=str(tmp_path))
    try:
        srv._remember_engine({"signals": {
            "rpm": {"v": 761.0}, "battery": {"v": 13.93}, "speed": {"v": 0.0}}})
        srv._connect_progress("sending init (try 1/3)")
        srv._connect_progress("waiting for the bus to settle")   # no context here
        lines = (tmp_path / "connection.log").read_text().strip().splitlines()
    finally:
        srv.server_close()
    assert "motor: rpm 761, 0 km/h, 13.9 V" in lines[0]
    assert "motor:" not in lines[1]


def test_conf_of_reads_store():
    # The confidence filter (Verified/Experimental) reads the store. After rpm_error
    # and the balance fields were promoted 2026-08-19, maf (1D u16@4) is a remaining
    # TD5 candidate — field proven but the kg/hr scale awaits a factory reference.
    from d2diag.web.sources import _conf_map, _conf_of
    conf = _conf_map("td5")
    assert _conf_of("td5", "rpm_error", conf) == "belagt"
    assert _conf_of("td5", "balance_3", conf) == "belagt"
    assert _conf_of("td5", "maf", conf) == "kandidat"


def test_fuel_computer_rate_trip_economy():
    from d2diag.web.sources import _FuelComputer
    t = [0.0]
    fc = _FuelComputer(clock=lambda: t[0])
    # idle: 12 mg/stroke, 750 rpm, stationary → ~1.62 L/h, no economy (not moving)
    r = fc.update(12.0, 750, 0)
    assert abs(r["fuel_rate"] - 1.62) < 0.1
    assert "economy" not in r
    # drive 10 s: 20 mg/stroke, 2000 rpm, 90 km/h in 1 s steps
    for _ in range(10):
        t[0] += 1.0
        r = fc.update(20.0, 2000, 90)
    assert abs(r["fuel_rate"] - 7.21) < 0.1        # L/h
    assert 6 < r["economy"] < 10                    # momentary L/100km
    assert 6 < r["trip_economy"] < 10               # trip average
