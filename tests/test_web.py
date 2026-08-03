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
    assert set(d["signals"]["rpm"]) == {"v", "u"}
    assert d["signals"]["battery"]["u"] == "V"
    assert isinstance(d["faults"], list) and d["faults"]


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
