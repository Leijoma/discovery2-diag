"""Generate faultmap.json (browser-readable) from d2diag.td5.faults — the single source of truth.

The ESP node reports the raw 21 3B fault block; the /live page (or any browser) fetches THIS JSON
from GitHub and decodes the bits to text. So the fault dictionary lives in the repo, not on the ESP
— the node stays a dumb reporter. Keeps in sync with the Python decoder (guarded by a test).

    python3 tools/gen_faultmap.py           # write the JSON
    python3 tools/gen_faultmap.py --check   # exit 1 if the committed file is stale (CI/test)
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from d2diag.td5.faults import FAULT_BLOCK_LEN, FAULTS  # noqa: E402

_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                          "src", "d2diag", "td5", "faultmap.json")


def build() -> str:
    """Return the JSON text: {block_len, bits:{"offset.bit": name}} keyed like decode_faults."""
    bits = {}
    for f in FAULTS:
        bit = f.mask.bit_length() - 1          # each mask is a single bit (0x01..0x80)
        bits[f"{f.offset}.{bit}"] = f.name
    doc = {"module": "td5", "block_len": FAULT_BLOCK_LEN, "bits": bits}
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    out = build()
    if "--check" in sys.argv:
        cur = ""
        if os.path.exists(_JSON_PATH):
            with open(_JSON_PATH, encoding="utf-8") as fh:
                cur = fh.read()
        if cur != out:
            print("faultmap.json is stale — run: python3 tools/gen_faultmap.py", file=sys.stderr)
            return 1
        return 0
    with open(_JSON_PATH, "w", encoding="utf-8") as fh:
        fh.write(out)
    print(f"wrote {_JSON_PATH} ({len(FAULTS)} named bits)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
