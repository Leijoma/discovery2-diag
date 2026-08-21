"""Build a machine-readable protocol library from capture logs.

Combines **auto-extracted** KWP transactions (TD5/SLABS — checksum-validated
request→response) with **curated, verified** non-KWP facts (Autobox `72…`,
ACE bulk, Airbag fault format, BCU EKA). Result = JSON: module → protocol →
transactions/functions + annotations.
"""
from __future__ import annotations

from . import capture

# Verified non-KWP facts (from analysis of the logs, see protocol_state_handoff.md).
KNOWN: "dict" = {
    "td5_settings": {
        "note": "TD5 settings ID strings are ASCII-decodable (proven)",
        "21 0e": "Config Tune ID, every-other-byte-doubled → 'sutdp008' (RDL 016)",
        "21 32": "Config+Fuel Tune ID, straight ASCII → 'sutdp008' + 'suhde0244145' (RDL 016)",
        "21 3d": "feature/config-block, 20 bytes packed (docx: 21 flags) — requires differential",
    },
    "autobox": {
        "protocol": "proprietary-72",
        "framing": "72 <len> <data> <XOR-cs> (request; XOR verified). Response: 72 <len> 60 <data> <cs>",
        "note": "reference tool 'unable to perform the function' but the ECU RESPONDS with a data block",
        "confirmed": {
            "read_faults": "72 05 04 00 73 -> 72 09 60 01 00 00 00 00 1b (reproduced in 2 sessions)",
            "clear_faults": "72 04 05 73 -> 72 04 60 99 ff",
        },
        "functions": {
            "read_faults": "72 05 04 00 73",
            "clear_faults": "72 04 05 73",
            "read_settings": "72 05 93 00 e4",
            "inputs_pressure": "72 05 0b 00 7c",
            "inputs_general": "72 05 0b 03 7f",
            "reset_adaptive": "72 06 83 ff 07 08 ff",
        },
        "response_marker": "72 <len> 60 <data> <cs>",
        "caveats": [
            "72 04 60 99 ff = GENERIC ack (= the response to keepalive 72 04 1e 68), NOT fault-specific",
            "read-fault-payload 01 00 00 00 00: do NOT interpret as count/empty-list/DTC yet",
        ],
        "open": "content interpretation, meaning of 60, why the reference tool rejects the response (requires a successful session)",
    },
    "ace": {
        "protocol": "bulk; pair-wise framing (67 67 / e0 e0 / f0 f0 — NOT uniform → protocol, not artifact)",
        "fault_block": "67 67 11 e0 e0 f0 f0 00 00 00 1a 00 00 08 09 80 92 00 00",
        "fault_set_seen": ["004-02", "004-04", "004-05", "006-1"],
        "utilities": {"calib_acc1": "15 15 ff", "calib_acc2": "16 16 ff", "set_calibrated": "10 10 00"},
        "keepalive": ["04 04 00", "07 07 00"],
        "open": "inputs = one bulk block → differential captures for field mapping",
    },
    "airbag": {
        "protocol": "kwp-addressed",
        "address": "0x5B (addressed framing per message, NOT unaddressed session frames)",
        "framing_example": "82 5b f7 21 02 -> f7 5b 61 02 90 04 90 16 00 00 (faultread-20260809.log line 885)",
        "fault_read": "21 02",
        "clear": "14 -> 54",
        "record": "[status][number]; number = the reference tool's display number (90 04 = 004, 90 16 = 022)",
        "status_seen": {"0x90": "open circuit intermittent (candidate)"},
        "security": "SecurityAccess on 0x5B: seed 44 8E -> key 00 6E -> positive 67 02 (probably before clear). "
                    "CORR: this pair is AIRBAG, not 'insecure/BCU' (the only complete seed->key with a positive acknowledgement)",
        "decoded_in_code": "src/d2diag/airbag/faults.py",
        "open": "status byte's bit meanings; 21 01 vs 21 02; comms class requires addressed framing",
    },
    "bcu": {
        "protocol": "valeo",
        "eka_read": "21 cc",
        "eka_write": "3b cc <4 byte>",
        "eka_rdl016": "XXXX (3b cc XX XX XX XX)",
        "settings_ids": ["c7", "ca", "cb", "d3", "eb", "c6", "ce", "d4", "d5", "d6", "d7"],
        "connect": "ignition cycling: off→key→on→key",
        "security": {
            "note": "SecurityAccess required before output-writes (HIGH). 27 01->67 01 <seed>; 27 02 <key>->pos/neg",
            "captured_attempt": "seed EB CD -> key C0 10 -> DENIED 7f 27 83; after restart key 4A 8A -> writes started",
            "caveat": "no clean 67 02 for a successful attempt -> 'succeeded' is the inferred conclusion; do NOT mark 4A 8A as universally valid",
            "extra_pairs": "4B 5C (-2.log, seed corrupt=unusable). NOTE: seed 44 8E->key 00 6E +67 02 on addr 0x5B is AIRBAG (see KNOWN['airbag']), NOT BCU",
        },
        "outputs": {
            "service": "3B WriteLocalId; four 4-byte banks (PROVEN structure, cs validated)",
            "banks": ["06 3b 22 00000000 63", "06 3b 23 00000000 64",
                      "06 3b c1 00000000 02", "06 3b c2 00000000 03"],
            "hypothesis": "22/23/c1/c2 = 32-bit output/control bitfields (STRONG hypothesis)",
            "warning": "ALL captured payloads = 00000000 (probably reset/disable-all). NEVER link output->bank/bit via annotation. The ON frame is missing.",
        },
        "open": "elicit non-zero bank state; map output bits; seed->key algorithm; which session bank-writes require",
    },
}


def build_library(paths: "list[str]") -> "dict":
    lib = {"generated_from": list(paths), "modules": {}}
    mods = lib["modules"]

    # 1) auto: KWP transactions (TD5/SLABS) — dedupe on request
    for path in paths:
        events = capture.parse_log(path)
        for tx in capture.kwp_transactions(events):
            name = tx["module"] or "unknown"
            mod = mods.setdefault(name, {"protocol": "kwp2000-lengthprefix", "transactions": {}, "lids": []})
            if "transactions" not in mod:
                mod["transactions"] = {}
            t = mod["transactions"].setdefault(tx["req"], {
                "req": tx["req"], "service": tx["service"],
                "lid": f"{tx['lid']:02x}" if tx["lid"] is not None else None,
                "example_resp": None, "count": 0, "annotations": set(),
            })
            t["count"] += 1
            if tx["resp"] and not t["example_resp"]:
                t["example_resp"] = tx["resp"]
            if tx["annotation"]:
                t["annotations"].add(tx["annotation"])

    # 2) finalise KWP: dict→sorted list, set→list, collect LIDs
    for name, mod in mods.items():
        txs = mod.pop("transactions", {})
        rows = []
        lids = set()
        for t in txs.values():
            t["annotations"] = sorted(t["annotations"])[:4]
            if t["lid"]:
                lids.add(t["lid"])
            rows.append(t)
        rows.sort(key=lambda r: (r["service"] or "", r["req"]))
        mod["transactions"] = rows
        mod["lids"] = sorted(lids)

    # 3) curated non-KWP facts
    for name, facts in KNOWN.items():
        mods.setdefault(name, {}).update(facts)

    return lib
