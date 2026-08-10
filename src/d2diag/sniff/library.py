"""Bygg ett maskinläsbart protokollbibliotek ur capture-loggar.

Kombinerar **auto-extraherade** KWP-transaktioner (TD5/SLABS — checksum-validerade
request→response) med **curerade, verifierade** icke-KWP-fakta (Autobox `72…`,
ACE bulk, Airbag-felformat, BCU EKA). Resultat = JSON: modul → protokoll →
transaktioner/funktioner + annoteringar.
"""
from __future__ import annotations

from . import capture

# Verifierade icke-KWP-fakta (ur analys av loggarna, se protocol_state_handoff.md).
KNOWN: "dict" = {
    "autobox": {
        "protocol": "proprietary-72",
        "note": "Nanacom 'unable to perform the function' men ECU:n SVARAR med datablock",
        "functions": {
            "read_faults": "72 05 04 00 73",
            "clear_faults": "72 04 05 73",
            "read_settings": "72 05 93 00 e4",
            "inputs_pressure": "72 05 0b 00 7c",
            "inputs_general": "72 05 0b 03 7f",
            "reset_adaptive": "72 06 83 ff 07 08 ff",
        },
        "response_marker": "72 <len> 60 <data> <cs>",
        "open": "ramformat/checksum + innehållstolkning (kräver lyckad session)",
    },
    "ace": {
        "protocol": "bulk; par-vis framing (67 67 / e0 e0 / f0 f0 — EJ uniform → protokoll, ej artefakt)",
        "fault_block": "67 67 11 e0 e0 f0 f0 00 00 00 1a 00 00 08 09 80 92 00 00",
        "fault_set_seen": ["004-02", "004-04", "004-05", "006-1"],
        "utilities": {"calib_acc1": "15 15 ff", "calib_acc2": "16 16 ff", "set_calibrated": "10 10 00"},
        "keepalive": ["04 04 00", "07 07 00"],
        "open": "inputs = ett bulk-block → differential-captures för fält-mappning",
    },
    "airbag": {
        "protocol": "kwp-variant",
        "fault_read": "21 02",
        "clear": "14 -> 54",
        "record": "[status][number]; number = Nanacoms display-nr (90 04 = 004, 90 16 = 022)",
        "status_seen": {"0x90": "open circuit intermittent (kandidat)"},
        "decoded_in_code": "src/d2diag/airbag/faults.py",
        "open": "statusbytens bit-betydelser; 21 01 vs 21 02",
    },
    "bcu": {
        "protocol": "valeo",
        "eka_read": "21 cc",
        "eka_write": "3b cc <4 byte>",
        "eka_rdl016": "XXXX (3b cc XX XX XX XX)",
        "settings_ids": ["c7", "ca", "cb", "d3", "eb", "c6", "ce", "d4", "d5", "d6", "d7"],
        "connect": "tänd-cykling: off→key→on→key",
    },
}


def build_library(paths: "list[str]") -> "dict":
    lib = {"generated_from": list(paths), "modules": {}}
    mods = lib["modules"]

    # 1) auto: KWP-transaktioner (TD5/SLABS) — deduppa på request
    for path in paths:
        events = capture.parse_log(path)
        for tx in capture.kwp_transactions(events):
            name = tx["module"] or "okänd"
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

    # 2) finalisera KWP: dict→sorterad lista, set→lista, samla LID:er
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

    # 3) curerade icke-KWP-fakta
    for name, facts in KNOWN.items():
        mods.setdefault(name, {}).update(facts)

    return lib
