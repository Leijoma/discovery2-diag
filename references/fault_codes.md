# Discovery 2 — felkoder, samlad referens (alla moduler)

Alla felkoder vi känner till — **sedda på RDL 016** och **dokumenterade online** (så
vi har en komplett bild utan att kunna provocera fram varje fel). Levande dokument;
uppdatera när vi ser nya fel eller hittar bättre källor.

**Statusnyckel:**
🔴 sedd **aktuell** (Current) på RDL 016 · 🟠 sedd **loggad/intermittent** på RDL 016 ·
📖 dokumenterad online (ej sedd) · ✅ bekräftad rå-mappad (byte↔kod känd i vår kod)

> Format skiljer per modul: SLABS `020-05`, ACE `004-02`, Airbag `004`/`022`,
> Td5-text. `<nr>-<sub>` = felnr + status/underkod. Se resp. modul.

---

## Motor — Td5 (EDC)
**Sedda på RDL 016** (reference tool-baslinje + egen läsning):
| Kod | Beskrivning | Status |
|---|---|---|
| 001-07 | EGR-vakuummodul kortslutning | 🟠 intermittent |
| 004-01 | Inlet air temp (IAT) krets | 🟠 intermittent |
| — | air flow circuit + inlet air temp circuit (under last, air_temp pegged 120°C) | 🔴 (egen läsning, B-009) |

**Full dokumenterad lista:** `src/d2diag/td5/faults.py` (**210 poster**, ur Ekaitza
get_faults/fault_code_text) + `21 3B`-bit-per-fel. ✅ rå-mappad i vår kod.

## SLABS — ABS + självnivellering
**Sedda på RDL 016:**
| Kod | Beskrivning | Status |
|---|---|---|
| 020-05 | Höger fram hjulhastighetsgivare — output too low (×254) | 🟠 loggad · ✅ rå (`21 11` byte3.bit4) |
| 027-05 | Shuttle valve switch — electrical failure (×254) | 🟠 loggad · ✅ rå (`21 11` byte10.bit4) |

**Full lista (012–114):** `references/slabs_fault_codes.md` (📖 rswsolutions).
*(Trolig tre-amigos-orsak: RF-givaren + shuttle valve.)*

## ACE — Active Cornering Enhancement
**Sedda på RDL 016 — AKTIVA fel:**
| Kod | Beskrivning | Status |
|---|---|---|
| 004-02 | Riktningsventil 2 — ström utanför intervall | 🔴 aktuell |
| 004-04 | Elfel riktningsventil 2-krets (fault 28) | 🔴 aktuell |
| 004-05 | Elfel riktningsventil 1-krets (fault 29) | 🔴 aktuell |
| 006-01 | Hydraultryck för lågt | 🔴 aktuell |

**Full dokumenterad lista:** 📖 *(online-research pågår — fylls)*

## EAT — Automatlåda (ZF4HP22/24)
Gick **ej att läsa** med denna reference tool 1. Inga sedda koder.
**Dokumenterad lista:** 📖 *(online-research pågår — fylls)*

## SRS / Airbag
**Sedda på RDL 016:**
| Kod | Beskrivning | Status |
|---|---|---|
| 004 | Airbag-varningslampa — öppen krets | 🟠 intermittent |
| 022 | Vänster bältessträckare — öppen krets | 🟠 intermittent |

**Full dokumenterad lista:** 📖 *(online-research pågår — fylls)*

## BCU — Valeo centralelektronik
Ej sniffad än → inga sedda koder. (DRL disabled = inställning, ej felkod.)
**Dokumenterad lista:** 📖 *(online-research pågår — fylls)*

---
Se även: `references/slabs_fault_codes.md`, `src/d2diag/td5/faults.py`,
minne `reference tool-d2-fault-baseline.md` (bilens aktuella fel per modul).
