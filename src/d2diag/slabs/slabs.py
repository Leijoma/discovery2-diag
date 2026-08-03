"""SLABS (Wabco) modul-lager — SKELETT.

Status: SLABS kan **etableras** via 5-baud slow init (verifierat att fast init
bara når motorn 0x13). Men följande är ännu OKÄNT och krävs innan läsning/rensning
kan implementeras — måste tas fram via avsökning/upptäckt/sniff:

  1. **Adress** — vilken 5-baud-adress SLABS svarar på (`tools/probe_slow.py`).
  2. **Tjänstebytes** — hur felkoder/inputs begärs (KWP2000-tjänst? Wabco-egen?).
  3. **Felminnesstruktur** — SLABS-koder anges som (X,Y) i communityn men Y kan
     vara >8 (t.ex. "2-12"), så det är troligen (kategori, kod), INTE Td5:ans
     (byte-offset, bit). Blockets layout måste bekräftas.

Därför: :meth:`Slabs.establish` fungerar (slow init), medan läs-/rensa-metoderna
är stubbar som höjer NotImplementedError tills protokollet är känt. När det är
klart byggs ett tunt lager ovanpå det generiska KWP2000-lagret, precis som Td5.

Referens: ``references/wabco_slabs_capabilities.md``, ``references/d2_diagnostic_overview.md``.
"""
from __future__ import annotations

from ..kwp2000.kwp2000 import KWP2000

# Kända SLABS-felkoder ur community-research (FRAGMENT — inte full lista på 47,
# och (X,Y)-tolkningen är obekräftad). Enbart som referens/startpunkt.
KNOWN_SLABS_FAULTS: "dict[str, str]" = {
    "1-1": "at start of sequence",
    "2-12": "air gap — right hand front (wheel speed sensor)",
    "2-13": "air gap — left hand rear",
    "2-14": "air gap — left hand front",
    "2-15": "air gap — right hand rear",
    "15-4": "front left outlet valve open circuit",
}


class Slabs:
    """Wabco SLABS via slow init. Endast uppkoppling implementerad ännu."""

    def __init__(self, kwp: KWP2000) -> None:
        self._kwp = kwp

    def open(self) -> None:
        self._kwp.open()

    def close(self) -> None:
        self._kwp.close()

    def __enter__(self) -> "Slabs":
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def establish(self, address: int) -> "tuple[int, int]":
        """5-baud slow init mot SLABS-adressen. Returnerar keybytes (KW1, KW2).

        Höjer KLineTimeout om ingen modul svarar. Adressen tas fram med
        ``tools/probe_slow.py``.
        """
        return self._kwp.slow_init(address)

    # ---- ännu ej implementerat (kräver tjänsteupptäckt) --------------- #
    def read_faults(self) -> "list[str]":
        raise NotImplementedError(
            "SLABS läs-fel-tjänst är okänd — kräver tjänstebytes + felminnesstruktur "
            "(avsökning/sniff). Se d2diag.slabs modul-docstring."
        )

    def clear_faults(self) -> None:
        raise NotImplementedError("SLABS clear-tjänst okänd — se modul-docstring.")

    def read_inputs(self) -> "dict[str, float]":
        raise NotImplementedError("SLABS read-inputs-tjänst okänd — se modul-docstring.")
