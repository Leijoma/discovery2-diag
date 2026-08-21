"""Airbag (TRW SPS 2A) fault decoding — PROVEN from sniff 2026-08-10 (RDL 016).

The fault memory is read via ``21 02`` (the response starts ``61 02``). The data field is records of
**2 bytes: [status][fault-number]**, where fault-number is **the reference tool's display number
directly** (`0x04`=004, `0x16`=022). Empty records = `00 00`. Clear = `14` → `54`.

Proven example (RDL 016): ``61 02 90 04 90 16 00 00 …`` →
``90 04`` = fault 004 (open circuit intermittent), ``90 16`` = fault 022 (ditto).

The fault number is looked up against the position list in the fault code dictionary (Airbag, position =
display code, 1–65). The status encoding is preliminary — `0x90` observed for both
"open circuit intermittent"; other status values need more captures.
"""
from __future__ import annotations

FAULT_LID = 0x02          # 21 02 → the fault memory (held the active/intermittent faults)
FAULT_LID_ALT = 0x01      # 21 01 → empty in the capture (another fault class?)
_CLEAR = 0x14             # 14 → 54

# Preliminary status interpretation (needs more captures to confirm bit meanings).
STATUS = {0x90: "open circuit intermittent (candidate)"}


def decode_faults(data: bytes) -> "list[dict]":
    """Decode the data field (after ``61 02``) → list of ``{number, status, status_text}``.

    Number = the reference tool's display fault number (e.g. 4 → 004). Look up the text in the
    dictionary (Airbag position=display code)."""
    out: "list[dict]" = []
    for i in range(0, len(data) - 1, 2):
        status, num = data[i], data[i + 1]
        if status == 0 and num == 0:
            continue  # empty/padding record
        out.append({
            "number": num,
            "status": status,
            "status_text": STATUS.get(status, f"unknown status 0x{status:02x}"),
        })
    return out
