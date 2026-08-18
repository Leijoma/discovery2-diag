"""Community contribution endpoint — validation, storage, stats (server/endpoint.py)."""
import pytest

from server.endpoint import (
    Store,
    render_admin,
    validate_contribution,
    validate_register,
)


# ---- validation: PII is rejected, only whitelisted fields survive ---------- #
def test_register_rejects_pii():
    with pytest.raises(ValueError):
        validate_register({"install_id": "abcd1234-uuid", "vin": "SALLXXXXXXXXXXXXX"})
    with pytest.raises(ValueError):
        validate_register({"install_id": "abcd1234-uuid", "vehicle": {"registration": "RDL016"}})


def test_register_requires_valid_install_id():
    with pytest.raises(ValueError):
        validate_register({"install_id": "short"})           # too short
    with pytest.raises(ValueError):
        validate_register({})                                # missing


def test_register_clean_vehicle_ok():
    rec = validate_register({
        "install_id": "11111111-2222-3333",
        "tool_version": "0.1.0",
        "vehicle": {"model": "Discovery 2", "year": "2002", "engine": "Td5", "market": "EU"},
    })
    assert rec["install_id"] == "11111111-2222-3333"
    assert rec["vehicle"] == {"model": "Discovery 2", "year": "2002",
                              "engine": "Td5", "market": "EU"}


def test_contribution_whitelists_fields():
    rec = validate_contribution({
        "install_id": "aaaaaaaa-bbbb",
        "tool_version": "0.1.0",
        "module": "slabs",
        "lid": "44",
        "offset": 12,
        "kind": "u8",
        "raw": "00 80 01 02",
        "our_name": "battery",
        "our_value": 11.3,
        "our_confidence": "kandidat",
        "answer": {"type": "correct", "value": 12.1, "unit": "V"},
        "secret_owner_name": "should be ignored",   # not a PII key, just dropped
    })
    assert rec["module"] == "slabs" and rec["lid"] == "44" and rec["offset"] == 12
    assert rec["answer_type"] == "correct" and rec["answer_value"] == "12.1"
    assert "secret_owner_name" not in rec           # only whitelisted keys stored


def test_contribution_requires_module():
    with pytest.raises(ValueError):
        validate_contribution({"install_id": "aaaaaaaa-bbbb"})


# ---- storage + stats ------------------------------------------------------- #
def test_store_counts_installs_and_contributions(tmp_path):
    st = Store(str(tmp_path / "db.sqlite"))
    st.register(validate_register({"install_id": "inst-one-xxxx", "tool_version": "0.1"}))
    st.register(validate_register({"install_id": "inst-two-xxxx", "tool_version": "0.1"}))
    # only install one contributes (twice)
    for val in (11.3, 12.1):
        st.add_contribution(validate_contribution({
            "install_id": "inst-one-xxxx", "module": "slabs", "lid": "44",
            "our_confidence": "kandidat",
            "answer": {"type": "correct", "value": val, "unit": "V"}}))

    s = st.stats()
    assert s["installs"] == 2           # both opted in / registered
    assert s["contributing"] == 1       # only one actually sent readings
    assert s["total"] == 2
    assert {"module": "slabs", "n": 2} in s["by_module"]
    assert st.recent()[0]["module"] == "slabs"


def test_contribution_registers_install_if_new(tmp_path):
    st = Store(str(tmp_path / "db.sqlite"))
    st.add_contribution(validate_contribution({
        "install_id": "fresh-install-9", "module": "td5",
        "answer": {"type": "confirm"}}))
    assert st.stats()["installs"] == 1   # contributing without prior register still counts


def test_admin_renders_without_crash(tmp_path):
    st = Store(str(tmp_path / "db.sqlite"))
    st.add_contribution(validate_contribution({
        "install_id": "some-install-1", "module": "td5", "lid": "1a",
        "answer": {"type": "confirm"}}))
    html = render_admin(st.stats(), st.recent())
    assert "community contributions" in html and "td5" in html
    # anonymous install shown truncated, never the full id in a table cell
    assert "some-install-1" not in html
