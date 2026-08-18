"""Tester för webbdashboarden: mock-källans form + att servern serverar."""
import json
import threading
import time
import urllib.request

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
    assert d["signals"]["rpm_error"]["c"] == "kandidat"        # experimental → hidden in Verified view
    assert isinstance(d["faults"], list) and d["faults"]


def test_signal_status_ranges():
    from d2diag.td5.identifiers import signal_status
    assert signal_status("battery", 13.5) == "ok"
    assert signal_status("battery", 10.0) == "low"
    assert signal_status("coolant_temp", 120) == "high"
    assert signal_status("ext_temp", 150) is None   # oansluten givare → flaggas ej
    assert signal_status("maf_raw", 999) is None
    assert signal_status("okänd", 1) is None


def test_mock_signals_include_status_and_flag_iat():
    d = MockDataSource().poll()
    assert "s" in d["signals"]["rpm"]
    assert d["signals"]["air_temp"]["s"] == "high"   # mock IAT 120 °C → högt
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
    lg = SnapshotLogger(str(p), min_interval=999)  # hög throttle → bara feländring/förstalog
    snap = {"status": "connected",
            "signals": {"rpm": {"v": 800, "u": "rpm"}},
            "faults": ["air flow circuit (Current)"]}
    lg.log(snap)               # första → skrivs
    lg.log(snap)               # oförändrat + throttlat → skrivs INTE
    snap2 = dict(snap, faults=snap["faults"] + ["road speed missing (Logged)"])
    lg.log(snap2)              # feländring → skrivs trots throttle

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
    # föredrar FTDI-matchen bland by-id-länkarna
    assert "FTDI" in s.resolve_serial_port("auto")


def test_resolve_serial_auto_macos_cu_port(monkeypatch):
    import d2diag.web.sources as s
    # macOS: inga Linux-portar, men en CH340- och en FTDI-kabel som cu.*
    mapping = {
        "/dev/cu.usbserial-*": ["/dev/cu.usbserial-0001"],
        "/dev/cu.wchusbserial*": ["/dev/cu.wchusbserial1420"],
    }
    monkeypatch.setattr(s.glob, "glob", lambda pat: mapping.get(pat, []))
    # föredrar en känd KKL-chip (usbserial matchar _KKL_HINTS "usb-serial"? nej —
    # men "usbserial" gör inte det; verifiera bara att en cu.*-port väljs)
    assert s.resolve_serial_port("auto").startswith("/dev/cu.")


def test_resolve_serial_auto_mac_preferred_over_ttyusb(monkeypatch):
    import d2diag.web.sources as s
    mapping = {
        "/dev/cu.usbserial-*": ["/dev/cu.usbserial-FTDI99"],
        "/dev/ttyUSB*": ["/dev/ttyUSB0"],
    }
    monkeypatch.setattr(s.glob, "glob", lambda pat: mapping.get(pat, []))
    # mac cu.* (med FTDI-hint) går före den generiska ttyUSB-fallbacken
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
        "states": {"0": "av", "1": "på"}}})
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
    assert not _signal_upsert({"module": "td5", "record": {"lid": "1"}})["ok"]  # saknar name/offset


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
    """Minimal SLABS-stub som styr vad read_block returnerar (tomt = tyst buss)."""
    def __init__(self, raws): self._raws = raws
    def tester_present(self): pass
    def read_block(self, lids): return self._raws
    def read_faults(self): return {"loggade": [], "aktuella": []}
    def close(self): pass


def test_slabs_empty_read_grace_keeps_session_then_reconnects(monkeypatch):
    # En tyst pollcykel ska INTE riva sessionen direkt (full reconnect ~20 s).
    # Sessionen behålls i nåd-perioden och visar senaste kända värden ("stale"),
    # först efter _SLABS_EMPTY_GRACE tomma i rad ges den upp.
    from d2diag.web.sources import SlabsDataSource, _SLABS_EMPTY_GRACE
    src = SlabsDataSource(port="x", read_faults=False)
    src._slabs = _FakeSlabs({})            # bussen svarar aldrig
    src._last_signals = {"height_left": {"v": 42, "u": "", "s": "ok", "c": "belagt"}}

    for _ in range(_SLABS_EMPTY_GRACE - 1):  # nåd-pollar: connected+stale, session kvar
        d = src.poll()
        assert d["status"] == "connected" and d.get("stale") is True
        assert d["signals"] == src._last_signals
        assert src._slabs is not None

    # Blockera reconnect (ingen hårdvara) så vi ser att sessionen faktiskt revs.
    monkeypatch.setattr(src, "_connect", lambda: (_ for _ in ()).throw(RuntimeError("no cable")))
    d = src.poll()                          # nåd slut → riv + försök koppla om (misslyckas)
    assert d["status"] == "error"
    assert src._slabs is None


def test_slabs_successful_read_resets_empty_streak():
    from d2diag.web.sources import SlabsDataSource
    src = SlabsDataSource(port="x", read_faults=False)
    src._slabs = _FakeSlabs({})
    src.poll(); assert src._empty_streak == 1        # en tom cykel
    src._slabs = _FakeSlabs({"54": b"\x91\x9c"})     # bussen svarar igen
    d = src.poll()
    assert d["status"] == "connected" and not d.get("stale")
    assert src._empty_streak == 0                    # nollställd av lyckad läsning


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
        assert not srv._set_mode("nope")["ok"]   # okänt läge avvisas
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

    srv = DiagServer(MockDataSource(), host="127.0.0.1", port=0)   # bakåtkompat
    try:
        assert srv._modes == [] and srv.latest["modes"] == []
        assert not srv._set_mode("live")["ok"]
    finally:
        srv.server_close()


def test_slabs_source_decodes_live_via_store():
    # Binder ihop read_block (EcuSession) + signalstoren i SlabsDataSource.poll.
    from d2diag.kline import KLine, encode
    from d2diag.kwp2000 import KWP2000
    from d2diag.slabs import Slabs
    from d2diag.web.sources import SlabsDataSource
    from tests.fakes import FakeKLineEcu

    def _f(d):
        return encode(d, addressed=False)

    resp = {
        _f(b"\x3e\x01"): _f(b"\x7e\x01"),                       # tester_present
        _f(b"\x21\x54"): _f(b"\x61\x54\x91\x9c\x0f\x0f"),        # höjder 145/156
        _f(b"\x21\x56"): _f(b"\x61\x56\x01\x0f\x0f\x0f"),        # any_door bit0=1 (öppen)
        _f(b"\x21\x43"): _f(b"\x61\x43\x7c\x00\x7c\x00\x7c\x00\x7c\x00"),
        _f(b"\x21\x50"): _f(b"\x61\x50\x72\x73\x73\x72"),
        _f(b"\x21\x44"): _f(b"\x61\x44" + bytes(14)),            # batteri/ecu_supply = 0
    }
    src = SlabsDataSource(port="x", read_faults=False)
    src._slabs = Slabs(KWP2000(KLine(FakeKLineEcu(resp))))
    src._slabs.open()
    out = src.poll()

    assert out["status"] == "connected"
    sig = out["signals"]
    assert sig["height_left"]["v"] == 145 and sig["height_right"]["v"] == 156   # SVG-fält
    assert "battery" in sig and "ecu_supply" in sig                            # store-drivna
    assert "any_door" not in sig    # state-fält → visas i Karta (decode_known), ej som numerisk gauge


def test_mock_clear_faults_command():
    src = MockDataSource()
    assert src.poll()["faults"]  # har fel från början
    assert src.command("clear_faults")["ok"] is True
    assert src.poll()["faults"] == []  # tomt direkt efter radering
    out = {}
    for _ in range(5):  # efter några polls återkommer det AKTIVA felet
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
        time.sleep(0.2)  # låt bakgrundspollern köra minst en gång
        snap = json.loads(
            urllib.request.urlopen(f"http://127.0.0.1:{port}/snapshot", timeout=2).read()
        )
        assert snap["status"] == "connected"
        assert "rpm" in snap["signals"]
        html = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2).read().decode()
        assert "<title>" in html and "EventSource" in html
    finally:
        srv.shutdown()
        srv.server_close()
        srv.stop()
