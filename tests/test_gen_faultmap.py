"""faultmap.json (browser fault dictionary) must stay in sync with the Python decoder.

The ESP reports raw 21 3B bits; the browser decodes them against faultmap.json. This locks that
JSON to d2diag.td5.faults so the two never drift, and proves a JSON-based decode gives EXACTLY the
same result as decode_faults (so the browser and the Python stack agree).
"""
import json
import pathlib

from d2diag.td5.faults import decode_faults

import tools.gen_faultmap as g


def test_committed_faultmap_matches_source():
    p = pathlib.Path(g._JSON_PATH)
    assert p.exists(), "src/d2diag/td5/faultmap.json missing — run: python3 tools/gen_faultmap.py"
    assert p.read_text(encoding="utf-8") == g.build(), (
        "faultmap.json is stale vs d2diag.td5.faults — run: python3 tools/gen_faultmap.py"
    )


def _decode_via_json(doc: dict, block: bytes) -> "list[str]":
    """Mirror of the browser decode: same logic decode_faults uses, driven by the JSON map."""
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


def test_json_decode_matches_python_decode():
    doc = json.loads(g.build())
    block = bytearray(doc["block_len"])
    block[0] |= 0x40    # air flow circuit (Logged Low)
    block[33] |= 0x01   # inj. 1 short circuit (Current)
    block[14] |= 0x01   # an UNKNOWN bit (14.0 not in the map) → generic byte14.bit0
    assert _decode_via_json(doc, bytes(block)) == decode_faults(bytes(block))
