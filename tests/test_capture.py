"""Tester för capture-parsningen (protokollbibliotekets grund)."""
from d2diag.sniff import capture
from d2diag.sniff.library import build_library


def test_split_frames_validates_checksum():
    # 02 21 09 2c = giltig (02+21+09=2c); följt av svaret 04 61 09 02 fa 6a
    b = [int(x, 16) for x in "02 21 09 2c 04 61 09 02 fa 6a".split()]
    frames, consumed = capture.split_frames(b)
    assert consumed == len(b) and len(frames) == 2
    assert capture.classify_frame(frames[0])["dir"] == "req"
    assert capture.classify_frame(frames[1])["dir"] == "resp"


def test_split_frames_rejects_bad_checksum():
    frames, consumed = capture.split_frames([0x02, 0x21, 0x09, 0xff])  # fel cs
    assert frames == [] and consumed == 0


def test_classify_service_and_lid():
    frame = [int(x, 16) for x in "04 61 09 02 fa 6a".split()]
    c = capture.classify_frame(frame)
    assert c["service"] == "ReadLocalId" and c["lid"] == 0x09 and c["cs_ok"]


def test_kwp_transactions_pairs_req_resp(tmp_path):
    log = tmp_path / "c.log"
    log.write_text(
        "=== SESSION ===\n"
        "[1] 81 13 f7 81 0c\n"                       # TD5 fast init → modul=td5
        ">>> read fuelling\n"
        "[2] 02 21 09 2c 04 61 09 02 fa 6a\n",       # 21 09 → 61 09 02 fa
        encoding="utf-8",
    )
    events = capture.parse_log(str(log))
    txs = capture.kwp_transactions(events)
    tx = next(t for t in txs if t["lid"] == 0x09)
    assert tx["module"] == "td5" and tx["req"] == "21 09"
    assert tx["resp"] == "61 09 02 fa" and tx["annotation"] == "read fuelling"


def test_build_library_merges_auto_and_known(tmp_path):
    log = tmp_path / "c.log"
    log.write_text("[1] 81 13 f7 81 0c\n[2] 02 21 09 2c 04 61 09 02 fa 6a\n", encoding="utf-8")
    lib = build_library([str(log)])
    assert "td5" in lib["modules"] and lib["modules"]["td5"]["transactions"]
    # curerade icke-KWP-fakta finns med
    assert lib["modules"]["bcu"]["eka_read"] == "21 cc"
    assert lib["modules"]["autobox"]["functions"]["read_faults"] == "72 05 04 00 73"
