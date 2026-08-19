"""Tester för webbdashboarden: mock-källans form + att servern serverar."""
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
    # rpm_error och balance_1..5 befordrades till belagt 2026-08-19 (labeled_captures
    # 21/40 = "korrekt", värden varierar över captures). Kvarvarande TD5-kandidater
    # (maf_raw, accel_way3, ext_temp) emitteras inte av mocken, så confidence-
    # filtret testas separat i test_conf_of_reads_store.
    assert d["signals"]["rpm_error"]["c"] == "belagt"
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
    """Minimal SLABS-stub som styr vad read_data(0x54) returnerar (tomt = tyst buss)."""
    def __init__(self, height=b""): self._height = height
    def tester_present(self): pass
    def read_data(self, lid): return self._height
    def read_faults(self): return {"loggade": [], "aktuella": []}
    def close(self): pass


def test_slabs_empty_read_grace_keeps_session_then_reconnects(monkeypatch):
    # En tyst pollcykel ska INTE riva sessionen direkt (full reconnect ~20 s).
    # Sessionen behålls i nåd-perioden och visar senaste kända värden ("stale"),
    # först efter _SLABS_EMPTY_GRACE tomma i rad ges den upp.
    from d2diag.web.sources import SlabsDataSource, _SLABS_EMPTY_GRACE
    src = SlabsDataSource(port="x", read_faults=False)
    src._slabs = _FakeSlabs(b"")           # bussen svarar aldrig (21 54 → tomt)
    src._last_signals = {"height_left": {"v": 42, "u": "", "s": "ok", "c": "belagt"}}

    for _ in range(_SLABS_EMPTY_GRACE - 1):  # nåd-pollar: connected+stale, session kvar
        src._last_bus = 0.0                  # öppna 1 Hz-strypningen: vi vill nå bussen
        d = src.poll()
        assert d["status"] == "connected" and d.get("stale") is True
        assert d["signals"] == src._last_signals
        assert src._slabs is not None

    # Blockera reconnect (ingen hårdvara) så vi ser att sessionen faktiskt revs.
    monkeypatch.setattr(src, "_connect", lambda: (_ for _ in ()).throw(RuntimeError("no cable")))
    src._last_bus = 0.0
    d = src.poll()                          # nåd slut → riv + försök koppla om (misslyckas)
    assert d["status"] == "error"
    assert src._slabs is None


def test_slabs_successful_read_resets_empty_streak():
    from d2diag.web.sources import SlabsDataSource
    src = SlabsDataSource(port="x", read_faults=False)
    src._slabs = _FakeSlabs(b"")                # tyst buss
    src._last_bus = 0.0
    src.poll(); assert src._empty_streak == 1   # en tom cykel
    src._slabs = _FakeSlabs(b"\x91\x9c")        # bussen svarar igen (höjder)
    src._last_bus = 0.0
    d = src.poll()
    assert d["status"] == "connected" and not d.get("stale")
    assert d["signals"]["height_left"]["v"] == 0x91
    assert src._empty_streak == 0               # nollställd av lyckad läsning


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


def test_slabs_source_light_poll_reads_heights_only():
    # LÄTT baslinje-poll (sniff 2026-08-07): SLABS-pollen läser BARA höjder (21 54).
    # Store-driven block-läsning av många LID:er destabiliserade sessionen (~7×
    # busstrafik) och är medvetet borttagen — se slabs_protocol.md.
    from d2diag.kline import KLine, encode
    from d2diag.kwp2000 import KWP2000
    from d2diag.slabs import Slabs
    from d2diag.web.sources import SlabsDataSource
    from tests.fakes import FakeKLineEcu

    def _f(d):
        return encode(d, addressed=False)

    resp = {
        _f(b"\x3e"): _f(b"\x7e"),                          # bar 3E-keepalive (utan sub)
        _f(b"\x21\x54"): _f(b"\x61\x54\x91\x9c\x0f\x0f"),   # höjder 145/156
    }
    src = SlabsDataSource(port="x", read_faults=False)
    src._slabs = Slabs(KWP2000(KLine(FakeKLineEcu(resp))))
    src._slabs.open()
    out = src.poll()

    assert out["status"] == "connected"
    sig = out["signals"]
    assert sig["height_left"]["v"] == 145 and sig["height_right"]["v"] == 156
    # Inga tunga store-drivna fält längre — bara de fyra höjd-fälten hålls lätta.
    assert set(sig) == {"height_left", "height_right", "height_left_mm", "height_right_mm"}


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


class _RecordingSession:
    """Stub som skiljer på release() (rent modulbyte) och close() (felväg)."""
    def __init__(self): self.calls = []
    def release(self): self.calls.append("release")
    def close(self): self.calls.append("close")


def test_td5_disconnect_releases_session_not_just_close():
    # Modulbyte på delad buss: TD5-sessionen ska avslutas rent (StopDiagnosticSession)
    # innan porten släpps, annars får SLABS 7F 81 10 på sin init.
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
    assert sess.calls == ["release"]   # no-op för SLABS (ingen session), men symmetriskt
    assert src._slabs is None


def test_module_switch_disconnects_previous_source():
    # DiagServer._select ska släppa den gamla sessionen innan den nya modulen väljs.
    from d2diag.web.server import DiagServer
    from d2diag.web.sources import MockDataSource, MockSlabsDataSource

    td5, slabs = MockDataSource(), MockSlabsDataSource()
    dropped = []
    td5.disconnect = lambda: dropped.append("td5")  # type: ignore[method-assign]

    srv = DiagServer({"td5": td5, "slabs": slabs}, host="127.0.0.1", port=0, active="td5")
    try:
        assert srv._select("slabs")["ok"] is True
        assert dropped == ["td5"]                  # gamla modulen släppt
        assert srv.source is slabs and srv.latest["status"] == "connecting"
    finally:
        srv.server_close()


def test_fault_watch_command_runs_inline():
    # set_fault_watch skriver bara attribut på källorna → ska inte köas bakom en
    # pågående anslutning i pollertråden (ingen poller körs i testet).
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


def test_ecu_commands_still_go_through_the_poll_queue():
    # Motsatsen: allt som rör K-line MÅSTE serialiseras med pollen. Utan poller
    # dräneras kön aldrig → kommandot timeoutar (kort timeout här).
    from d2diag.web.server import DiagServer
    from d2diag.web.sources import MockDataSource

    srv = DiagServer(MockDataSource(), host="127.0.0.1", port=0)
    try:
        r = srv.enqueue_command({"action": "clear_faults"}, timeout=0.2)
        assert r["ok"] is False and "timeout" in r["error"]
        assert not srv._commands.empty()          # ligger kvar i kön till pollern
    finally:
        srv.server_close()


def test_connect_sleep_aborts_when_a_command_is_queued():
    # SLABS tysta period är 28 s och en full etablering ~90 s. Sover pollertråden
    # ut den medan ett modulbyte står i kön får UI:t timeout trots giltigt kommando.
    from d2diag.web.server import ConnectAborted, DiagServer
    from d2diag.web.sources import MockDataSource

    srv = DiagServer(MockDataSource(), host="127.0.0.1", port=0)
    try:
        srv._connect_sleep(0.05)                    # tom kö → sover klart
        srv._commands.put(({"action": "select_module"}, {}))
        with pytest.raises(ConnectAborted):
            srv._connect_sleep(30)                  # köat kommando → avbryter direkt
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
    """Räknar bussanrop så strypningen kan mätas."""
    def __init__(self, height=b"\x91\x9c"):
        super().__init__(height)
        self.calls = 0
    def tester_present(self): self.calls += 1
    def read_data(self, lid):
        self.calls += 1
        return self._height


def test_slabs_poll_reads_store_lids_by_rotation():
    # Experimentläget ska visa mer än höjder: pollen läser 21 54 varje cykel och
    # roterar EN extra store-LID per cykel (håller trafiken på ~1 Hz). Över flera
    # cykler fylls alla store-fält i utan att någon enskild cykel block-läser.
    from d2diag.kline import KLine, encode
    from d2diag.kwp2000 import KWP2000
    from d2diag.slabs import Slabs
    from d2diag.web.sources import SlabsDataSource
    from tests.fakes import FakeKLineEcu

    def _f(d):
        return encode(d, addressed=False)

    resp = {
        _f(b"\x3e"): _f(b"\x7e"),
        _f(b"\x21\x54"): _f(b"\x61\x54\x95\xa4\x0f\x0f"),   # höjder 149/164
        _f(b"\x21\x56"): _f(b"\x61\x56\x01\x0f\x0f\x0f"),   # any_door bit0=1
        _f(b"\x21\x43"): _f(b"\x61\x43\x00\x7c\x00\x7c\x00\x7c\x00\x7c"),  # wheel_speed_fr u16=0x007c
        _f(b"\x21\x50"): _f(b"\x61\x50\x72\x73\x73\x72"),   # abs_sensor_fr=0x72
        _f(b"\x21\x44"): _f(b"\x61\x44" + bytes(12) + b"\xe0\xdc"),  # batteri 0xe0*0.0625=14.0
    }
    src = SlabsDataSource(port="x", read_faults=False)
    src._slabs = Slabs(KWP2000(KLine(FakeKLineEcu(resp))))
    src._extra_lids = [0x43, 0x44, 0x50, 0x56]   # som _connect skulle sätta

    seen = {}
    for _ in range(6):                # 6 cykler → alla 4 extra-LID:er hinner läsas
        src._last_bus = 0.0           # öppna 1 Hz-strypningen
        out = src.poll()
        seen.update(out["signals"])
    assert out["status"] == "connected"
    assert seen["height_left"]["v"] == 149 and seen["height_right"]["v"] == 164
    assert seen["any_door"]["v"] == 1.0
    assert seen["wheel_speed_fr"]["v"] == 0x7c
    assert round(seen["battery"]["v"], 1) == 14.0
    # confidence flödar från storen
    assert seen["height_left"]["c"] == "belagt"
    assert seen["wheel_speed_fr"]["c"] == "kandidat"


def test_slabs_poll_is_throttled_to_one_hz():
    # Servern pollar 2 Hz men SLABS tål inte det: reference tool körde ~1 Hz
    # (keepalive var ~1048:e ms). Extra pollar ska returnera cachade värden UTAN
    # att röra bussen — annars skickar vi 4 ramar/s och sessionen dör (~21 s i bilen).
    from d2diag.web.sources import SlabsDataSource, _SLABS_BUS_PERIOD
    src = SlabsDataSource(port="x", read_faults=False)
    sess = _CountingSlabs()
    src._slabs = sess

    first = src.poll()                       # första pollen når bussen
    assert sess.calls == 2                   # 3E + 21 54
    assert first["signals"]["height_left"]["v"] == 0x91

    cached = src.poll()                      # direkt igen → ingen trafik
    assert sess.calls == 2
    assert cached["status"] == "connected"
    assert cached["signals"] == first["signals"]

    src._last_bus -= _SLABS_BUS_PERIOD       # låtsas att en sekund gått
    src.poll()
    assert sess.calls == 4                   # bussen nås igen


def test_slabs_faults_are_read_on_a_slow_clock():
    # Felkoder kostar två extra ramar → egen kadens i sekunder, oberoende av
    # fault_watch (som annars sätter fault_every=1 på alla källor).
    from d2diag.web.sources import SlabsDataSource, _SLABS_FAULT_PERIOD
    src = SlabsDataSource(port="x", read_faults=True)
    reads = []

    class _S(_CountingSlabs):
        def read_faults(self):
            reads.append(1)
            return {"loggade": [], "aktuella": []}

    src._slabs = _S()
    src.fault_every = 1                      # fault watch på → ska INTE påverka SLABS
    src.poll()
    assert len(reads) == 1                   # första pollen läser en gång
    src._last_bus = 0.0
    src.poll()
    assert len(reads) == 1                   # men inte igen direkt
    src._last_bus = 0.0
    src._last_fault -= _SLABS_FAULT_PERIOD   # låtsas att 30 s gått
    src.poll()
    assert len(reads) == 2


def test_connection_log_notes_each_module_separately(tmp_path):
    # Byte från en uppkopplad modul till en annan: status är "connected" i båda
    # ändar. Nycklas övergången bara på status tystnar den nya modulens rad — det
    # gömde en lyckad SLABS-session 2026-08-18 23:08:54.
    from d2diag.web.server import DiagServer
    from d2diag.web.sources import MockDataSource

    class _Liveish(MockDataSource):              # namnet får inte börja på "Mock"
        name = "motor"

    srv = DiagServer(_Liveish(), host="127.0.0.1", port=0, csv_dir=str(tmp_path))
    try:
        srv._mode = "live"                       # mock-källor loggas annars inte
        srv._log_conn_transition({"module": "motor", "status": "connected", "signals": {"rpm": 1}})
        srv._log_conn_transition({"module": "slabs", "status": "connected", "signals": {"h": 1}})
        srv._log_conn_transition({"module": "slabs", "status": "connected", "signals": {"h": 1}})
        lines = (tmp_path / "connection.log").read_text().strip().splitlines()
    finally:
        srv.server_close()
    assert len(lines) == 2                       # en rad per modul, ingen upprepning
    assert "[motor/live]" in lines[0] and "[slabs/live]" in lines[1]


def test_repeated_connect_phase_is_logged_once(tmp_path):
    # Utan kabel ropar återanslutningen "opening the cable" 2 ggr/s i all evighet
    # (1,9 MB brus på en kväll) och dränker raderna man felsöker med.
    from d2diag.web.server import DiagServer
    from d2diag.web.sources import MockDataSource

    srv = DiagServer(MockDataSource(), host="127.0.0.1", port=0, csv_dir=str(tmp_path))
    try:
        for _ in range(5):
            srv._connect_progress("opening the cable")
        srv._connect_progress("sending init (try 1/3)")   # ny text → ny rad
        lines = (tmp_path / "connection.log").read_text().strip().splitlines()
    finally:
        srv.server_close()
    assert len(lines) == 2


def test_init_lines_carry_the_last_known_engine_context(tmp_path):
    # K-line är delad: vi kan inte läsa motorn medan SLABS är aktiv. Utan den
    # senast kända kontexten går det inte att i efterhand se om ett tyst
    # initförsök gjordes i rörelse (SLABS vägrar comms >8–20 km/h) eller stilla.
    from d2diag.web.server import DiagServer
    from d2diag.web.sources import MockDataSource

    srv = DiagServer(MockDataSource(), host="127.0.0.1", port=0, csv_dir=str(tmp_path))
    try:
        srv._remember_engine({"signals": {
            "rpm": {"v": 761.0}, "battery": {"v": 13.93}, "speed": {"v": 0.0}}})
        srv._connect_progress("sending init (try 1/3)")
        srv._connect_progress("waiting for the bus to settle")   # ingen kontext här
        lines = (tmp_path / "connection.log").read_text().strip().splitlines()
    finally:
        srv.server_close()
    assert "motor: rpm 761, 0 km/h, 13.9 V" in lines[0]
    assert "motor:" not in lines[1]


def test_conf_of_reads_store():
    # Confidence-filtret (Verified/Experimental) läser storen. Efter att rpm_error
    # och balansfälten befordrats 2026-08-19 är maf_raw en kvarvarande TD5-kandidat.
    from d2diag.web.sources import _conf_map, _conf_of
    conf = _conf_map("td5")
    assert _conf_of("td5", "rpm_error", conf) == "belagt"
    assert _conf_of("td5", "balance_3", conf) == "belagt"
    assert _conf_of("td5", "maf_raw", conf) == "kandidat"
