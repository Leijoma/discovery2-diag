# Handoff — Discovery 2 diagnostics: protocol state (for parallel work)

This document summarizes what is **proven** vs **candidate** vs **open**, so a second
analyst can build on it without re-deriving. The car: RDL 016, Td5 ES,
ZF4HP22/24. Sniff = passive ESP32 (RX-only) on K-line pin 7, while the reference tool runs.

## Log files (raw data)
| File | Content |
|---|---|
| `logs/session.log` | **Cleanest** — TD5 (fuelling/outputs/security) + full SLABS sweep |
| `logs/faultread-20260809.log` | Auto gearbox (EAT), ACE, Airbag — read faults/inputs/outputs |
| `logs/faultread-20260809-2.log` | BCU (RF test, EKA read) |
| `logs/labeled_captures.jsonl` | Labeled captures: `{module, lid, raw, text}` (plain-text reference) |
| `logs/analysis-all.txt` | Machine-run analysis of all logs (`tools/analyze_capture.py`) |

## Framing & conventions
- **Log format:** lines `[ms] hh hh …` (ESP32 gap frames + timestamp), `>>> text` = operator marker.
- ⚠️ **Markers land IN THE MIDDLE of a sensor's stream** — not before/after. Anchor retroactively:
  search backwards (~2–6 s) for a traffic regime that differs from the previous one.
- **Screen fingerprint:** each reference tool screen polls a fixed set of `21 xx` — so tie
  annotations to the *regime*, not the nearest packet.

## TD5 (Lucas) — KWP2000, **base protocol solved**
- **Frame:** `<len> <SID> <data…> <cs>`, `cs = sum(all preceding) mod 256`. **Verified.**
- **Fast init:** addr `0x13` → `C1 57 8F`. Session `10 A0`→`50`. Security `27 01`(seed)→`67`,
  `27 02`(key)→`67`. **Keygen proven** (seed `d3 e6`→key `ad 87`).
- **Services:** 21→61 (ReadLocalId), 30→70 (IOControl), 31→71 (StartRoutine),
  33→73 (RoutineResults), 3E→7E (TesterPresent), 1A→5A (ReadEcuId), 14→54 (Clear), 18→58 (ReadDTC).
- **Fault codes:** `21 3B` = 35-byte bit block (index = offset·8+bit). Decoded in `td5/faults.py` (210 bits).
- **Fuelling (PROVEN against the car, see labeled_captures):** `09`=rpm, `0D`=road speed,
  `10`=battery(u16/1000), `1A`=temp×4 (u16/10−273.2; ext_temp@8 = unconnected 150°C),
  `1B`=accel way1/2/3+supply (4×u16/1000 V), `1C`@0=MAP, `21`=idle err(s16), `23`=ambient×2,
  `40`=cyl balance 1–5 (s16). NOTE the reference tool shows pressure in **kPa** = our bar × 100.
- **Outputs (30 xx FF):** A1 fuel pump, A2 MIL, A3 AC-clutch, A4 AC-fan, B3 glow, B7 rev-counter,
  BA temp-gauge, BE wastegate(+PWM), BD EGR(+PWM). **Injectors:** `31 C2 0<n>` (cyl 1–5). Coded.
- **Security:** `31 C0` + `33 C0` → `73 C0 03` (03 = not immobilised). Coded.
- **OPEN:** switch inputs = `21 1E` + `21 36` **bit fields** (1E toggled `00 CA`↔`00 EA` = bit `0x20`;
  36 constant `00 0D`). Settings fetched in **bulk** (`21 3D 20 0E 32 24`, one-off). Needs
  differential (change a switch/setting → see the bit).
- **OPEN (BinOwl leads, 2026-08-25):** `21 1C` is an **8-byte** block — @2 = MAP raw,
  **@4 = MAF (u16/10 kg/h)**, @6 = constant 0x009C. RDL 016 reads @4 = 0 with
  `air flow circuit (Current)` live, i.e. plausibly a dead sensor, not a wrong offset —
  which would make our `1D`@4 `maf` a *modelled* air mass instead. Also unread:
  **`21 38` = wastegate modulator (u16/1000 %)**, `21 1D`@0 = driver fuel demand,
  `21 1D`@14 = idle fuel demand. Details + test plan in `references/td5_externa_fynd.md`.

## SLABS (Wabco) — KWP2000, base protocol solved
- **Fast init addr `0x29`** → `C1 57 8F`. Faults: `21 11`=logged / `21 47`=current (bit block),
  clear `14 FF FF`→`54`. Decoded. RDL 016: `020-05` RF sensor + `027-05` shuttle valve (logged).
- **Screen fingerprints:** SLS inputs `21 53/54/55`; ABS inputs `21 43/44/49/50/57`;
  switches `21 42/48/56/58`; settings `21 45/46/49/59`.
- **Proven:** `21 54` = live height L/R (byte0/1). `21 43` = wheel speed, stationary `7c 00 ×4`
  (≈124 baseline ≠ 0). any-door = `21 56` byte0 bit0.
- **OPEN:** analog scaling for 53/55 (supplies), 44/49/57 (valves/voltages), 50 (ABS sensor V).
  Settings **LID→function UNSOLVED** (order-based labeling contradicts itself across runs —
  needs differential). "Stored height" ≠ `21 54` (different source, not captured).

## Airbag (TRW SPS 2A) — **fault format decoded; address 0x5B (PROVEN)**
- **Address `0x5B`, ADDRESSED framing per message** (ISO 14230 format byte,
  NOT the Td5/Slabs unaddressed session frames). Proven from `faultread-20260809.log`
  line 885: `82 5b f7 21 02 … → f7 5b 61 02 90 04 90 16 00 00 …`.
- `21 02` → `61 02` + entries **`[status][fault-number]`**; number = display number directly
  (`90 04`=004, `90 16`=022). Status `0x90` = open circuit intermittent (candidate).
  `21 01` was empty (a different fault class?). Clear `14`→`54`. Coded in `airbag/faults.py`.
- **SecurityAccess was seen on 0x5B** (lines 882–883): seed `44 8E` → key `00 6E` → **positive `67 02`**
  (probably required before clear, NOT before read). ⚠️ **CORRECTION:** this 0x5B pair belongs to
  the AIRBAG — NOT "uncertain module/BCU" as previously noted under BCU. The only known complete
  seed→key pair with a positive acknowledgement in the whole material.
- **OPEN:** the status byte's bit meanings (more captures); 01 vs 02; an `Airbag(EcuSession)`
  read-only class requires support for addressed per-message framing (a different path than Td5/Slabs).

## Auto Gearbox (EAT, Bosch GS8.87) — **different protocol (`72`-framed)**
- The reference tool said "unable to perform the function", BUT the ECU **responds with a data block**.
- **CONFIRMED (reproduced in two independent sessions — `faultread-20260809.log` + `-3.log`):**
  - Read faults: `72 05 04 00 73` → **`72 09 60 01 00 00 00 00 1B`**
  - Clear faults: `72 04 05 73` → `72 04 60 99 FF`
  - ⚠️ `72 04 60 99 FF` is a **generic status/ack** — the same response comes on the keepalive poll
    `72 04 1E 68`. Do NOT interpret it as a fault-specific acknowledgement.
  - Payload `01 00 00 00 00` in the read-fault response: do **NOT** interpret yet (not a fault count/empty list/DTC structure).
- Other functions (from an older log): settings `72 05 93 00 E4`, inputs pressure `72 05 0B 00 7C`,
  inputs general `72 05 0B 03 7F`, reset adaptive `72 06 83 FF 07 08 FF`. Response: `72 <len> 60 <data> <cs>`.
- **OPEN:** content interpretation, the meaning of `60`, why the reference tool rejects the response — wait for a successful session.

## ACE (Lucas) — bulk block
- Fault block (one-off): `67 67 11 e0 e0 f0 f0 00 00 00 1a 00 00 08 09 80 92 00 00` = fault set
  {`004-02`, `004-04`, `004-05`, `006-1`}. Then only `04 04 00`/`07 07 00` is polled (keepalive).
- Utilities: calib acc1 `15 15 FF`, calib acc2 `16 16 FF`, set calibrated `10 10 00`.
- Inputs = **one bulk block** streamed ~1/s (offset/bit mapping, not one request per sensor).
- ⚠️ **Open question (duplication):** many bytes come in pairs (`67 67`, `e0 e0`, `f0 f0`, `04 04`).
  Is it the protocol or a sampling artefact? Needs settling (affects all ACE/EAT interpretation).

## BCU (Valeo) — EKA solved; outputs = four 3B banks (structure proven, bits open)
- **EKA:** read `21 CC`, write `3B CC <4 bytes>`. Captured: `3B CC XX XX XX XX` → **EKA XXXX**.
- Settings IDs (BCU settings screen): `C7 CA CB D3 EB C6 CE D4 D5 D6 D7 …` (match against documented groups).
- **Outputs require SecurityAccess before writes (HIGH, from `-4.log`):** `27 01`→`67 01 <seed>`,
  `27 02 <key>`→ positive/negative. Captured attempt: seed **`EB CD`** → key `C0 10` → **DENIED `7F 27 83`**;
  after restart key `4A 8A` was sent, after which 3B writes began. ⚠️ **No clean `67 02` in the log** for
  the successful attempt — that writes followed is *inferred*, not proven. Do NOT mark `4A 8A` as a universally valid key.
- **Output writes = `SID 3B` (WriteLocalId) against four 4-byte banks (PROVEN structure, checksums validated):**
  `06 3B 22 00000000 63` · `06 3B 23 … 64` · `06 3B C1 … 02` · `06 3B C2 … 03`
  (cs = sum incl. length byte, mod 256). Repeated around fog/DRL/indicators/windows.
- ⚠️ **CRITICAL — all captured bank payloads are `00 00 00 00`.** NEVER tie an output (e.g. fog light)
  to a bank/bit via the nearest annotation. The zero writes are probably **reset/disable-all housekeeping**
  (the same four zeros are re-written between annotated commands). The actual "ON" frame is missing from the capture.
- **Extra seed/key data (different provenance — for future algorithm work, NOT clean BCU material):**
  `-2.log` gave key `4B 5C` but **the seed line is corrupt/duplicated** → unusable pair. The large log has a
  complete pair `seed 44 8E → key 00 6E` with a **positive `67 02`**, but on **address `0x5B` with double framing**
  (a different/uncertain module — NOT proven BCU). ⇒ One single clean BCU sample (EB CD→C0 10, denied) — derive no algorithm yet.
- **OPEN:** provoke a non-zero bank state; map individual output bits; the seed→key algorithm;
  which session/security the bank writes actually require.

## Tools
- `tools/analyze_capture.py <log>` — checksum-validated KWP req→resp, fingerprints,
  retroactive anchoring, recognizes 72/67/90/CC frames. Output in `logs/analysis-all.txt`.

## Suggested division of labour
- **Claude (code):** analyze_capture → machine-readable protocol library (JSON), fold in
  function IDs/decoders in `d2diag`, tests.
- **ChatGPT (hypotheses):** deep byte-field analysis on **one** bulk block at a time — start with
  (a) the ACE duplication question + ACE fault-block structure, or (b) the TD5 settings bulk (`21 3D/32/0E`),
  or (c) the EAT `72` frame format. Deliver candidate offsets/bits + which differential test confirms it.
