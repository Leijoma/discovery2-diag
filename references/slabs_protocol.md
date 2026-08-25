# Wabco SLABS — complete K-line protocol (sniffed from reference tool 1)

Captured 2026-08-07 via a passive ESP32 tap (RX-only, GPIO16) on pin 7, while a borrowed
**reference tool 1** ran the full function set. Raw log + markers:
`logs/session.log` (decoded with `tools/decode_session.py`). This is **proven from
real traffic**, not guessed.

> The raw capture files (`slabs_session_20260807` etc.) are kept **local-only** —
> gitignored under the `captures/` / `*.log` policy, since a full session may carry
> VIN/EKA. This document is the distilled, redacted evidence; the protocol facts below
> are what the captures showed.

## Basics
- **Address `0x29`, FAST init:** `81 29 F7 81 22` → response `C1 57 8F` (KWP2000, KW2=8F).
  ✅ **Init works since 2026-08-19** — see "The init pulse" below. That it previously
  took many attempts was OUR fault (TiniH ~32 ms instead of 25), not the module's.
- **Session:** unaddressed, length-prefixed frames `<len> <SID> <data…> <cs>`
  (checksum = byte sum & 0xFF), same style as the Td5 session.
- **Keepalive:** `01 3E` → `7E` (TesterPresent), ~1 s. **NOTE: bare `3E` without
  sub-byte** (frame `01 3e 3f`). `3E 01` gets no response and tears down the session.
- Requires **ignition ON** (ignition-fed module). Comms die >8–20 km/h.

### ⚠️ SLABS must be polled LIGHTLY (proven 2026-08-07)
The reference tool ran ~**1 Hz keepalive + occasional reads** — not continuous
block polling. Our driver must do the same:
- **Read few LIDs, rarely.** The dashboard's `SlabsDataSource.poll` reads only
  heights (`21 54`). An earlier store-driven block read of 5 LIDs + fault codes on
  **every** 0.5 s cycle (~7× the bus traffic) connected but **killed the session
  after ~15 s**.
- **The RATE matters as much as the number of LIDs (the car 2026-08-18).** Just reading
  `21 54` wasn't enough: with the server's 0.5 s cycle it became `3E` + `21 54` = **4
  frames/s**, whereas the reference tool ran ~1 Hz (keepalive `01 3e 3f` was every ~1048 ms
  in the sniff). The session died after 21 s (connected 20:54:28, dead 20:54:49).
  Traffic is therefore throttled on the **clock, not the poll cycle**: `_SLABS_BUS_PERIOD =
  1.0 s` and fault codes on their own cadence `_SLABS_FAULT_PERIOD = 30 s`. Extra polls
  return cached values without touching the bus.
### ⚠️ Init requires a SILENT PERIOD — not more attempts (measured 2026-08-18)
All reference tool sniffs were re-measured (`slabs_session_20260807`,
`td5_slabs_session_20260808`, `faultread-20260809-4`). The time with no traffic to
the module before each init attempt:

| silence before | result |
|---|---|
| (session start) | no response |
| 24.9 s · 26.5 s · 27.8 s · 28.0 s · 41.0 s · 51.5 s | **C1 every time** |
| 59.0 s | no response (exception) |

**The tool NEVER made a fast retry** — every successful init came on the
*first* attempt after tens of seconds of silence. So the module needs the silent
period to release its link, and every init we send during it resets the wait.
Hammering is actively harmful: that is exactly what kept us
out for ~2 min on 2026-08-18 (and the reading "several attempts is normal" in this
file was a misreading of the same sniff).

- **`establish`: `idle=0.3 s`, `attempts=3`, `retry_sleep=28 s`.** The long pause
  is probably no longer needed — it was introduced when init failed for
  timing reasons. Feel free to lower it and measure (`tools/slabs_probe.py --quiet 5` now
  hits on the first or second attempt).
- The car 2026-08-18 confirmed the other half: once connected, SLABS sat
  **stable for 2 min 25 s** with data (4 signals, no reconnect). The light
  poll holds — the problem was only getting in.
- **Shared K-line bus:** a `7F 81 10` (generalReject) on StartCommunication =
  a session is already open — **and it comes from ANOTHER module**. Proven in the
  sniff 2026-08-08 (`td5_slabs_session`, t=403982): TD5's keepalive `02 3e 01 41`
  2.9 s earlier, then SLABS answers `C1 57 8F` **and** TD5 `03 7f 81 10 13` to
  the same init — both in the same burst. The reference tool ignored the reject and used C1.
  Our tolerant init does the same (searches for C1 in the burst), so a reject in itself is not
  fatal; the problem is when SLABS doesn't answer at all. Common cause: a leftover **TD5 session**
  (StartDiagnosticSession + SecurityAccess) after a module switch.
  **Fixed in code:** `EcuSession.release()` = StopDiagnosticSession (`20` → `60`)
  + close, and it is called on module switch (`Td5DataSource.disconnect`,
  `_select`/`_set_mode` in the web server) and between modules in `faultscan`. Just
  `close()` isn't enough — the ECU holds the session until it times out on its own.
  Modules without a session (SLABS, Airbag) have `_has_session = False` → no-op.
  Still, don't run fault-watch which switches modules quickly.
- **StopCommunication `82` → `C2` (proven in the car 2026-08-18).** It was NOT enough
  to close the TD5 session. Two teardowns exist and they are different things:
  `20` ends a *diagnostic session* (Td5 only), `82` tears down the
  *communication link* that fast init established — and every module has one.
  Proof: a **brand-new process** with `--slabs` (no TD5 involved, SLABS as the
  first module ever in the process) got `7F 81 10` on the very first
  init attempt: `81 29 f7 81 22 03 7f 81 10 13`. So the link survives our
  process dying. Fix in code: `EcuSession.release()` sends `20` (if the module
  has a session) + **always `82`**, and `_establish` sends a best-effort `82`
  before *every* init attempt to tear down a leftover link.
  Error paths (empty read, dropped cable) now also go through `release()` — the log
  showed that those in particular left the link open and gave a ~90 s reconnect loop.

### `1A 8A` is the reference tool's FIRST message after C1
In every successful init in the sniffs, `C1 57 8F` is followed by `02 1a 8a a6` → `5a 8a …`
after ~170 ms, before keepalive and reads begin. We mirror it since
2026-08-19 and use the response as **acknowledgement that the session is alive**: the
tolerant init only looks for a `C1` in the burst and, in noise, can give a false
positive "session established" followed by zero reads (seen in the car 2026-08-18).
If the response is absent, establishment is not torn down — it is reported in the connection log, so
"up" can be distinguished from "thought we were up".

⚠️ Remaining deviation from the tool: we send `01 82 83` (StopCommunication)
before the first init attempt. The tool **never** sends `82` in any sniff — it
trusts the link to time out on its own. Our `82` solved TD5's generalReject
but is unvalidated against the car.

### P4 — inter-byte time when TRANSMITTING (measured, no signal yet)
First measurement with mixed order (32 attempts, 2026-08-19 16:03–16:07):
**P4 = 0 ms gave 1/17, P4 = 5 ms gave 2/15.** Too small to say anything —
the difference is well within chance. The hypothesis survives but is unconfirmed.


The muki01 reference sends **one byte at a time with 5 ms between**
(`writeRawData`: `K_Serial.write(b); delay(WRITE_DELAY)`), and the comment cites
ISO 14230-2's interval **5–20 ms** for P4. We have always sent the whole frame in a
single `write()` — at 10400 baud a 5-byte frame then takes ~5 ms instead of ~25 ms.

A strict ECU may refuse to parse a frame without a P4 gap. That is a better candidate
than the addressing mode for why the reference tool gets in on the first attempt while we
need several, and it also explains why TD5 (Lucas) works while SLABS
(Wabco) is finicky — different ECUs, different tolerance.

`KLine(write_gap=…)` and `EcuSession._write_gap` exist now, but **are not enabled
for any module** — test first with `tools/slabs_probe.py --write-gaps 0,5`, which
runs P4 = 0 and 5 ms as separate cells in the mixed matrix.

### 🔑 THE INIT PULSE was the whole problem (solved 2026-08-19)
Our TiniH — the high period between the low pulse and StartCommunication — was **~32 ms
instead of ISO's 25 ± 1**, for two reasons:

1. **The UART stop bit was not counted.** The low pulse is a `0x00` at ~360 baud;
   the frame ends with a stop bit that is HIGH (~2.8 ms) and `flush()` waits until
   it has been sent. TiniH had thus already begun.
2. **`time.sleep(25 ms)` overshoots.** Measured on macOS: 25.3–32.0 ms, median 29.1.

Fix: `fast_init_low()` returns the time the line has already been high, and `KLine`
waits with `_precise_wait()` (spinning clock) instead of `sleep` → measured
**25.00 ± 0.01 ms**.

| | Hit rate per init attempt |
|---|---|
| Before | 3/32 = **9 %** |
| After | 6/11 = **55 %**, and the dashboard connects on the FIRST attempt |

Fisher's exact test **p = 0.007**. Three of the hits came on `81 29 F7 81 22` —
the addressing mode was never the problem, and all hypotheses about voltage, engine status,
silent period and doors were dead ends.

**The lesson:** TD5 (Lucas) accepted our faulty pulse without complaint for months.
SLABS (Wabco) has a narrower tolerance window and exposed the bug. A module that
is "finicky" while another works does not mean the module is broken — it
can be us sitting on the edge of the spec.

⚠️ Still to measure: the **physical** edges. We only measure our software side; the time
from `write()` to the byte leaving the FT232 is not visible from Python. The ESP32 tap
can timestamp the edges if needed.

### W5 and P4 — implemented, not proven
- `KLine(init_idle=…)` gives guaranteed bus idle before the pulse (ISO: 300 ms). Off by
  default. The probe: `--init-idle 1000`.
- `KLine(write_gap=…)` gives P4, inter-byte time when transmitting (ISO 5–20 ms, muki01
  uses 5). Off by default. The 0-vs-5 ms measurement gave no signal — but it
  was done before the P4 wait became precise, so the figure actually measured 8–9 ms.

### Fast-init pulse's physical edges
The sniff is RX-only and only sees UART data — the electrical init pulse (how long
K-line is pulled low/high before `81 29 F7 81 22`) is not visible in any capture. Everything at
application level is therefore proven and implemented, while the pulse timing is
guessed from ISO 14230-2 (25 ms low + 25 ms high). That is also where our problem
sits: the reference tool gets in on the first attempt, we need several. An ESP32 in
master mode (see `hardware/README.md`) would give deterministic pulse timing unlike
the USB-KKL's OS-timed one.

### 🔑 The addressing mode: functional init (`C1 29 F1 81`) — unexploited lead
The reference tool initializes **physically** with tester address `0xF7` (`81 29 F7 81 22`),
and that is what we copied. But two independent sources point to a different mode:

| Source | Frame | SLABS |
|---|---|---|
| Our address hunt 2026-08-05, `func-f1` | `C1 29 F1 81 5c` | **`C1 57 8F`** ✅ |
| Our address hunt, `fast-f1` | `81 29 F1 81 1c` | silent |
| Our address hunt, `func-f7` | `C1 29 F7 81 62` | silent |
| muki01 (confirmed correct) | `C1 33 F1 81 66` | — (functional broadcast) |

**MEASURED IN THE CAR 2026-08-19, 8 controlled runs** (`tools/slabs_probe.py`,
one variant at a time with 30 s silence between, ack via `1A 8A`):

| Time | Battery | Engine | Outcome |
|---|---|---|---|
| 13:25 | 13.66 V | running | silent (all 4) |
| 13:28 | 12.11 V | off | HIT → functional/F7 |
| 13:32 | 11.89 V | off | silent |
| 13:36 | 11.83 V | off | silent |
| 13:38 | 13.71 V | running | HIT → functional/F1 |
| 13:42 | 13.77 V | running | HIT → functional/F7 |
| 13:46 | 13.80 V | running | HIT → **physical/F7** (first attempt) |
| 13:47 | 12.28 V | off | silent |

**Engine running: 3 hits of 4. Engine off: 1 of 4.**

**Per ATTEMPT (25 init attempts across 8 runs), which is the better statistic:**

| Engine | Hits | Rate |
|---|---|---|
| running | 3 of 10 | 30 % |
| off | 1 of 15 | 7 % |

**Fisher's exact test: p = 0.27 — not significant.** The difference looks large but
the material is too small to rule out chance. Simulation says it takes
~50 attempts per mode for an 80 % chance of reaching p < 0.05 if the true effect is
30 % vs 7 %.

Confidence: **CANDIDATE, not proven.** n=8 is too small, the ranges overlap
(hits 12.11–13.80 V, misses 11.83–13.66 V) and there are counterexamples in both
directions — 13:25 failed with the engine running, 13:28 succeeded with the engine off. What we
have is the strongest correlation we've measured, not an established cause. The mechanism
is wide open: it could be supply voltage, but just as easily that the module is awake
and levelling when the engine runs and goes to sleep when the car is parked.

**How it becomes proven:** ~50 attempts per mode (`tools/slabs_torture.py`, mixed
order with logged seed) in three power modes — engine running / ignition with charger /
ignition without charger. **The charger mode is the key:** it gives high voltage WITHOUT
the engine running and thus separates voltage from engine status. Preferably measure SLABS's own
supply on C0504 pin 1/2 at the same time; TD5's battery value is only a proxy for what the
module actually sees.

**The echo confirmed as an error source:** the five false `C1` reported 13:25–13:34
disappeared entirely after the echo fix — zero in the five runs after that.

**The addressing mode: functional looks better, but it isn't settled.**
All probe attempts 2026-08-19 where all variants were tried in the same time window:

| Variant | Frame | Hits |
|---|---|---|
| functional/F7 | `c1 29 f7 81 62` | 4/11 |
| functional/F1 | `c1 29 f1 81 5c` | 2/13 |
| physical/F7 | `81 29 f7 81 22` | 1/14 |
| physical/F1 | `81 29 f1 81 1c` | 0/7 |

Functional in total **6/24 (25 %)** vs physical **1/21 (5 %)** — Fisher's
exact test gives p = 0.10.

✅ **Resolved 2026-08-19 with mixed order:** when the variant order is randomized per
round, the difference disappears entirely — functional/F1 1/8, functional/F7 1/9,
physical/F7 1/7, physical/F1 0/8. So the addressing mode plays **no** role; the
earlier difference was the position effect below. Keep several variants only
because it gives several attempts.

🚨 **The numbers below are confounded with the attempt number.** The probe always ran
the variants in the same order, so the hit rate per position is IDENTICAL to that per
variant:

| Attempt no. | Hits | | Variant (always in this order) | Hits |
|---|---|---|---|---|
| 1 | 1/14 | | physical/F7 | 1/14 |
| 2 | 2/13 | | functional/F1 | 2/13 |
| 3 | 4/11 | | functional/F7 | 4/11 |
| 4 | 0/7 | | physical/F1 | 0/7 |

So there's no telling "functional is better" apart from "the second/third
attempt is better" — e.g. that the first init pulse wakes the module and the next
gets through. `tools/slabs_probe.py` therefore shuffles the variant order per round
(``--order shuffle``, seed logged). Only with mixed order can the question be
settled.

⚠️ **The trap we fell into:** a torture run was locked to only `physical/F7` and gave
0 hits over 50 attempts. It looked like the module had stopped answering entirely, but we had
just stopped sending the frames that used to work. Never lock the experiment to one
variant before the question is settled.

**Working rule (not an established truth): run the engine when you talk to SLABS.**
It gives the best odds in what we've measured, and it's the module's normal operating case.

⚠️ **The echo looks like a response in functional mode.** The frame itself starts on `0xC1`,
and half-duplex echoes everything we send. A naive search for `0xC1` in the burst finds
our own echo and reports a connection on an empty bus (`C1! c1 29 f1 81`).
`fast_init_tolerant` therefore skips the echo before searching — and the `1A 8A`
ack catches the rest.

**Stability looks solved:** three hold periods (2026-08-19 13:29, 13:40, 13:44)
gave 95/95, 95/95 and 71/71 successful reads at 1 Hz — zero dropped. It
is strong but still n=3, and all during the same afternoon.

`0xC1` = functional addressing mode (bits 7-6 = 11) instead of physical `0x81`.
The hunt got a response **only** in functional mode with `0xF1`, the same combination that
the muki01 reference uses. `Slabs._init_variants` therefore now alternates: odd
attempts physical/F7, even functional/F1. Test systematically with
`tools/slabs_probe.py`, which runs the whole matrix with silent periods between and
logs raw TX/RX.

## ReadEcuIdentification — `1A xx`
| Req | Response | Content |
|---|---|---|
| `1A 8A` | 28 bytes `00 37 44 60 44 03 10 ff 31 90 10 86 40 ff 06 29 …` | hardware/config ID |
| `1A 8B` | ASCII | **software modules:** `KRTE49B0 HDTE16A0 EBTE87A0 CDTE91A0 KWTP11A0` |
| `1A 8D` | ASCII | **VIN:** `SALLXXXXXXXXXXXXX` ✅ (confirms the decoding) |

## Fault codes
- **`21 11`** → 16-byte block = **LOGGED faults** (bit-per-fault). Before clear: bits set
  in byte 3 (`0x10`) + byte 10 (`0x10`) = **two faults = baseline's `020` RF sensor +
  `027` shuttle valve**. After clear: all `00`. ⇒ `21 11` IS the logged-fault block.
- **`21 47`** → 16-byte block = **CURRENT faults** (was `00` = none current now).
- **`14 FF FF`** → `54` = **ClearFaults** (safe write; reset `21 11`).
- Byte↔number mapping: 2 bits (byte3.bit4, byte10.bit4) = faults 020+027. More
  anchor points come from the "induce a known fault" technique.

## Live data — ReadDataByLocalIdentifier `21 xx`
Grouped by reference tool screen (values = examples):
- **SLS inputs:** `21 53`=`d2 d2 0f 0f` · `21 54`=`91 9c 0f 0f` (heights, changed live) ·
  `21 55`=`00 00 00 02` · `21 45`=`7f` · `21 46`=`78 76` · `21 49`=`00 00 01` ·
  `21 59`=`00 0f 0f 0f`
- **ABS inputs:** `21 43`=`7c 00 7c 00 7c 00 7c 00` (**4 wheel speeds**) ·
  `21 44`=`00 80 01 02 01 01 02 01 02 02 03 04 …` · `21 50`=`72 73 73 72`
  (**sensor voltages?**) · `21 57`=`06 0f 0f 0f` · `21 49`=`00 00 01`
- **ABS-SLS switch:** `21 42`=`82` · `21 48`=`94 61` · `21 56`=`01 0f 0f 0f` ·
  `21 58`=`32 0f 0f 0f`

## Actuators / tests — StartRoutine `31 xx` → response `71 xx 20`
**This is the write/control protocol.** All respond `71 <rid> 20`.
| Command | Function |
|---|---|
| `31 25 <p>` | **ABS pump relay** (`31 25 08 fa 5c`=on, `31 25 02 fa 56`) |
| `31 2F 28` | **SLS bleed valve** (exhaust valve) |
| `31 30 28` | **SLS compressor** |
| `31 31 0a` | **SLS buzzer** |
| `31 33 28` | **raise left** |
| `31 34 28` | **raise right** |
| `31 35 28` | **lower left** |
| `31 36 28` | **lower right** |
| `31 22 <sub> <p…>` | **ABS bleed + wheel tests** (12-byte param) |

**`31 22` subcommands** (the byte after `22` selects the circuit, then `<flags> c1 f4 …`):
| sub | function (from markers) |
|---|---|
| `04` | ABS power bleed (`31 22 04 00 49 c4 …`) |
| `11` | front left / module bleed step 1 (`31 22 11 0c c1 f4` = FL test; `…11 00 c0 7d 00 bb` = bleed) |
| `10` | front right (`31 22 10 03 c1 f4`) |
| `13` | rear left (`31 22 13 c0 c1 f4`) |
| `12` | rear right (`31 22 12 30 c1 f4`) |
| `14` | module bleed step 4 |
**The flag byte = a 2-bit mask per wheel (decoded 2026-08-07):** `03`=FR (bits 0–1),
`0c`=FL (bits 2–3), `30`=RR (bits 4–5), `c0`=RL (bits 6–7) — i.e. 2 bits (in/out valve)
per wheel in the order FR, FL, RR, RL. `sub` = `0x10 + wheel index` (FR=0…RL=3). `c1 f4`
constant (likely duration/timeout). Live data is also per-wheel: `21 43`=4
wheel speeds, `21 50`=4 sensor voltages → fits a wheel-oriented UI perfectly.

**NOTE — lamp tests missing cleanly:** the instrument-lamp tests (TC/ABS/HDC/brake/SLS lamps)
were only run in the FIRST session (baud clash → garbage). The bytes are unusable; the function
exists but must be **re-logged** (list the reference tool order at the same time, please).

## To build in d2diag (all the material exists now)
`Slabs(KWP2000(KLine(...)))`: establish() via fast init 0x29 → C1 57 8F; keepalive 3E;
`read_faults()` = `21 11`/`21 47` (bit-per-fault, map in `slabs_fault_codes.md`);
`clear_faults()` = `14 FF FF`; live via `21 xx`; actuators via `31 xx`. Reuse
the Td5 layer's tolerant read + the same session pattern.

## Input LIDs (sniffed 2026-08-08, full per-input sweep)
The reference tool polls a fixed LID set per screen; the operator stepped through
the entries. All input LIDs are now identified (offset/scale per entry still to be isolated
with targeted captures):

| Screen | LIDs | Entries |
|---|---|---|
| SLS inputs | `21 53`, `21 54`, `21 55` | L/R sensor value (**`21 54` b0/b1 decoded**), sensor supply, value (V), exhaust valve (V), compressor relay (V) |
| ABS inputs | `21 43`, `21 44`, `21 49`, `21 50`, `21 57` | wheel speed (`21 43`), ABS sensor V (`21 50`), inlet/outlet valves, pump relay/monitor, battery, ECU supply, ground ref, HDC brake, engine speed/torque/throttle (via CAN) |
| Switches | `21 42`, `21 48`, `21 56`, `21 58` | neutral, low range, diff lock, reverse, HDC, shuttle, **any-door (`21 56` byte0 bit0 — PROVEN: 00 closed/01 open)**, plip |
| Settings | `21 45`, `21 46`, `21 49`, `21 59` | **Stable raw bytes proven (RDL 016):** `45`=`7f`, `46`=`78 76`, `49`=`00 00 01`, `59`=`00 0f 0f 0f`. ⚠️ **LID→setting UNSOLVED** — two order-based labelings contradict each other (card order unstable). Solve with DIFFERENTIAL: change ONE setting → see which raw byte changes. |

## Byte variance from session.log (`analyze_capture.py --variance`)
Which bytes **moved** during the capture = ready-made differential candidates. Narrows
down what should be correlated against reference tool values:

| LID | Byte structure (proven from variance) |
|---|---|
| `21 54` | **byte0 = left height, byte1 = right height** (both vary = live). Confirmed. |
| `21 50` | 4 bytes, **one ABS sensor voltage per wheel** (~`0x72`); byte1/2 varied (two wheels). |
| `21 43` | constant `7c 00 ×4` stationary = wheel-speed **baseline** (≠0). |
| `21 53` | byte0 ~`d1/d2` varies (supply candidate); byte1 const, byte2/3 = `0f 0f`. |
| `21 55` | byte3 varies (small value 00/02/03); the rest `00`. |
| `21 57` | byte0 varies (`05/06/08`); the rest `0f 0f 0f`. |
| `21 44` | **rich block** — offsets 2,3,4,6,8–13 vary (valves/pump/battery/supply). Requires labels. |
| `21 49` | constant `00 00 01`. |

**TD5 switches (session.log):** `21 1E` byte1 = switch bitfield (toggled `CA`→`EA`
= bit `0x20`; byte0 const); `21 36` constant `00 0D` (fixed switches). So we know
*which byte* but not *which switch* — requires an annotated toggle.

## Field identity from reference tool screen reading 2026-08 (structure proven, scale candidate)
Values read off the screen, correlated against old raw bytes (not the same
moment → scale = candidate). **Structure (which LID = which screen section) is proven** via
display order + value range:

| LID | Field | Candidate |
|---|---|---|
| `21 43` | **4× wheel speed** (2 bytes/wheel) | stationary `7c 00` = 1.7 km/h (baseline) |
| `21 50` | **4× ABS sensor voltage** (1 byte/wheel) | FR byte0 `0x72`=114 → 2.17 V (≈×0.019); FL blank in reference tool |
| `21 44` | **large analog block (14 bytes):** 8 valve voltages + pump relay/monitor + battery + ECU supply | valves `0x01–03`→ ×0.01 V (0.01–0.03); **byte12/13 = battery/ECU supply** (~`0xb3/b1`→ ×1/16 ≈ 11.3–11.5 V; VARIES = matches) |
| `21 53` | **L/R sensor supply** (byte0/1) | `0xd1`=209 → ~5 V (≈×0.024); byte2/3 `0f 0f` |
| `21 54` | **L/R height** (byte0=left, byte1=right) | **proven** (149/162) |
| `21 55` | compressor relay | byte3 `0x02` → 0.13 V (candidate) |
| `21 49`/`21 57` | CAN-derived: engine speed (noise 195–235 engine off), torque, throttle | throttle 0–86 on throttle application |

⚠️ **The exact byte↔valve order and scales require ONE fresh sniff capture** (raw +
reference tool value at the same moment) of the ABS/SLS inputs screens. Without it this is
the ceiling. Battery/ECU supply (21 44 byte12/13) is strongest — they vary and match.

**Next step for full decoding:** targeted differential captures — change ONE thing
(open a switch, lift a corner, measure a voltage) and compare the raw bytes before/after.
Run `analyze_capture.py --variance <log>` for the candidates directly.

### ABS bleed — complete frames (proven from the sniff 2026-08-07, coded)
Two procedures under `31 22`, distinct from the wheel-valve test (`31 22 <sub> <mask> c1 f4`):

| Command | Frame (data after `31 22`) | Code |
|---|---|---|
| Power bleed START | `04 00 49 c4` + 8×00 | `Slabs.abs_power_bleed(True)` |
| Power bleed STOP | `04 00 40 00` + 8×00 | `Slabs.abs_power_bleed(False)` |
| Module bleed step 1 | `11 00 c0 7d 00 bb` + 6×00 | `abs_module_bleed_step(1)` |
| Module bleed step 2 | `12 00 c0 7d 00 bb` + 6×00 | `abs_module_bleed_step(2)` |
| Module bleed step 3 | `13 00 c0 7d 00 bb` + 6×00 | `abs_module_bleed_step(3)` |
| Module bleed step 4 | `14 00 c0 7d 00 bb` + 6×00 | `abs_module_bleed_step(4)` |

`abs_module_bleed()` runs all four in sequence with ~2.3 s between (the reference tool's
cadence). All respond `71 22 20`. ⚠️ Brake system — stationary only, ignition on.
