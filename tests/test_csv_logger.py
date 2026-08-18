"""CSV live-data logger (web/logger.py::CsvLogger) + server start/stop commands."""
import csv

from d2diag.web.logger import CsvLogger


def _snap(signals, status="connected", faults=None):
    return {"status": status, "signals": signals, "faults": faults or []}


def test_header_from_first_snapshot_with_units(tmp_path):
    p = tmp_path / "live.csv"
    log = CsvLogger(str(p))
    log.log(_snap({"coolant_temp": {"v": 59.2, "u": "°C"},
                   "battery": {"v": 14.1, "u": "V"},
                   "maf_raw": {"v": 33, "u": ""}}))
    rows = list(csv.reader(p.open(encoding="utf-8")))
    # header: timestamp,status,faults, then signals sorted, unit in name (blank unit → bare name)
    assert rows[0] == ["timestamp", "status", "faults", "battery (V)", "coolant_temp (°C)", "maf_raw"]
    assert rows[1][1] == "connected" and rows[1][2] == ""
    assert rows[1][3] == "14.1" and rows[1][4] == "59.2"
    assert log.rows == 1


def test_faults_column_records_when_a_fault_appears(tmp_path):
    p = tmp_path / "live.csv"
    log = CsvLogger(str(p))
    log.log(_snap({"speed": {"v": 0, "u": "km/h"}}))                       # no faults
    log.log(_snap({"speed": {"v": 0, "u": "km/h"}},
                  faults=["020: RF wheel sensor (Logged)", "027: shuttle valve (Logged)"]))
    rows = list(csv.reader(p.open(encoding="utf-8")))
    assert rows[1][2] == ""                                                 # fault-free row
    assert rows[2][2] == "020: RF wheel sensor (Logged); 027: shuttle valve (Logged)"  # appears here


def test_columns_fixed_after_first_row(tmp_path):
    p = tmp_path / "live.csv"
    log = CsvLogger(str(p))
    log.log(_snap({"a": {"v": 1, "u": ""}, "b": {"v": 2, "u": ""}}))
    log.log(_snap({"a": {"v": 3, "u": ""}, "c": {"v": 9, "u": ""}}))  # b missing, c is new
    rows = list(csv.reader(p.open(encoding="utf-8")))
    assert rows[0] == ["timestamp", "status", "faults", "a", "b"]   # columns locked to first row
    assert rows[2][3] == "3" and rows[2][4] == ""                   # a kept, b blank, c ignored
    assert log.rows == 2


def test_waits_for_signals_before_writing_header(tmp_path):
    p = tmp_path / "live.csv"
    log = CsvLogger(str(p))
    log.log(_snap({}, status="connecting"))   # no signals yet → nothing written
    assert not p.exists() and log.rows == 0
    log.log(_snap({"rpm": {"v": 800, "u": "rpm"}}))
    assert p.exists() and log.rows == 1


def test_server_start_stop_csv_commands(tmp_path):
    from d2diag.web import MockDataSource
    from d2diag.web.server import DiagServer

    srv = DiagServer(MockDataSource(), host="127.0.0.1", port=0, csv_dir=str(tmp_path))
    try:
        assert srv._csv is None
        r = srv.start_csv()
        assert r["ok"] and srv._csv is not None and r["file"].startswith("livedata-")
        # a poll-style log writes a row
        srv._csv.log(_snap({"coolant_temp": {"v": 60.0, "u": "°C"}}))
        stopped = srv.stop_csv()
        assert stopped["ok"] and stopped["rows"] == 1 and srv._csv is None
        assert (tmp_path / r["file"]).exists()
        # stopping again is harmless
        assert srv.stop_csv()["rows"] == 0
    finally:
        srv.server_close()


def test_csv_commands_do_not_queue_behind_the_poller(tmp_path):
    # CSV-start/stopp rör inte K-line och ska svara direkt. Köades de i pollertråden
    # fick de vänta ut en pågående etablering (SLABS ≈ 20 s) och timeoutade på 8 s
    # i UI:t — trots att de sedan lyckades. Här körs INGEN pollertråd: hade
    # kommandot köats hade det timeoutat, nu svarar det inline.
    import time as _time

    from d2diag.web import MockDataSource
    from d2diag.web.server import DiagServer

    srv = DiagServer(MockDataSource(), host="127.0.0.1", port=0, csv_dir=str(tmp_path))
    try:
        t0 = _time.monotonic()
        r = srv.enqueue_command({"action": "start_csv"})
        elapsed = _time.monotonic() - t0
        assert r["ok"] and srv._csv is not None
        assert elapsed < 1.0                      # inte 8 s timeout
        assert srv._commands.empty()              # gick aldrig via kön
        assert srv.enqueue_command({"action": "stop_csv"})["ok"] and srv._csv is None
    finally:
        srv.server_close()
