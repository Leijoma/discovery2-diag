# Other Modules — ACE, EAT Autobox, Airbag/SRS

Three more modules hang off the shared Discovery 2 K-line. All three are at an
earlier stage than the Td5 engine, SLABS, or BCU: addresses and/or framing are
partly established, but live-data and fault-payload decoding is incomplete. This
page records exactly what is proven versus open for each, so nothing here reads as
more finished than it is.

Everything below was reverse-engineered from passive ESP32 (RX-only) sniffs of the
factory tool talking to **RDL 016**, 2026-08-09/10, unless noted. The passive tap
loads the bus and occasionally bit-flips or drops the ECU's response frames, which
is why several facts are stuck at 🟡/🔴.

---

## Airbag / SRS (TRW SPS Type 2A)

> 🔴 **Pyrotechnic safety module — read-only by construction.** This layer reads
> fault codes only. **No clear, no outputs, no SecurityAccess writes** — deliberately
> not implemented. Never activate any output or igniter circuit. Our sniffer is
> RX-only.

The airbag module is the **exception to the platform's framing rule**: where Td5,
SLABS, and BCU run an unaddressed length-prefixed session after init, the airbag
uses **addressed framing on every message**, throughout the session.

| Property | Value | Confidence |
|---|---|---|
| Diagnostic address | `0x5B` | 🟢 Proven — sniff RDL 016, 2026-08-10 |
| Init | 5-baud **slow** init (`55` sync) | 🟢 Proven (same sniff) |
| Framing | **Addressed per message** (`82 5b f7 …` / `f7 5b …`), ISO 14230 format byte | 🟢 Proven |
| Session | StartDiagnosticSession `10 81` → `50 81` (session `0x81`, **not** Td5's `0xA0`) | 🟢 Proven |
| Read faults | `21 02` → `61 02` + `[status][fault-number]` records | 🟢 Proven (format decoded) |
| Fault-number encoding | display number directly (`0x04` = 004, `0x16` = 022) | 🟢 Proven |
| Status-byte meaning | `0x90` = "open circuit intermittent" | 🟡 Assumed (candidate; needs more captures) |

**Proven fault example (RDL 016):**

```
82 5b f7 21 02 …  →  f7 5b 61 02 90 04 90 16 00 00 …
                                  └004┘ └022┘ └pad┘
```

`90 04` = fault 004, `90 16` = fault 022 (both "open circuit intermittent" per the
factory tool). `21 01` came back empty (a different fault class?). Records are
2-byte `[status][fault-number]`; `00 00` is padding. Decoded in
`src/d2diag/airbag/faults.py`.

**Caveats and open items:**

- ⚠️ **Not verified against the car by us.** The whole layer is derived from **one**
  sniffed sequence. In that capture the factory tool performed a SecurityAccess
  (seed→key) *before* reading. We believe `21 02` (read) does **not** require the
  unlock and that SecurityAccess is only needed before *clear* — but this is
  unconfirmed. If `21 02` does require an unlocked session, our read will fail with
  a negative response and airbag reading is blocked until the algorithm is known.
  Reading is harmless; a soft failure is acceptable.
- 🔴 The one **complete seed→key pair with a positive acknowledgement** in the
  entire material is on this module: seed `44 8E` → key `00 6E` → positive `67 02`.
  It is a single pair (no algorithm derivable), and it belongs to airbag `0x5B` —
  *not* to the BCU, as an earlier note mistakenly filed it.
- 🔴 Status-byte bit meanings (beyond the `0x90` candidate), and the `21 01` vs
  `21 02` distinction, need more captures.
- The Settings/ID page (manufacturer, VIN, airbag-present flags, etc.) is `todo` —
  read-only when reached; VIN is the only documented writable field and we read it
  only. TRW SPS 2A has **no** output/utility page by design.

Source: `src/d2diag/airbag/airbag.py`, `src/d2diag/airbag/faults.py`,
`src/d2diag/airbag/menu.py`.

---

## EAT Autobox (Bosch GS8.87.0 / ZF4HP22-24)

The automatic gearbox ECU speaks a **different, non-KWP2000 protocol** — its own
`72`-prefixed framing. Notably, the factory tool itself displayed *"unable to
perform the function"* during the sniff, **yet the ECU still answered with data
blocks**, which is how we have anything at all.

| Property | Value | Confidence |
|---|---|---|
| Protocol | Proprietary **`72`-framed** (`72 <len> <cmd…> <cs>`; response `72 <len> 60 <data> <cs>`) | 🟢 Proven (frame shape) |
| Diagnostic address / init type | — | 🔴 Not recorded in our sources |
| Read faults | `72 05 04 00 73` → `72 09 60 01 00 00 00 00 1B` | 🟢 Proven (reproduced in two independent sessions) |
| Clear faults | `72 04 05 73` → `72 04 60 99 FF` | 🟢 Proven frame, but see caveat |
| Fault payload meaning | `01 00 00 00 00` | 🔴 Unknown — do not interpret |

**What's confirmed vs open:**

- ✅ **ReadFaults is confirmed**: `72 05 04 00 73` reliably returns a data block
  (`72 09 60 01 00 00 00 00 1B`), reproduced across two independent sessions
  (`faultread-20260809.log` + `-3.log`).
- ⚠️ The clear-faults reply `72 04 60 99 FF` is a **generic status/ack** — the
  *same* frame comes back on the keepalive poll `72 04 1E 68`. Do **not** read it
  as a fault-specific acknowledgement.
- 🔴 The read-fault payload `01 00 00 00 00` is **undecoded**. Do not assume it is a
  fault count, an empty list, or a DTC structure — it is genuinely open.
- 🔴 The meaning of the `60` byte, and *why* the factory tool rejects a response the
  ECU clearly sends, are open — waiting on a successful session.
- Other functions seen in older logs (same `72 <len> 60 <data> <cs>` response
  shape): settings `72 05 93 00 E4`, inputs-pressure `72 05 0B 00 7C`,
  inputs-general `72 05 0B 03 7F`, reset-adaptive `72 06 83 FF 07 08 FF`. All 🔴
  undecoded.
- The fault dictionary side is better off: **39 RAVE P-codes** for this box are
  compiled (official + forum-confirmed), ready to map once the payload structure
  is cracked.

Source: `src/d2diag/autobox/menu.py` (menu + confirmed command IDs); the 26-input
live list is transcribed but every field is `todo`.

---

## ACE (Lucas Active Cornering Enhancement)

ACE is the hydraulic active-anti-roll system. Its data arrives as **bulk blocks**
streamed ~once per second (an offset/bit-mapped block, not one request per sensor),
rather than discrete LID reads.

| Property | Value | Confidence |
|---|---|---|
| Diagnostic address | asserted "known" in `portabilitet_andra_bilar.md` | 🟡 Assumed — the concrete address byte is **not recorded** in these sources |
| Init type / framing | — | 🔴 Not established (ACE not yet cleanly sniffed by us) |
| Fault block | one-shot bulk block, then keepalive polling | 🟡 Assumed (structure seen, not decoded field-by-field) |
| Live inputs | single streamed bulk block (~1 Hz) | 🔴 Offset/bit mapping open |

**What we have:**

- A one-shot **fault block** was captured:
  `67 67 11 e0 e0 f0 f0 00 00 00 1a 00 00 08 09 80 92 00 00`, which the factory tool
  displayed as the fault set **{004-02, 004-04, 004-05, 006-1}** on RDL 016. After
  that, only keepalive-style polls (`04 04 00` / `07 07 00`) stream.
- Utility commands were seen: calibrate accelerometer 1 `15 15 FF`, accelerometer 2
  `16 16 FF`, set calibrated `10 10 00`. ⚠️ These **write calibration** — out of
  scope, listed only so they are recognised, never sent.
- The fault-code dictionary side is compiled (ACE 0001–0048); `04-02/04/05` and
  `06-01` were seen on RDL 016 via the factory tool. Raw not yet sniffed by us.

**Open questions:**

- 🔴 The concrete **diagnostic address and init/framing** are not established in our
  material — the address is asserted "known" but no byte is recorded here, so it is
  not treated as proven.
- ⚠️ **Byte-doubling puzzle:** many bytes arrive in pairs (`67 67`, `e0 e0`, `f0 f0`,
  `04 04`). Whether that is the protocol or a sampling artefact of the passive tap
  is **unresolved**, and it affects the interpretation of *all* ACE (and possibly
  EAT) blocks — it needs to be settled before any field decode is trusted.
- ⚠️ ACE caveat (factory-tool behaviour): its valve fault codes are unreliable — a
  pressure-sensor fault can present as a "control valve" fault. Read live pressure
  first; outputs activate real valves. Stationary only.

Source: `src/d2diag/ace/menu.py` (menu + coverage status; nothing is `ok` yet —
ACE has not been cleanly sniffed).

---

## Summary status

| Module | Address | Init / framing | Decoded | Open |
|---|---|---|---|---|
| Airbag (TRW SPS 2A) | `0x5B` 🟢 | 5-baud slow, **addressed** framing, session `0x81` 🟢 | Fault format (`21 02`) 🟢 | Status bits 🟡, our-car verification, SA-before-read question |
| EAT autobox (Bosch GS8.87.0) | 🔴 not recorded | `72`-framed proprietary 🟢 | ReadFaults *frame* 🟢 | Fault payload 🔴, all live data 🔴 |
| ACE (Lucas) | 🟡 "known", byte not recorded | 🔴 not established | Fault-set mapping (via tool) 🟡 | Address, framing, bulk-block decode, byte-doubling 🔴 |

See also `references/protocol_state_handoff.md` (proven/candidate/open per module)
and `references/portabilitet_andra_bilar.md`.
