"""Bygg protokollbiblioteket (JSON) ur capture-loggarna.

    python3 tools/build_protocol_library.py                       # alla logs/*.log
    python3 tools/build_protocol_library.py logs/session.log ...  # specifika

Skriver `references/protocol_library.json`: modul → protokoll → transaktioner
(auto, checksum-validerade) + curerade icke-KWP-funktioner.
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from d2diag.sniff.library import build_library  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Build protocol library (JSON)")
    ap.add_argument("logs", nargs="*", help="log files (default: logs/*.log)")
    ap.add_argument("--out", default="references/protocol_library.json")
    args = ap.parse_args()

    logs = args.logs or sorted(glob.glob("logs/*.log"))
    if not logs:
        print("no log files found", file=sys.stderr)
        return 1
    lib = build_library(logs)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(lib, fh, indent=2, ensure_ascii=False)
    n_tx = sum(len(m.get("transactions", [])) for m in lib["modules"].values())
    print(f"{args.out}: {len(lib['modules'])} moduler, {n_tx} KWP-transaktioner "
          f"ur {len(logs)} loggar")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
