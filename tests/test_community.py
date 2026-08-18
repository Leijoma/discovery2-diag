"""Community contribution client — consent gating, anonymous ID, PII-free payload."""
import json

from d2diag.community import Community


class _FakePoster:
    """Records POSTs instead of hitting the network; returns {ok:True}."""
    def __init__(self):
        self.calls = []

    def __call__(self, url, payload, timeout=8.0):
        self.calls.append((url, payload))
        return {"ok": True}


def _community(tmp_path, poster=None):
    poster = poster or _FakePoster()
    c = Community(config_path=str(tmp_path / "community.json"),
                  endpoint="https://example.test/d2diag", poster=poster)
    return c, poster


def test_install_id_is_stable_and_persisted(tmp_path):
    c, _ = _community(tmp_path)
    iid = c.install_id()
    assert len(iid) >= 8 and c.install_id() == iid            # stable within instance
    c2, _ = _community(tmp_path)                              # reload from disk
    assert c2.install_id() == iid


def test_consent_unset_by_default_and_contribute_is_noop(tmp_path):
    c, poster = _community(tmp_path)
    assert c.consent is None and c.state()["consent"] is None
    res = c.contribute({"module": "td5", "lid": "1a"})
    assert res["ok"] is False and "not enabled" in res["error"]
    assert poster.calls == []                                # nothing left the machine


def test_opt_in_registers_the_install(tmp_path):
    c, poster = _community(tmp_path)
    res = c.set_consent(True, vehicle={"model": "Discovery 2", "year": "2002", "engine": "Td5"})
    assert res["ok"] and res["consent"] is True and res["registered"] is True
    assert poster.calls[0][0].endswith("/register")
    reg = poster.calls[0][1]
    assert reg["install_id"] == c.install_id() and reg["vehicle"]["engine"] == "Td5"
    assert c.state()["registered"] is True


def test_opt_out_does_not_register(tmp_path):
    c, poster = _community(tmp_path)
    assert c.set_consent(False) == {"ok": True, "consent": False}
    assert poster.calls == []


def test_contribution_payload_is_whitelisted_pii_free(tmp_path):
    c, poster = _community(tmp_path)
    c.set_consent(True, vehicle={"model": "D2", "plate": "RDL016"})   # plate must be dropped
    c.contribute({
        "module": "slabs", "lid": "44", "offset": 12, "kind": "u8", "raw": "00 80",
        "name": "battery", "our_value": 11.3, "confidence": "kandidat",
        "answer": {"type": "correct", "value": 12.1, "unit": "V"},
        "vin": "SALLXXXXXXXXXXXXX",           # must NOT be forwarded
    })
    url, payload = poster.calls[-1]
    assert url.endswith("/contribute")
    assert payload["module"] == "slabs" and payload["our_name"] == "battery"
    assert payload["answer"]["value"] == 12.1
    assert "vin" not in payload and "vin" not in json.dumps(payload)   # no PII forwarded
    assert payload["vehicle"] == {"model": "D2"}                       # plate stripped


def test_consent_persists_across_reloads(tmp_path):
    c, _ = _community(tmp_path)
    c.set_consent(True, vehicle={"model": "D2"})
    c2, poster2 = _community(tmp_path)
    assert c2.consent is True and c2.state()["registered"] is True
    # already opted in → contribute works on the reloaded instance
    c2.contribute({"module": "td5"})
    assert poster2.calls[-1][0].endswith("/contribute")


class _Toggle:
    """Poster that is offline until ``online`` is set — for testing the outbox."""
    def __init__(self):
        self.online = False
        self.calls = []

    def __call__(self, url, payload, timeout=8.0):
        self.calls.append((url, payload))
        return {"ok": True} if self.online else {"ok": False, "error": "offline"}


def test_offline_outbox_queues_then_flushes(tmp_path):
    p = _Toggle()
    c = Community(config_path=str(tmp_path / "c.json"), endpoint="https://x.test/d2diag", poster=p)
    c.set_consent(True, {"model": "D2"})                 # opt in while offline
    assert c.consent is True and c.state()["registered"] is False

    r1 = c.contribute({"module": "td5", "name": "a"})
    r2 = c.contribute({"module": "td5", "name": "b"})
    assert r1["ok"] is False and r1["queued"] is True    # queued, never lost
    assert c.state()["pending"] == 2

    p.online = True                                      # back online
    r3 = c.contribute({"module": "slabs", "name": "c"})
    assert r3["ok"] is True and r3["flushed"] == 2       # current sent + 2 queued drained
    assert c.state()["pending"] == 0 and c.state()["registered"] is True

    # queue survives a reload while offline
    p.online = False
    c.contribute({"module": "td5", "name": "d"})
    c2 = Community(config_path=str(tmp_path / "c.json"), endpoint="https://x.test/d2diag", poster=p)
    assert c2.state()["pending"] == 1


def test_offline_is_graceful(tmp_path):
    # REAL _post against an unreachable endpoint → never raises; the app keeps working
    # and consent is saved locally regardless of the network.
    cfg = str(tmp_path / "c.json")
    c = Community(config_path=cfg, endpoint="http://127.0.0.1:59999/x")
    r = c.set_consent(True, {"model": "Discovery 2"})
    assert r["ok"] is True and r["consent"] is True and r["registered"] is False
    assert c.consent is True                       # consent saved despite being offline
    assert c.contribute({"module": "td5"})["ok"] is False   # graceful, no exception
    # reload from disk → choice persisted, no network involved
    c2 = Community(config_path=cfg, endpoint="http://127.0.0.1:59999/x")
    assert c2.consent is True and len(c2.state()["install"]) == 8
