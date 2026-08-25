# Discovery 2 — diagnostic module landscape

Overview of the D2's control units on the diagnostic side, to broaden the platform
beyond the Td5 engine. Compiled from the workshop manual, community research and
reference tool / a commercial vendor module guides (protocol facts; no code copied).

## Physical connection (PROVEN from FACTORY SCHEMATIC 2026-08-05)
**Source:** `referens docs/d2_electricalcircuitdiagrams_2000.pdf` (Discovery II 2000MY
Electrical Circuit Diagrams, 2nd ed) — Land Rover's own wiring diagram. This
SETTLES the pin question definitively (no more guessing).
- **Diagnostic connector V100, only connected pins:** `C0040-4 B` (ground), `C0040-5 B`
  (ground), **`C0040-7 K` = K-LINE (the only one!)**, `C0040-13 R` (signal), `C0040-16 P`
  (battery +). **NO pin 8. NO second K-line. No L-line (pin 15).**
- **K-line split `Y128` ("K LINE")** = passive shared node (multidrop). Wire code
  **K, 0.5 mm²**. The diagnostic connector (`C0040-7`) AND **SLABS (D163)** (`C0647-10 K`→Y128,
  also via header 0286 `C0286-17`→`C0504-5`) are on the SAME split. The others on Y128
  via header 0286 (K109): **ECM D131** (engine), **BCU D162** (`C0661-4`), **gearbox
  D123/EAT** (`C0193-31`), **SRS/airbag** (`C0256-9`).
  ⇒ **SLABS IS electrically on pin 7's K-line — our KKL already reaches it.** The silence
  is 100 % protocol (init/address/timing), NOT the pin and NOT an electrical gateway.
- **BCU "gateway"** = at most logical/software coordination; the schematic shows a passive
  split, so all modules hear everything ⇒ a borrowed tool's traffic IS sniffable on pin 7.
- Differs per module: **diagnostic address, init type (fast/slow), service bytes** —
  remaining research/probe work per module (the pin question is CLOSED).

## Modules to map
| Module | What | Sources / status |
|---|---|---|
| **Td5 EDC** (engine) | Address 0x13, fast init, seed/key. **DONE** in d2diag. | Ekaitza + reference tool (fault map cross-validated) |
| **Wabco SLABS** | ABS/SLS/EBD/ETC/HDC/EAS. 47 fault types, Current/Intermittent + counters. | `wabco_slabs_capabilities.md`. **FAST init** (not slow!); candidate address **0x29** → `probe_slabs.py` |
| **Valeo BCU** | Body electronics + **immobiliser/alarm/EKA/key programming**. | `valeo_bcu_capabilities.md`. Address/init unknown |
| **SRS/airbag** | Airbags. | Not mapped |
| **ACE** | Active Cornering Enhancement (roll control). | Own K-line diagnostic pin; not mapped |
| **HEVAC** | Climate. | Not mapped |
| **EAT** | Automatic gearbox — **the car is an AUTOMATIC**, so the module is relevant. | Not mapped |

## Resource: a commercial vendor module guides (functional capabilities)
a commercial vendor publishes per-module guides (PDF) describing *what* each module
exposes (inputs/settings/outputs/fault codes) — excellent for building the respective
layer. Extractable with `pdftotext`. Known URLs:
- BCU: `reference tool-diagnostics.com/uploads/downloads/Discovery II Valeo BCU ECU Guide.pdf`
- SLABS: `reference tool-diagnostics.com/downloads/preview/wabco-slabs`
- Per-module help pages: `a commercial vendor's module help pages` (SLABS = SM016).
More modules (SRS/HEVAC/ACE/EAT) likely have corresponding guides on the same
download path — worth trying when we tackle them.

## SLABS fault-code format (same as Td5!)
Community codes are given as **(X,Y)** or **X-Y** — the same bit-per-fault indexing
as the Td5's `21 3B` (X = byte offset+1, Y = bit+1). Known examples:
- `(1,1)` at start of sequence
- `(2,12)…(2,15)` air gap: RH front / LH rear / LH front / RH rear (wheel-speed sensors)
- `(15,4)` front left outlet valve open circuit
- front right outlet valve short to ground; shuttle valve switch electrical failure
This suggests the SLABS fault memory can be decoded with **the same technique as the Td5**
(offset*8+bit → fault text) once we have address/init and can read the block. The full
list (47 types) is in the Nanocom firmware but is not publicly dumped — **to be read out
once we connect to SLABS.**

## Car test 2026-08-04 (more init variants) — SLABS is on pin 7
`probe_slabs.py` + `probe_addresses.py 40 FF` + F1 variants against the car (engine C1 fault-free):
- **0x29/0x34 (F7 physical + F1 physical + functional): silent.**
- **Entire 0x01–0xFF physical fast init F7: silent** except 0x13.
- The engine check gave `03 c1 57 8f aa` every time → connection/timing excellent.

**EVIDENCE (LR OBD pinout + community): pin 7's K-line on the D2 is shared by ECM, ABS,
SLABS, HVAC, cruise control, instruments** — NO separate body-system K-line (pin 15
= L-line, barely used, only ECM). Reference tools' **Blue-lead** reaches all; NCOM13/NCOM15
= software locks, not different cables. ⇒ **SLABS IS reachable on pin 7 (our wire) — it's
protocol/address, not the pin.** (The earlier "separate pin" hypothesis is rejected.)

**Still to try (multi-mode, `tools/probe_scan.py`):** fast **F1** (entire 0x01–0xFF),
**functional (C1)** F1/F7, plus **slow init** (now corrected 8N1 — SLABS may, despite the
forum, use ISO 9141 0.4 kb/s). Creative: **passive sniff at key-on** (BCU=gateway may
wake/ping modules → addresses without guessing init). Total silence so far still points to
an unusual init/address → **sniffing a borrowed tool** remains the safest route.

## REFERENCE-TOOL SNIFF 2026-08-07 — SLABS = FAST INIT 0x29 (confirmed), BCU = SLOW
Borrowed **reference tool 1** (reads engine/SLABS/BCU/ABS/airbag/ACE; **not the auto gearbox**).
Passive sniff of pin 7 (Y-cable + KKL) captured the reference tool's init per module:
- **SLABS: `81 29 F7 81 22` (FAST init, address `0x29`) → response `03 c1 57 8f aa`**
  (C1 57 8F, KWP2000). Reproducible. ⇒ **SLABS was fast init on 0x29 all along**
  (the pyTD5Tester candidate was right). Our own fast scan missed 0x29 because of the KKL's
  unclean init pulse — ESP32 real-time timing should reach it. **So SLABS is NOT a slow module.**
- **BCU: SLOW init** — the reference tool's BCU init shows up only as `00` (5-baud bit-bang,
  not UART-readable). Consistent with our 0x40 (slow, permanently powered, works ignition-off).
- The slow-init modules 0x18/0x33/0x40 were therefore BCU (0x40) / generic OBD (0x33) / 0x18(?),
  not SLABS.

**KKL is NOT good enough as a passive tap:** it loads the bus → the reference tool can't hold
sessions (the engine didn't respond; the SLABS session broke after init). We only capture the
**init handshake**, never fault/live services; slow-init addresses aren't visible in UART.
**Next: HIGH-IMPEDANCE read-only tap** (ESP32 RX branch / discrete, 47 kΩ+ series, no TX on the
bus) for deep capture.

## BREAKTHROUGH 2026-08-05: chassis modules answer 5-BAUD SLOW INIT (proven)
`tools/slabs_hunt.py full` + `tools/verify_slow.py` against the car. Fast init (all
variants, 0x01–0xFF) was silent except the engine — **wrong init method.** With **5-baud
slow init** (ISO 9141) several modules respond with a **complete, reproducible handshake**
(0x55 sync + KW1 KW2 + correct `~address` acknowledgement):

| Address | KW1 KW2 | Protocol | Verified |
|---|---|---|---|
| **0x18** | `08 08` | ISO 9141-2 | 3/3 complete (~addr 0xE7 ✓) |
| **0x33** | `08 08` | ISO 9141-2 | 3/3 complete (~addr 0xCC ✓) |
| **0x40** | `e5 8f` | KWP2000 (KW2=8F) | 2/3 complete (~addr 0xBF ✓) |

**IDENTITY (research 2026-08-05, community + power domain) — reinterprets 0x33:**
- **0x33 = generic OBD-II** (NOT a chassis module). `0x33` is the *standard* 5-baud OBD-II
  address (ISO 9141-2), and `55 08 08` is the textbook ISO 9141-2 response. ⇒ This is the
  **Td5 engine's OBD-II side** (same ECM that answers fast init on 0x13). Community:
  "cheap devices only read engine codes" — 0x33 is precisely that generic engine entry.
- **0x40 = probable BCU (Valeo).** KWP2000 + responds with the key FULLY OFF = permanently
  battery-powered; the only D2 module that is (alarm/immobiliser). Medium-high confidence.
- **0x18 = unclear.** ISO 9141-2 (KW 08 08) like 0x33, ignition-powered. Either a real
  proprietary module (SLABS/EAT/SRS?) OR the engine's OBD side on a second address. Low conf.
- **SLABS/EAT/SRS not yet located.** IMPORTANT: the slow-init scan only tested a
  CANDIDATE LIST (0x08/14/18/28/29/33/34/38/40/44/50), not the entire 0x01–0xFF. SLABS may
  be on an unscanned slow address. **Next car test: `tools/slow_sweep.py <port>`** —
  exhaustive slow sweep 0x01–0xFF with handshake classification (COMPLETE/SYNC/silent) +
  auto re-verification (3×/8 s) + KW/protocol interpretation. One command, ~13 min, ignition on.
Sources: discoii.wordpress OBDII, a commercial module guide, reference tool Valeo-BCU/Wabco guides,
obd-cable ISO9141-5-baud (0x33 std address, 55 08 08=ISO9141 / 55 8F..=KWP).

**Power-domain fingerprint (3 key positions, 2026-08-05):** 0x40 responds **even in position 0
(key fully off)** = **permanently battery-powered** → **BCU (Valeo)** effectively confirmed
(always live for alarm/immobiliser; flaky in position 0 = woken from sleep). 0x18 & 0x33 silent
in position 0 AND position 1, respond only with **ignition on** = ignition-powered → **SLABS/EAT/SRS
etc.** ⇒ **0x40/BCU can be tested/sniffed entirely without the key** (easiest, + KWP2000 like the
engine → the best module to crack the post-init format on first). SLABS requires position 2.

**Session lock confirms authenticity:** after a successful slow init the module enters a session
and goes silent to new inits until timeout (~sec) — hence **≥8 s between attempts** is needed.
Fast repeat (2 s) gives silent #2/#3; 8 s gives 3/3. An artefact would not be stateful like that.
0x18 & 0x33 share KW `08 08` (perhaps the same module on two addresses). 0x40 = its own
KWP2000 (KW2=0x8F, like the engine's `57 8F`) ⇒ **our KWP2000 stack should reach 0x40 after slow
init.** The engine 0x13 = fast init (the exception). **Remaining:** identify which modules
(SLABS/BCU/EAT/SRS?) via a post-init request (0x40 KWP2000 first), then read DTC/data.
The fast-init hypothesis for SLABS (forum) is disproven for these addresses.

## Extended SLABS hunt test (`tools/slabs_hunt.py`) — last attempt on pin 7
One command runs the whole remaining pin-7 matrix in ONE run with a shared, timestamped
log (`logs/slabs_hunt-<stamp>.log`). Phases:
1. **Link check** — fast init against the engine (0x13), expects `C1 57 8F`. Proves the
   cable/OBD/ground/timing is OK → silence from SLABS becomes an *answer*, not a broken link.
2. **Passive sniff** ~20 s RX-only at key-on (BCU=gateway may poll modules).
3. **Active matrix** — `fast-f1`, `func-f1`, `func-f7` over 0x01–0xFF + `slow` against
   candidate addresses. Looks for C1/7F and 0x55 respectively. The engine 0x13 is always skipped.

Run (stationary, ignition on):
```
PYTHONPATH=src python3 tools/slabs_hunt.py <port> full     # ~15 min, whole matrix
PYTHONPATH=src python3 tools/slabs_hunt.py <port> quick    # ~3 min, candidates only
```
**Creative variable:** run once **engine OFF** and once **engine idling**
(SLABS/EAS/SLS active → the module may be awake differently). Total silence in BOTH
→ strong support for the pin-8 hypothesis. Logged per run for comparison.

**Nuanced conclusion 2026-08-04:** D2-specific sources agree that pin 7 is shared by
everything (SLABS/ACE/trans/BCU) with **the BCU as gateway**. Pin 8 (BMW convention)
downgraded but not ruled out. Leading explanation for the silence: **the BCU gateway
does not route our init to SLABS**. Settle it with (1) a physical pin check in the
connector, (2) **sniffing a borrowed tool** (next step) → shows exactly how it reaches BCU→SLABS.

## Bus scan 2026-08-03 (corrected 2026-08-04)
`tools/probe_addresses.py` against the car (stationary, ignition on):
- **Only 0x13 (the engine) responds to physical fast init** (`81 <addr> F7 81`, positive C1).
- With the engine session dormant + 0x13 untouched: no address **0x01–0x3F** responded.
- (Note: an OPEN engine session generalRejects all addresses and masks the bus —
  the engine must be dormant, and 0x13 must not be addressed.)

**Correct (softened) conclusion:** *no other module responded to specifically **physical fast
init with tester F7 in 0x01–0x3F** during this scan.* It does **not prove** slow init.
**Counter-evidence (LR forum + pyTD5Tester):** SLABS uses **KWP2000 fast init** —
someone read wheel speed/switches + drove outputs that way. Concrete candidate:
**`81 29 F7 81 22`** (physical 0x29, F7) and functional **`C1 34 F1 81 67`** (0x34, F1).
The scan missed them (outside 0x01–0x3F, different tester address, possibly functional init).
Read DTC via the standard service gives "invalid function" on SLABS; **clear (0x14) works**
→ fault reading happens via a non-standard service, probably `21 xx` (like the Td5).
**Next test:** `tools/probe_slabs.py` (targeted at 0x29/0x34, long silence, ≥5 s between).
So slow init is probably NOT needed for SLABS (but `slow_init` remains, with the bug of
7→8 data bits fixed 2026-08-04, for any other modules).

## Sniffing — the best route to unknown protocols
K-line is one wire, half-duplex → a **passive RX listener captures the whole conversation**
(both the tool's questions and the ECU's answers). With a borrowed tool (a commercial tool (
a commercial tool)) that reads SLABS we get the address, init, service bytes and fault
structure from real traffic — exactly how Ekaitza's `Sniffing/*.log` (and thus our Td5
knowledge) was created.
- **Connection:** OBD splitter (piggyback) — the borrowed tool on one branch, our listener
  on the other. Requires the splitter to pass through **pin 7** (K-line).
- **Listener:** ESP32 + L9637D in pure RX (best), or KKL in RX only. **RX only — never
  transmit**, otherwise you collide with the tool.
- **Tool:** `tools/esp32_read.py` (RX-only ESP32 tap, timestamps) + `tools/decode_session.py`
  (frame split on silence gaps + KWP2000 decode). Core in the `d2diag.sniff` package
  (`capture`, `decoder`).
- The 5-baud address is not visible in the UART stream (200 ms/bit) — get it by sampling the
  line level; but the services/fault structure (the hard part) come from the sniff.

## Next steps to reach a new module (pattern)
1. **Try fast init first** (the D2 mostly uses fast init): targeted StartCommunication
   against candidate addresses — for SLABS `tools/probe_slabs.py` (0x29/0x34). Slow init
   (`SerialTransport.slow_init`, now 8N1) is the fallback for modules that require it.
2. **Services:** identify read-inputs/read-DTC/clear. NOTE: standard read-DTC may give
   "invalid function" (like SLABS) → try `21 xx` ReadDataByLocalIdentifier (the Td5 pattern).
3. **Thin module layer** on top of the generic KWP2000 layer (reuse the Td5 pattern).
