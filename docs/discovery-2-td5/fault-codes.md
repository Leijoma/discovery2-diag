# Fault codes — reading and raw ↔ display mapping

How the Discovery 2 Td5 modules store diagnostic faults over the K-line, how this
tool reads and decodes them, and — critically — where the **raw K-line index**,
the **factory-tool fault number**, and the **human-readable text** are known to
line up versus where they still have to be sniff-mapped rather than assumed.

Confidence tags follow [`../README.md`](../README.md): 🟢 Proven (sent the bytes,
confirmed against a real vehicle), 🟡 Assumed (derived/transcribed, not yet
confirmed on our car), 🔴 Unknown (open question). The reference car throughout is
a Discovery 2 Td5, reg. **RDL 016**.

> **The one rule that matters on this page:** a factory tool's fault *number* is a
> display index, not the raw storage location, and the two do **not** trivially
> agree. On SLABS we have proof they disagree (see below). Never map raw byte/bit
> to a display number by guessing — it must be captured with both halves visible at
> once.

---

## Td5 (Lucas engine ECU)

Unlike the other modules, the Td5 fault memory is **already raw-mapped in code** —
we read it directly on the K-line and decode it bit-for-bit.

- Raw decoder: [`src/d2diag/td5/faults.py`](../../src/d2diag/td5/faults.py) — 210
  named fault bits.
- Live signals: [`src/d2diag/td5/identifiers.py`](../../src/d2diag/td5/identifiers.py).

### How the faults are read 🟢

The Td5 does **not** expose standard OBD DTCs. The fault memory is fetched as a
single **status block** via ReadDataByLocalIdentifier `21 3B` — the bytes that
follow the positive response `61 3B`.

- The block is **35 bytes** (offset 0–34) and **bit-encoded**: every bit is one
  fault.
- **Fault index = offset·8 + bit**, where bit 0 = mask `0x01` … bit 7 = `0x80`.
- The tolerant read can trail the frame checksum/glitch after the block; the
  decoder truncates to 35 bytes (`FAULT_BLOCK_LEN`) so that trailing noise is never
  decoded as a fault.
- Any set bit with no known text is reported generically as `byte<off>.bit<n>`, so
  an unrecognised fault bit never disappears silently.

*Evidence:* the offset·8+bit encoding and the bit map are **proven** — cross-validated
between two independent reference sources (Ekaitza_Itzali's `get_faults` /
`fault_code_text`, and an independent reference tool v1.12); both give the same name
at the same offset/bit. No code was copied (facts about a bus are not copyrightable;
see `THIRD_PARTY_LICENSES.md`). The block itself was also read live on RDL 016
(2026-08-08).

### Clearing Td5 faults 🟢

Faults are cleared with StartRoutine `0xDD` followed by **18 zero bytes**.

> Observed on RDL 016: the `54` acknowledgement to the clear routine came back
> **delayed by ~300 ms** rather than immediately. Read logic must wait for it; a
> tight timeout will miss the ack and wrongly report the clear as failed.

### Fault-table structure

Each row in `FAULTS` is a `Fault(offset, mask, name)`. A raw block byte at `offset`
is AND-ed with `mask`; if non-zero, that fault's `name` is emitted. So a single raw
bit maps to exactly one description. Example rows:

| Offset | Mask | Bit | Name |
|---|---|---|---|
| 0 | `0x04` | 2 | egr vacuum diagnostics (Logged Low) |
| 1 | `0x01` | 0 | inlet air temp. circuit (Logged Low) |
| 4 | `0x40` | 6 | air flow circuit (Current) |
| 27 | `0x40` | 6 | topside switch failed pre injection (Logged) |

The status suffix is finer than Ekaitza's coarse Logged/Current, taken from the
reference-tool distinction. The block is laid out in **offset bands**:

| Offset band | Meaning |
|---|---|
| 0–1 | **Logged Low** — stored, signal low (short / low voltage), sensor circuits |
| 2–3 | **Logged High** — stored, broken circuit (high) |
| 4–5 | **Current** — sensor-circuit faults active right now |
| 6–13 | Drive stages (over-temp / open-load / short), Logged then Current |
| 14–25 | Crank, CAN, boost, driver demand, road speed, cruise control |
| 26–34 | Injectors 1–6 (peak long/short, open/short/partial) + topside switch |

### Display-code ↔ raw (still to be sniff-mapped) 🔴

The reference tool shows faults as `X-Y` (e.g. `28-7` topside switch), while our raw
mapping yields `offset.bit`. These have **not** been fully cross-validated for the
Td5 — the way to do it is to sniff the factory/reference tool while it reads Td5
faults, capturing the raw block and the displayed code simultaneously (the same
method proven on SLABS below). Our decoder holds the raw side; the display-code
dictionary holds the `X-Y` side; the bridge between them is an open item.

> 🔴 **`28-7` / topside switch failed pre-injection** (offset 27 bit 6 Logged;
> offset 29 bit 6 Current) is the forum's strongest lead for *engine stops dead /
> tool won't connect* — the topside switch is a solenoid **inside the ECU** that
> fails, especially after moisture ingress. Not seen on RDL 016.

---

## SLABS (Wabco ABS + rear self-levelling)

- Raw decoder: [`src/d2diag/slabs/faults.py`](../../src/d2diag/slabs/faults.py).
- Display-number list: [`../../references/slabs_fault_codes.md`](../../references/slabs_fault_codes.md).

### How the faults are read 🟢

SLABS stores faults as a **16-byte bit-per-fault block** — the same technique as the
Td5's `21 3B` — read via two identifiers:

- `21 11` = **logged** faults
- `21 47` = **current** faults

A set bit at (byte offset, bit) is one fault; index = byte·8 + bit, bit 0 = `0x01`.
Faults are cleared with `14 FF FF`.

> **Poll SLABS lightly.** SLABS reads must stay sparse (see the platform notes):
> block-reading many LIDs each cycle or running an aggressive fault-watch kills the
> session after ~15 s. Read faults occasionally, not every poll.

### CRITICAL: reference tool fault numbers differ from the rsw-list numbers 🟢

This is the whole reason the raw ↔ number ↔ text mapping cannot be assumed. On
RDL 016 (reference tool, 2026-08-07) the two real SLABS faults were displayed as **020** and
**027**. In the published rsw ABS-code list the *same physical faults* — RF
wheel-speed sensor output-low and shuttle-valve-switch electrical failure — are
numbered **044** and **114**. The display number depends on which tool you read
with; it is **not** the raw storage index.

The raw block resolves the ambiguity. In the same sniffed session, `21 11` came back
as:

```
00 00 00 10 00 00 00 00 00 00 10 00 00 00 00 00
```

— exactly two bits set, at (byte 3, bit 4) and (byte 10, bit 4), which zeroed after
a clear. Those are the two anchor points now encoded in `SLABS_FAULT_BITS`:

| Raw (byte, bit) | reference tool # | rsw list # | Text |
|---|---|---|---|
| (3, 4) | 020 | 044 | RH-front wheel-speed sensor — output too low |
| (10, 4) | 027 | 114 | Shuttle valve switch — electrical failure |

Every other bit is decoded generically as `okänt (byte i, bit b)` until more anchor
points are captured (e.g. by inducing a known fault). The full display-number list
(012–114) in `references/slabs_fault_codes.md` is the **display** side only, and is
explicitly tagged as such — it is 🟡 Assumed for the raw mapping until sniffed.

The rsw numbering is regular (per 8 valves = 4 wheels × in/out, per fault type;
per 4 wheel-speed sensors; relays; pump), which strongly suggests the raw index is
also systematic — but "suggests" is 🟡, not proven, and does not license guessing
individual bits.

---

## Known real faults on RDL 016 (baseline)

Read on the actual car with a borrowed reference tool (2026-08-07), across the K-line
modules. All 🟢 — these are faults an established factory tool displayed on the real
vehicle. Note the tool-number caveat above: the Td5/SLABS numbers below are reference tool
display numbers.

| Module | Fault | reference tool # | Meaning | State |
|---|---|---|---|---|
| Td5 | `001-07` | 001 | EGR vacuum module — short circuit | Intermittent |
| Td5 | `004-01` | 004 | Inlet-air-temp (IAT) circuit | Intermittent |
| SLABS | `020-05` | 020 (rsw 044) | RH-front wheel-speed sensor — output too low (×254) | Logged / intermittent |
| SLABS | `027-05` | 027 (rsw 114) | Shuttle valve switch — electrical failure (×254) | Logged / intermittent |
| ACE | directional-valve faults | — | Directional valve / low hydraulic pressure | **Active** |
| Airbag/SRS | warning-lamp + LH pretensioner | — | Airbag warning lamp open circuit; LH seatbelt pretensioner open circuit | — |

Notes:
- The two SLABS faults each carried an occurrence count of **×254** (a saturated
  counter), consistent with a long-standing intermittent condition rather than a
  hard current fault.
- ACE was the only module with **active** (current) faults at the baseline read.
- A separate Td5 raw-sniff on RDL 016 (2026-08-08) additionally decoded, under warm
  idle/load: air flow circuit (Current + Logged Low), inlet air temp (Logged High),
  can tx/rx error (Logged), and driver-demand problems — plus two to treat with
  suspicion: an "inj. 6 peak charge long" (the engine is 5-cylinder) and an
  unmapped `byte18.bit6`. Those are raw-decoder output, useful but not the reference tool
  baseline.

---

## Open questions 🔴

- **Td5 display-code ↔ raw bridge.** The reference-tool `X-Y` codes have not been
  cross-validated against our `offset.bit` mapping. Needs a labelled capture (raw
  `21 3B` block + displayed code, simultaneously).
- **Td5 unmapped bits.** Several set bits have no text in the source table (decoded
  as `byte<off>.bit<n>`); `byte18.bit6` seen on RDL 016 is one concrete example.
- **SLABS raw ↔ number mapping is 2 of ~47 bits.** Only (3,4)→020 and (10,4)→027
  are anchored. The rest of the 16-byte block (and which identifier band maps to
  which fault family) is unmapped; the regular rsw numbering is a hint, not a proof.
- **SLABS reference tool-number ↔ rsw-number offset.** The 020/044 and 027/114 pairs show
  the two tool numbering schemes diverge, but the *rule* relating them is unknown —
  so neither list can be used to predict the other, or the raw index.
- **ACE / EAT / Airbag / BCU** use different framing than the Td5/SLABS KWP path and
  are only partially decoded (airbag fault format is decoded in
  `src/d2diag/airbag/faults.py`); their raw ↔ display mappings are outside this
  page's proven scope.
