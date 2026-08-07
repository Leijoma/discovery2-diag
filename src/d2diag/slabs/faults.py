"""SLABS-felkodsavkodning.

Felminnet läses som ett **16-byte bit-per-fel-block** (samma teknik som Td5:ans
`21 3B`), via två identifierare:
  - ``21 11`` = **loggade** fel
  - ``21 47`` = **aktuella** fel

Ett satt bit på (byte-offset, bit) = ett fel. Kopplingen (byte,bit) → reference tool-
felnummer/text är delvis känd: bekräftade **ankarpunkter** kommer från den sniffade
sessionen 2026-08-07 där `21 11` hade exakt två bitar satta som motsvarade
baslinjens två fel (`020` + `027`), och nollades efter clear. Övriga bitar avkodas
generiskt tills fler ankarpunkter tas fram (t.ex. via "framkalla känt fel").
Full nummer→text-lista finns i ``references/slabs_fault_codes.md``.
"""
from __future__ import annotations

FAULT_BLOCK_LEN = 16

# Bekräftade (byte-offset, bit) → (reference tool-nummer, text). Sniff 2026-08-07:
# 21 11 = `00 00 00 10 00 00 00 00 00 00 10 00 00 00 00 00` = fel 020 + 027.
SLABS_FAULT_BITS: "dict[tuple[int, int], tuple[str, str]]" = {
    (3, 4): ("020", "höger fram hjulhastighetsgivare — output too low"),
    (10, 4): ("027", "shuttle valve switch — electrical failure"),
}


def decode_fault_block(block: bytes) -> "list[str]":
    """Avkoda ett 16-byte SLABS-felblock till en lista med feltexter.

    Kända bitar ger ``"<nr>: <text>"``; okända ger ``"okänt (byte i, bit b)"``.
    """
    faults: "list[str]" = []
    for i, byte in enumerate(block[:FAULT_BLOCK_LEN]):
        for b in range(8):
            if byte & (1 << b):
                known = SLABS_FAULT_BITS.get((i, b))
                if known:
                    faults.append(f"{known[0]}: {known[1]}")
                else:
                    faults.append(f"okänt (byte {i}, bit {b})")
    return faults
