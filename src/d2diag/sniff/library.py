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
    "td5_settings": {
        "note": "TD5 settings ID-strängar är ASCII-avkodbara (belagt)",
        "21 0e": "Config Tune ID, varannan-byte-dubblerad → 'sutdp008' (RDL 016)",
        "21 32": "Config+Fuel Tune ID, rak ASCII → 'sutdp008' + 'suhde0244145' (RDL 016)",
        "21 3d": "feature/config-block, 20 byte packat (docx: 21 flaggor) — kräver differential",
    },
    "autobox": {
        "protocol": "proprietary-72",
        "framing": "72 <len> <data> <XOR-cs> (request; XOR verifierat). Svar: 72 <len> 60 <data> <cs>",
        "note": "reference tool 'unable to perform the function' men ECU:n SVARAR med datablock",
        "confirmed": {
            "read_faults": "72 05 04 00 73 -> 72 09 60 01 00 00 00 00 1b (reproducerat i 2 sessioner)",
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
            "72 04 60 99 ff = GENERISKT ack (= svaret pa keepalive 72 04 1e 68), EJ fault-specifikt",
            "read-fault-payload 01 00 00 00 00: tolka INTE som count/tom-lista/DTC annu",
        ],
        "open": "innehallstolkning, 60-betydelsen, varfor reference tool forkastar svaret (kraver lyckad session)",
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
        "protocol": "kwp-adresserad",
        "address": "0x5B (adresserad framing per meddelande, EJ oadresserade sessionsramar)",
        "framing_example": "82 5b f7 21 02 -> f7 5b 61 02 90 04 90 16 00 00 (faultread-20260809.log rad 885)",
        "fault_read": "21 02",
        "clear": "14 -> 54",
        "record": "[status][number]; number = reference tools display-nr (90 04 = 004, 90 16 = 022)",
        "status_seen": {"0x90": "open circuit intermittent (kandidat)"},
        "security": "SecurityAccess pa 0x5B: seed 44 8E -> key 00 6E -> positivt 67 02 (troligen fore clear). "
                    "KORR: detta par ar AIRBAG, ej 'osaker/BCU' (enda kompletta seed->key med positiv kvittens)",
        "decoded_in_code": "src/d2diag/airbag/faults.py",
        "open": "statusbytens bit-betydelser; 21 01 vs 21 02; comms-klass kraver adresserad framing",
    },
    "bcu": {
        "protocol": "valeo",
        "eka_read": "21 cc",
        "eka_write": "3b cc <4 byte>",
        "eka_rdl016": "XXXX (3b cc XX XX XX XX)",
        "settings_ids": ["c7", "ca", "cb", "d3", "eb", "c6", "ce", "d4", "d5", "d6", "d7"],
        "connect": "tänd-cykling: off→key→on→key",
        "security": {
            "note": "SecurityAccess kravs fore output-writes (HOG). 27 01->67 01 <seed>; 27 02 <key>->pos/neg",
            "captured_attempt": "seed EB CD -> key C0 10 -> NEKAD 7f 27 83; efter restart key 4A 8A -> writes borjade",
            "caveat": "inget rent 67 02 for lyckat forsok -> 'lyckades' ar slutsatsdraget; markera EJ 4A 8A som allmangiltig",
            "extra_pairs": "4B 5C (-2.log, seed korrupt=oanvandbart). OBS: seed 44 8E->key 00 6E +67 02 pa addr 0x5B ar AIRBAG (se KNOWN['airbag']), EJ BCU",
        },
        "outputs": {
            "service": "3B WriteLocalId; fyra 4-byte-banker (BELAGT struktur, cs validerade)",
            "banks": ["06 3b 22 00000000 63", "06 3b 23 00000000 64",
                      "06 3b c1 00000000 02", "06 3b c2 00000000 03"],
            "hypothesis": "22/23/c1/c2 = 32-bit output/control-bitfalt (STARK hypotes)",
            "warning": "ALLA fangade payloads = 00000000 (troligen reset/disable-all). Koppla ALDRIG output->bank/bit via annotation. PA-framen saknas.",
        },
        "open": "framkalla non-zero bank-state; mappa output-bitar; seed->key-algoritm; vilken session bank-writes kraver",
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
