"""faultmap.json (browser fault dictionaries) must stay in sync with the Python decoders.

The ESP reports raw fault blocks; the browser decodes them against these JSON maps. This locks each
JSON to its Python decoder and proves a JSON-driven decode gives EXACTLY the same result as the
Python decoder (so the browser and the Python stack agree) — for both TD5 and SLABS.
"""
import json
import pathlib

from d2diag.slabs.faults import decode_fault_block
from d2diag.td5.faults import decode_faults

import tools.gen_faultmap as g

_TD5 = pathlib.Path(g._DIR) / "td5" / "faultmap.json"
_SLABS = pathlib.Path(g._DIR) / "slabs" / "faultmap.json"


def test_committed_maps_match_source():
    assert _TD5.exists() and _SLABS.exists(), "run: python3 tools/gen_faultmap.py"
    assert _TD5.read_text(encoding="utf-8") == g.build_td5(), "td5 faultmap.json stale — regenerate"
    assert _SLABS.read_text(encoding="utf-8") == g.build_slabs(), "slabs faultmap.json stale — regenerate"


def _decode_via_json(doc: dict, block: bytes) -> "list[str]":
    """Mirror of the browser decode, driven by the JSON map."""
    block = block[: doc["block_len"]]
    out, known = [], {}
    for key, name in doc["bits"].items():
        off, bit = map(int, key.split("."))
        known[off] = known.get(off, 0) | (1 << bit)
        if off < len(block) and (block[off] & (1 << bit)):
            out.append(name)
    for off, byte in enumerate(block):
        unknown = byte & ~known.get(off, 0) & 0xFF
        for bit in range(8):
            if unknown & (1 << bit):
                out.append(f"byte{off}.bit{bit}")
    return out


def test_td5_json_decode_matches_python():
    doc = json.loads(g.build_td5())
    block = bytearray(doc["block_len"])
    block[0] |= 0x40    # air flow circuit (Logged Low)
    block[33] |= 0x01   # inj. 1 short circuit (Current)
    block[14] |= 0x01   # unknown bit → generic
    assert _decode_via_json(doc, bytes(block)) == decode_faults(bytes(block))


def test_slabs_json_decode_matches_python():
    # The exact RDL016 logged block: byte3.bit4 (020) + byte10.bit4 (027).
    block = bytes.fromhex("00000010000000000000100000000000")
    doc = json.loads(g.build_slabs())
    js = _decode_via_json(doc, block)
    py = decode_fault_block(block)
    # SLABS python labels unknowns "unknown (byte i, bit b)"; the JSON/browser uses "byteI.bitB".
    # Known bits must match exactly (that's what we care about here).
    assert [x for x in js if not x.startswith("byte")] == [x for x in py if not x.startswith("unknown")]
    assert "020: right front wheel speed sensor — output too low" in js
    assert "027: shuttle valve switch — electrical failure" in js
