# SLABS connection: problem brief for external review

_Written 2026-08-19. Standalone — assumes no knowledge of our codebase._

## Setup

- Car: Land Rover Discovery 2 Td5 (2000), reg RDL 016. Diagnostics over **K-line**
  (ISO 14230 / KWP2000) on OBD pin 7. No CAN.
- Interface: generic **USB-KKL 409.1** (FTDI FT232), macOS, `/dev/cu.usbserial-*`,
  10400 baud 8N1. pyserial + our own protocol stack in Python.
- Modules on the same bus: TD5 engine ECU (Lucas, physical address `0x13`), **SLABS**
  (Wabco ABS + self-levelling air suspension, `0x29`), airbag (`0x5B`), and others.
- Reference material: passive sniffs (ESP32, RX-only on pin 7) of a commercial
  tool running the full function set against the car.

## ✅ SOLVED 2026-08-19 at 17:26 — the cause was our own init pulse

This document was written while the problem was open. It stands as documentation of
the troubleshooting, but **the cause has been found and fixed**:

Our TiniH (the high period between the low pulse and StartCommunication) was **~32 ms
instead of 25 ± 1**, for two reasons: the UART stop bit after the pulse byte (~2.8 ms)
was not counted, and `time.sleep(25 ms)` overshoots to 25.3–32.0 ms (median 29.1)
on macOS. With the stop bit subtracted and a spinning wait instead of `sleep`:

| | Hit rate per init attempt |
|---|---|
| Before (TiniH ~32 ms) | 3/32 = **9 %** |
| After (TiniH 25.00 ± 0.01 ms) | 6/11 = **55 %** |

Fisher's exact test: **p = 0.007**. Five runs in a row hit, each time on the
first or second attempt — and three of them on `81 29 F7 81 22`, i.e. exactly
the frame we'd been using all along. **The addressing mode was never the problem.**

The conclusion is the hypothesis proposed during review: a Wabco module has a
narrower tolerance window for fast-init timing than the TD5's Lucas ECU, which
accepted our faulty pulse without complaint.

## The problem as it appeared (history)

**TD5 connects on the first attempt basically every time. SLABS answers on
about 1 in 10 init attempts — but once it does answer, the session is perfectly stable.**

## What is proven

**The application layer is solved and verified against the car.**

| Item | Value |
|---|---|
| StartCommunication (physical) | `81 29 F7 81 22` |
| Response | `03 C1 57 8F AA` (len, C1 = 0x81+0x40, KW1, KW2, checksum) |
| Session frames | `<len> <SID> <data…> <cs>`, unaddressed |
| Checksum | sum of preceding bytes & 0xFF |
| Positive response | SID + 0x40 |
| First request after C1 | `02 1A 8A A6` → `5A 8A …` (the tool always does this) |
| Keepalive | `01 3E 3F` → `01 7E 7F`, ~1 Hz. **Bare 3E — `3E 01` tears down the session** |
| Fault codes | `21 11` logged / `21 47` current, 16-byte bit block |
| Live data | `21 54` = height left/right in byte 0/1 |
| StopCommunication | `01 82 83` → `01 C2 C3` |

**Stability after connecting:** three hold periods of 2 minutes at 1 Hz gave 95/95,
95/95 and 71/71 successful reads — zero dropped. One session was held 5 min 31 s
and was ended only because we switched modules. So the module is not broken.

**Known requirements:** ignition on; comms die above 8–20 km/h (confirmed — attempts
while driving are always silent).

## What we have measured and REJECTED as an explanation

All figures are from controlled runs on 2026-08-19 with randomized order.

| Hypothesis | Measurement | Conclusion |
|---|---|---|
| **Addressing mode** (physical `81` vs functional `C1`, testing F7 vs F1) | with randomized order: functional/F1 1/8, functional/F7 1/9, physical/F7 1/7, physical/F1 0/8 | **No effect.** An earlier "effect" (6/24 vs 1/21) turned out to be confounded with the attempt number — fixed order in the matrix. |
| **P4, inter-byte time when transmitting** (0 ms vs 5 ms per ISO 14230-2 and the muki01 reference) | 0 ms: 1/17 · 5 ms: 2/15 | No signal, but n is small. The hypothesis survives weakly. |
| **Silent period before init** (5 s vs 10 s vs 30 s) | looked significant (p=0.017) but was fully confounded with time of day | **Rejected as evidence.** Hits have since come after 5 s of silence. |
| **Engine running vs off** | running 3/10, off 1/15 — Fisher's exact p = 0.27 | Tendency, not significant. Later runs with the engine running gave 0/20. |
| **Battery voltage** | hits 12.11–13.91 V, misses 11.83–13.80 V | No threshold, the ranges overlap completely. |
| **Leftover session from another module** | `7F 81 10` (generalReject) occurred, came from TD5 in an open session | **Fixed** — we send `82` StopCommunication at teardown and before init. The rejects have been gone since. |
| **Door open/closed** | 0 hits over 2 runs with the door open | Too small for a conclusion. |
| **Cable/bus/our code** | TD5 connects on the first attempt seconds before and after each failed SLABS attempt, on the same cable | Basic K-line hardware and session code **work**, verified against TD5. But **module-dependent tolerance for fast-init timing is still open** — TD5 (Lucas) may well have a wider window than SLABS (Wabco). That is the hypothesis that best fits the observation. |

**Remaining pattern:** the hits cluster in time. A window 13:29–13:47 gave
4 hits; after that, 54 straight silent attempts over 86 minutes under all conditions.
We have no variable that explains when the windows open.

## The known gap: the init pulse's electrical timing

The sniffs are **RX-only** and only see UART data. The electrical wake pulse
before `81 29 F7 81 22` is therefore in no capture — we don't know how the
commercial tool times it.

ISO 14230-2 fast init: bus silent ≥ 300 ms (W5) → K-line **low 25 ms ± 1** (TiniL)
→ **high 25 ms ± 1** → StartCommunication immediately.

**Our implementation — and two bugs found 2026-08-19 during external review:**

- The low pulse is hardware-timed: we drop the baud rate to ~360 and send a `0x00`
  (start bit + 8 zeros = 9 low bits ≈ 25 ms). Governed by the UART's bit clock.
- 🐛 **The stop bit was forgotten.** The UART frame ends with a stop bit that is HIGH —
  at 360 baud ≈ 2.8 ms — and `flush()` waits until it has been sent. TiniH had thus
  already begun before our wait started.
- 🐛 **`time.sleep(0.025)` overshoots badly.** Measured on the machine in question:
  `sleep(25 ms)` actually takes **25.3–32.0 ms, median 29.1**.

  Sum: real TiniH was ≈ **32 ms** where ISO specifies **25 ± 1**.

  **Fixed:** the stop bit's length is now subtracted, and the wait is done with a
  spinning clock instead of `sleep` → measured **25.00 ± 0.01 ms** in our code.
- **W5 was missing entirely** (no guaranteed bus idle before the pulse). Now implemented
  as `init_idle`, off by default, and intended to run at 0.3–1.0 s.

⚠️ **Still unmeasured:** we can only measure our own software side. The time from
`write()` returning until the byte physically leaves the FT232 — USB scheduling and
driver — is not visible from Python. The actual electrical edges are still
unknown.

**Idea to measure them:** we already have an ESP32 with an RX-only tap on K-line. It
can timestamp the edges (falling → rising → start bit) and thereby measure what our
USB-KKL actually produces — without having to rebuild it into a transmitter.

Comparison: the same ESP32 can also bit-bang the pulse itself (300 ms idle, 25 ms low,
25 ms high, then UART) with microsecond accuracy and no USB buffer in between.
That sketch already exists and transmits to TD5; retargeting it to `0x29` is a
constant change.

## Questions we'd like help with

1. **Is the USB-KKL's timing a likely explanation** for a Wabco module rejecting
   init while a Lucas ECU on the same bus accepts it? Is the TiniH window known
   to be tight on Wabco?
2. **W5** — how strict is the 300 ms bus-idle requirement before fast init in practice,
   and can a module end up in a state where it requires substantially longer?
3. Is there **documented SLABS/Wabco-specific init behaviour** (e.g. the module
   listening only in certain windows, requiring an ignition cycle, or going to sleep when
   the vehicle is parked)?
4. **The time clustering** — 4 hits in 18 minutes, then 0 over 86 minutes under
   identical conditions. What mechanism in an ABS/SLS ECU would produce that?
5. Is it worth going to **ESP32 in master mode** for a deterministic pulse, or is
   there more to gain on the USB side first?

_Note: an earlier version of this document claimed that FTDI's latency timer
(16 ms) adds delay on the transmit side. That is wrong — it governs how quickly
RECEIVED data is flushed from the chip's buffer to the host. Pointed out and struck._

## What we are NOT asking help with

The application layer above `C1` — that is solved, verified and stable. The question
concerns only getting in.
