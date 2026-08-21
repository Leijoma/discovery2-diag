# Fault codes — index (the canonical dictionary lives in the register)

**Canonical fault-code dictionary:** `Discovery 2/discovery2_reference tool_fault_dictionary.md`
(the register) — a reverse-engineering structure with confidence, raw-bytes column,
status encoding, occurrence, sources and flagged display-vs-raw conflicts. Filled in
alongside the sniff work. Capacities: TD5 >200 (256 slots), SLABS 47,
ACE 45, Auto Gearbox GS8.87.0 39, Airbag TRW SPS 2A 37.

This is only an **index** to our code-embedded and sniffed sources:

| Module | Raw-mapped in code | Public list | Seen on RDL 016 |
|---|---|---|---|
| **Td5** | `src/d2diag/td5/faults.py` (210, `21 3B` bit-per-fault) | reference tool Lucas TD5 guide + **forum list (Kelvin, complete X-Y)** — forum note: `28-7` topside switch ≈ ECU failure (not seen here) | `01-07` EGR, `04-01` IAT (intermittent); air flow+IAT under load |
| **SLABS** | ✅ `21 11`=logged / `21 47`=current (bit-per-fault, index=byte*8+bit), `14 FF FF`=clear. Confirmed: `020-05`→byte3.bit4, `027-05`→byte10.bit4 | `references/slabs_fault_codes.md` (012–114) | `020-05` RF sensor + `027-05` shuttle valve (×254, logged) |
| **ACE** | — (bulk block isolated) | dict **complete 0001–0048** (factory display index = display index, forum-confirmed) | `04-02/04/05` directional valves + `06-01` low pressure (current) — **re-read 2026-08-10**, cleared + calibrated accelerometers. Fault block: `67 67 11 e0 e0 f0 f0 … 08 09 80 92`. Utilities: calib1=`15 15 ff`, calib2=`16 16 ff`, set cal=`10 10 00` |
| **EAT** | — (different protocol, `72`-framed) | dict (39, RAVE) — **forum-confirmed** factory display index 1–39 | reference tool "unable to perform the function" 2026-08-10, BUT the ECU **responds** with a data block. Functions: read faults `72 05 04 00`, clear `72 04 05`, settings `72 05 93 00`, inputs `72 05 0b 00/03` |
| **Airbag** | ✅ **`src/d2diag/airbag/faults.py`** (`21 02`→entries `[status][num]`) | dict **position=display code solved**; full string dump 1–65 | `004` + `022` (intermittent) — **re-read + cleared 2026-08-10**; raw `61 02 90 04 90 16` decoded |
| **BCU** | — (EKA via LID `CC`) | no conventional fault capacity (reference tool) | EKA `XXXX` read: `21 CC`=read, `3B CC XX XX XX XX`=write (ignition cycling to connect) |

> ✅ **CORRECTION (earlier error):** ACE/EAT/Airbag/BCU are **structured protocols**,
> not "junk" — they just use different framing than the TD5/SLABS KWP. Analyze the logs
> with **`tools/analyze_capture.py`** (checksum-validates KWP, recognizes `72`/`67`/
> `90 xx`/`CC` frames, anchors annotations retroactively). The airbag fault format is now
> decoded in code; Autobox/ACE/BCU function IDs identified. ACE inputs are a
> **bulk block** → requires differential captures for field mapping.

**Workflow:** sniff → analyze (`decode_session.py`) → fill in **raw bytes + status
encoding** in the dict (the register) → update our code (`faults.py` / SLABS decoder).
The sniff resolves display-vs-raw conflicts (e.g. SLABS `027-05` = `0B10`; TD5 `01-07`).
