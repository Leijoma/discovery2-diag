"""Generate faultmap.json (browser-readable) from the Python fault decoders — the source of truth.

The ESP node reports the RAW fault block(s); the /live page (or any browser) fetches these JSON
maps from GitHub and decodes the bits to text. So the fault dictionaries live in the repo, not on
the ESP — the node stays a dumb reporter. Kept in sync with the Python decoders (guarded by a test).

    python3 tools/gen_faultmap.py           # write td5 + slabs maps
    python3 tools/gen_faultmap.py --check   # exit 1 if any committed file is stale (CI/test)
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from d2diag.slabs.faults import FAULT_BLOCK_LEN as SLABS_LEN, SLABS_FAULT_BITS  # noqa: E402
from d2diag.td5.faults import FAULT_BLOCK_LEN as TD5_LEN, FAULTS  # noqa: E402

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "d2diag")


def build_td5() -> str:
    """{block_len, bits:{"offset.bit": name}} keyed exactly like td5.decode_faults."""
    bits = {f"{f.offset}.{f.mask.bit_length() - 1}": f.name for f in FAULTS}  # mask is a single bit
    return json.dumps({"module": "td5", "block_len": TD5_LEN, "bits": bits}, ensure_ascii=False, indent=2) + "\n"


def build_slabs() -> str:
    """{block_len, bits:{"offset.bit": "nr: text"}} keyed like slabs.decode_fault_block."""
    bits = {f"{off}.{bit}": f"{nr}: {text}" for (off, bit), (nr, text) in SLABS_FAULT_BITS.items()}
    return json.dumps({"module": "slabs", "block_len": SLABS_LEN, "bits": bits}, ensure_ascii=False, indent=2) + "\n"


_MAPS = {
    os.path.join(_DIR, "td5", "faultmap.json"): build_td5,
    os.path.join(_DIR, "slabs", "faultmap.json"): build_slabs,
}


def main() -> int:
    check = "--check" in sys.argv
    stale = False
    for path, build in _MAPS.items():
        out = build()
        if check:
            cur = ""
            if os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    cur = fh.read()
            if cur != out:
                print(f"{os.path.relpath(path)} is stale — run: python3 tools/gen_faultmap.py", file=sys.stderr)
                stale = True
        else:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(out)
            print(f"wrote {os.path.relpath(path)}")
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
