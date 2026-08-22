# Td5 — findings from external repos (research 2026-08-21)

Review of EA2EGA/Ekaitza_Itzali (Python, real sniff logs), SimonRafferty
and muki01. Purpose: find what we do NOT already have. We turned out to be in good shape.

## Already implemented on our side (confirmed by Ekaitza's real sniffs)
- **Immobiliser/security status** — `security_status()` = `31 C0` + `33 C0`,
  RDL016 = **0x03 (not immobilised), proven**. NOTE: Ekaitza's README lists this
  as "Not yet" (unimplemented) — WE have it independently. "Learn code" is deliberately NOT done.
  ⚠️ Not yet shown in the v2 UI ("security status: planned").
- **Outputs `0x30`** — our `_OUTPUTS` matches Ekaitza's captured bytes exactly:
  A1 fuel pump · A2 MIL · A3 A/C clutch · A4 A/C fan · B3 glow plugs · B7 rev-counter
  sweep · BA temp-gauge sweep · BD EGR modulator (PWM).
- **Injector tests** `31 C2 01…05` (cylinder balance) — has `injector_pulse`.
- **Seed→key** LFSR (taps bits 1,2,8,9) — has a keygen.
- **Checksum = sum(all bytes incl. length) mod 256** — confirms the `raw_analyze` parser.
- **Fast init 25 ms low + 25 ms high** — matches ours (muki01 in
  `references/muki01_OBD2_K-line_Reader/`, Wayback capture, MIT).

## New to possibly adopt (unverified against RDL016 — confirm first)
- **`21 1D` = "fuel-usage params"** (Ekaitza) → confirms that MAF (1D@5) AND
  fuel/injection data live in the 1D block. **The route to fuel consumption** goes via
  injection quantity (mg/stroke) in 1D — hunt the field from a LOADED drive (byte1 27→65,
  byte11 50→127 moved with rpm; load distinguishes injection from pure rpm fields).
  - **1D fuelling-block decode (2026-08-22, candidate).** From the night drive + the
    Nanocom fuelling-page field ORDER (Ambient, Manifold, EGR Modulator, EGR Inlet,
    Wastegate — three modulators consecutive): **1D@15 = EGR modulator %**, **1D@16 = EGR
    inlet %**, **1D@17 = wastegate modulator %** (all `u8 × 100/255`), plus **1D@4 = a 2nd
    MAP reading** (r=0.995 vs manifold). @15 high-idle→0-load (textbook EGR); @17 follows
    boost (r=0.85) but is not MAP, scaled ~6%→32% = the published band (0 idle / 20-40
    boost). @16 read 0 all drive (EGR inlet inactive → identity by order only). Scaling
    100/255 not yet cross-checked vs a factory tool. Written to the store as `kandidat`.
  - **Injector classification codes** (Injector 1-5, five-char each, a Settings-block read):
    the dashboard never polls the identifier/Settings blocks, so these are in NO raw log —
    needs a targeted read on the car.
- **ECU identification `1A xx`**: `1A 87` VIN · `1A 9A` ECU type · `1A 9B/9C` more IDs.
  (Read-only, easy to add — we don't read VIN today.)
- **Digital inputs / switches `21 1E` and `21 36`** (bitfields): brake, clutch,
  cruise, A/C request, transfer position. Ekaitza gives pin mapping (A33 transfer, B10/B16
  brake, B35 clutch, B15/B17/B11 cruise, B9/B23 A/C). We capture 1E in the raw log but
  **don't decode the bitfield** — a concrete mapping task.
- **`21 32` / `21 0E`** homologation/map variant (ASCII) · **`21 3D`** 14-byte status block.
- **`30 BE` wastegate modulator** (we have BD EGR but possibly not BE wastegate — check).

## Low reuse
- colinbourassa/libcomm14cux (Rover V8 14CUX) + memsgauge (MEMS 1.6): NOT KWP2000,
  only a K-line/FTDI wiring reference.
- Zi-x/OBD-KLINE: generic ISO14230, nothing Td5-specific.

## Attribution
Ekaitza's sniff logs = high trust (captured from a real Td5). SimonRafferty reads as
partly reconstructed and clashes with our car-verified LID scheme (MAF@1B etc.) →
lower trust; verify its `21 37/38` (EGR/wastegate position) against the car first.
