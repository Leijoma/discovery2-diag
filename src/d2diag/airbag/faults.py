"""Airbag (TRW SPS 2A) felavkodning — BELAGT ur sniff 2026-08-10 (RDL 016).

Felminnet läses via ``21 02`` (svaret börjar ``61 02``). Datafältet är poster om
**2 byte: [status][fault-number]**, där fault-number är **Nanacoms display-nummer
direkt** (`0x04`=004, `0x16`=022). Tomma poster = `00 00`. Radera = `14` → `54`.

Belagt exempel (RDL 016): ``61 02 90 04 90 16 00 00 …`` →
``90 04`` = fault 004 (open circuit intermittent), ``90 16`` = fault 022 (dito).

Fault-numret slås upp mot positions-listan i felkodsordboken (Airbag, position =
display-kod, 1–65). Statuskodningen är preliminär — `0x90` observerat för båda
"open circuit intermittent"; övriga statusvärden behöver fler captures.
"""
from __future__ import annotations

FAULT_LID = 0x02          # 21 02 → felminnet (innehöll de aktiva/intermittenta felen)
FAULT_LID_ALT = 0x01      # 21 01 → tomt i capturen (annan fault-klass?)
_CLEAR = 0x14             # 14 → 54

# Preliminär status-tolkning (behöver fler captures för att bekräfta bit-betydelser).
STATUS = {0x90: "open circuit intermittent (kandidat)"}


def decode_faults(data: bytes) -> "list[dict]":
    """Avkoda datafältet (efter ``61 02``) → lista med ``{number, status, status_text}``.

    Number = Nanacoms display-felnummer (t.ex. 4 → 004). Slå upp texten i dicten
    (Airbag position=display-kod)."""
    out: "list[dict]" = []
    for i in range(0, len(data) - 1, 2):
        status, num = data[i], data[i + 1]
        if status == 0 and num == 0:
            continue  # tom/padding-post
        out.append({
            "number": num,
            "status": status,
            "status_text": STATUS.get(status, f"okänd status 0x{status:02x}"),
        })
    return out
