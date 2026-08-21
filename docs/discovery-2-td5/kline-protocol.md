# The Shared K-line / KWP2000 Layer

This is the common transport-and-protocol foundation every Discovery 2 module in
this project sits on: the physical K-line, the init handshakes that wake an ECU,
the two KWP2000 frame formats, and the KWP2000 services and teardown rules shared
across Td5, SLABS, BCU, ACE, EAT and Airbag. Module-specific identifiers, scaling
and security live in the per-module docs; everything here is what they have in
common.

The stack is strictly bottom-up — each layer knows only the interface of the one
below it:

```
Transport   raw bytes in/out (SerialTransport, LoggingTransport)
K-line      frame encode/decode + fast/slow init, echo, retries, tolerant reads
KWP2000     service IDs, negative responses (0x7F + NRC), responsePending (0x78)
EcuSession  lifecycle, keepalive, establish-retry, clean teardown
Module      td5 / slabs / bcu / airbag / ace / eat
```

## Confidence legend

| Tag | Meaning |
|---|---|
| 🟢 **Proven** | Sent against a real vehicle and confirmed. Car, date and method cited. |
| 🟡 **Assumed** | Derived, transcribed, or matched to a published spec/range but not confirmed on our car. |
| 🔴 **Unknown** | An open question we can see but cannot yet interpret. |

The reference vehicle throughout is **RDL 016**, a Discovery 2 Td5 (ES, ZF4HP22/24).
"Sniff" means a passive RX-only ESP32 on K-line pin 7 recording while a factory-grade
tool (a borrowed reference tool) drove the bus.

---

## 1. Physical layer

| Fact | Value | Confidence |
|---|---|---|
| Bit rate | 10 400 baud | 🟢 the working rate against every module; `DEFAULT_BAUDRATE = 10400` |
| Framing | 8 data bits, no parity, 1 stop bit (8N1) | 🟢 |
| Wire | Single shared, **half-duplex** K-line (pin 7 at the OBD connector) | 🟢 |
| Cable | Cheap **KKL 409.1 USB** adapter (FTDI-based) | 🟢 this is the hardware the whole project runs on |

K-line is one wire that both sides drive, so **every byte the tester sends is echoed
back** on the same line and must be read and discarded before the ECU's reply. The
K-line layer consumes this echo automatically (`KLine.request` reads the first valid
frame as the echo, the next as the response).

Because it is a single shared bus, only one module can be spoken to at a time. The
fault-scan reads modules strictly one after another: establish → read → release,
never overlapping.

> **macOS gotcha (🟢):** always open `/dev/cu.*`, never `/dev/tty.*`. The `tty`
> device blocks on DCD and will hang. `resolve_serial_port("auto")` handles this.

The `SerialTransport` keeps the byte interface (`send`/`receive`) clean and exposes
the serial-specific hooks (`baudrate`, `send_break`, `fast_init_low`, `slow_init`,
`reset_input_buffer`) that only the K-line layer is allowed to touch. A
`LoggingTransport` can wrap any transport transparently and record all raw TX/RX to
a timestamped file:

```
2026-07-21T12:00:00.123456Z TX 81 13 F7 81 0C
2026-07-21T12:00:00.234567Z RX 83 F7 13 C1 EA 8F
```

(On the in-car Raspberry Pi the log is `fsync`ed to the SD card every ~2 s rather
than per line, to survive an abrupt power cut when the engine is switched off
without hammering the card.)

---

## 2. Fast init (ISO 14230-2)

The Td5 engine ECU and SLABS are woken with a **fast init**: a fixed wake-up pulse
on the line, immediately followed by a `StartCommunication` request.

### The pulse

| Phase | Nominal | Confidence |
|---|---|---|
| TiniL — line **low** | 25 ms ± 1 | 🟡 from ISO 14230-2; matches muki01 (`delay(25)`) and Ekaitza |
| TiniH — line **high** | 25 ms ± 1 | 🟡 same sources |
| then | send `StartCommunication` | 🟢 |

The 25 ms + 25 ms figure is confirmed by two independent open references
(muki01/OBD2_K-line, MIT; Ekaitza_Itzali sniff logs) and produces a working init
against the real car, but the exact millisecond bounds are the ISO spec's, not
something we measured the ECU's tolerance of — hence 🟡 on the numbers, 🟢 that a
25/25 pulse wakes the car.

Timing this pulse on a non-realtime OS over USB is the hard part. Two problems:

1. **`time.sleep()` overshoots.** Measured on macOS, `sleep(25 ms)` actually
   returns after 25.3–32.0 ms (median ~29). So the *high* period is produced by
   sleeping to ~2 ms short of the target and then spin-waiting the rest
   (`_precise_wait`). 🟢 (measured)
2. **The low pulse must be deterministic.** An OS-timed UART break jitters with the
   scheduler; when it comes out too short the Td5 never enters diagnostic mode and
   answers `7F 81 10` (generalReject). So the low pulse is produced by a hardware
   trick where possible — **see the platform split below.**

### The macOS baud-360 trick vs the Linux `send_break` fix 🟢

`fast_init_low` needs to hold the line low for 25 ms. It does this differently per
platform, and getting this wrong was a **real bug fixed 2026-08-21**:

- **macOS (and `loop://` tests):** drop the port to ~360 baud and send a single
  `0x00` byte. A start bit plus 8 zero data bits = 9 low bits in a row; at 360 baud
  that is ~25 ms. The pulse length is set by the UART's bit clock (hardware), not by
  the OS scheduler, so it is stable even over USB. The trailing stop bit is high, so
  `fast_init_low` returns how long the line has *already* been high (~2.8 ms at
  360 baud plus baud-restore/buffer-flush cost) and the caller subtracts that from
  TiniH so the high period isn't systematically too long.

- **Linux (Raspberry Pi):** **the baud trick does not work.** FTDI on Linux
  (`ftdi_sio`) cannot actually do a baud rate as low as 360 — the kernel clamps it,
  so the `0x00` byte goes out at ~4500 baud and the low pulse is only **~2 ms
  instead of 25 ms → the ECU never wakes.** Measured in the car 2026-08-21: the baud
  trick gave `low_ms` 1.9–2.8 and **never** produced a C1; the OS-timed
  `send_break` gave `low_ms` 26 ms and C1 **on the first try.** So on Linux the code
  falls back to `send_break` (a real UART break condition held for the duration),
  which returns 0 high-time to compensate because a break is pure low time with no
  stop bit.

This platform split is why the same code can wake the car on the in-car Pi and on a
laptop, using two different mechanisms for the identical 25 ms pulse.

The actual pulse is always measured, not assumed: `KLine.last_pulse` records the
real `low_ms` / `high_ms` / `pre_high_ms` for every attempt, because the nominal
values say nothing about what a USB serial stack actually did.

### The StartCommunication response

| Message | Bytes | Confidence |
|---|---|---|
| Request (addressed) | `81 13 F7 81 0C` — StartCommunication `0x81` to ECU `0x13` from tester `0xF7` | 🟢 |
| Positive response | starts with **`0xC1`** (= `0x81 + 0x40`), followed by two key bytes | 🟢 |
| Td5 response | `C1 57 8F` | 🟢 (RDL016) |
| SLABS response | `C1 57 8F` | 🟢 (RDL016) |

`0xC1` is the universal "communication started" marker — muki01 checks the same
`resultBuffer[3] == 0xC1` on generic OBD-II, and we saw it against the Td5.

### Echo handling and tolerant reads

Cheap KKL cables + a non-realtime OS produce turnaround glitches: a stray byte
(e.g. `0xF8` / `0x00`) can slip in at the TX→RX turnaround, and FTDI latency jitter
during init can shred an otherwise valid frame's checksum. Two mechanisms cope:

- **`fast_init` (strict):** sends `StartCommunication` **once** and reads a valid
  frame. StartCommunication must never be retried — a second one is rejected as
  "already in session" (generalReject). 🟢
- **`fast_init_tolerant` / tolerant reads:** read the *whole* response burst raw
  (until ~60 ms of silence) and **search it for `0xC1`** instead of demanding a
  checksum-clean frame. A noise-damaged C1 frame (e.g. `03 c1 38 0e f8 00`) still
  *contains* `0xC1`, so we register "session open" on the first try and avoid the
  re-init loop that would otherwise re-open the session repeatedly and lock the ECU.
  The tolerant reader carefully **skips the echo first** before searching, because a
  *functional* request frame itself begins `0xC1` — without skipping, the search
  finds our own echo and falsely reports a session on an empty bus (seen in the car
  2026-08-19). 🟢

Keeping `tolerant=True` on KWP2000 for these cables is a hard rule — it is what
compensates for FTDI latency jitter during fast init.

---

## 3. Frame formats

Two KWP2000 frame formats are used, distinguished by the top two bits of the first
byte (the *format byte*). `read_frame` sniffs the format byte, so both work
transparently on the same session.

Format byte: bits 7–6 = address mode, bits 5–0 = length (0 → length is in a
separate following byte).

| Mode bits | Meaning | Header shape |
|---|---|---|
| `00` | no address (unaddressed) | `<len> …` |
| `10` | physical addressing | `<8n> <target> <source> …` |
| `11` | functional addressing | `<Cn> <target> <source> …` |

### Addressed (fast init / StartCommunication only)

Used **only** for StartCommunication / fast init. Carries a target and source
address:

```
81 13 F7 81 0C
8n Tgt Src data cs        (0x81 = mode 10 | length 1)
```

Physical addressing uses `0x8n`; **functional** addressing uses `0xCn`. The
functional variant (`C1 …`, source `0xF1`) is what the muki01 reference uses, and
was the **only** mode SLABS answered during our address hunt on 2026-08-05
(`C1 29 F1 81 5c` → `C1 57 8F`, while physical init to the same address was silent). 🟢

### Unaddressed (the whole session after init)

After the link is up, Td5 and SLABS switch to **unaddressed** length-prefixed
frames for everything — no target/source, just length:

```
02 10 A0 B2      02 27 01 2A      02 21 1D …
└len SID data cs┘
```

`EcuSession.read_block()` is deliberately the exact `{lid_hex: bytes}` shape the
differential mapper (`sniff/automap.py`) consumes, which is what lets a live session
feed the mapper directly.

### The Airbag exception 🟢

Airbag/SRS (TRW SPS 2A) does **not** switch to unaddressed session frames. It uses
**addressed framing on every message**, at address **`0x5B`**. Proven from
`faultread-20260809.log` line 885:

```
82 5b f7 21 02 …  →  f7 5b 61 02 90 04 90 16 00 00 …
```

The KWP2000 layer supports this with an `addressed=True` flag that prepends
format/target/source to *every* request, not just init.

---

## 4. Checksum

Every frame ends with a one-byte checksum:

> **checksum = 8-bit sum of all preceding bytes, including the length byte, mod 256.**

🟢 Confirmed against the Ekaitza sniff captures and independently validated by our
own capture parser (`tools/analyze_capture.py`) and the BCU write frames. This holds
for both frame formats — the sum runs over the entire frame up to (not including)
the checksum byte itself.

```python
checksum(b"\x02\x10\xA0") == (0x02 + 0x10 + 0xA0) & 0xFF == 0xB2
```

The frame reader is tolerant of leading junk: rather than trusting the first byte as
a format byte, it scans the receive buffer for the **first frame with a valid
checksum**, which discards turnaround glitch bytes, and keeps any trailing bytes
(e.g. a following responsePending reply) for the next read.

---

## 5. Slow init (5-baud) — BCU

The BCU (Valeo body control unit) is not woken with a fast init. It uses the classic
**ISO 9141 / ISO 14230 5-baud slow init**:

| Step | Detail | Confidence |
|---|---|---|
| Address | `0x40` | 🟢 confirmed BCU in car 2026-08-20 (previously a candidate from the 2026-08-05 address hunt) |
| Address transmission | bit-banged on the break condition at **200 ms/bit** (5 baud): start bit (0), 8 data bits **LSB-first**, stop bit (1), 8N1 | 🟢 |
| ECU sync | ECU replies `0x55` at the normal baud, then two key bytes | 🟢 |
| Key bytes (KW1 KW2) | **`E5 8F`** | 🟢 (KW2 `0x8F` = KWP2000, same low key byte as the engine's `57 8F`) |
| Handshake completion | wait W4 (~30 ms), send `~KW2` (inverted), read `~address` (`0xBF`) confirmation | 🟢 |

`parse_slow_init` pulls (KW1, KW2) from a response that begins `0x55`; no leading
`0x55` means no module answered that address. (Note: the address-byte bit builder
was fixed 2026-08-04 — an earlier 7-bit + mis-computed-parity version produced the
wrong byte for addresses with an odd number of set bits, which would have made a
slow-init address scan miss exactly the interesting candidates. `0x40` happened to
come out right and hid the bug.)

The BCU also requires **ignition cycling** to attach in the factory tool
(off → key → on → key); that is a module quirk documented with the BCU, not a
K-line-layer rule.

---

## 6. KWP2000 services

The KWP2000 layer knows service IDs, positive/negative responses and
responsePending, but nothing about any module's identifiers or scaling. A positive
response echoes the request SID **OR'd with `0x40`**.

| SID | Service | Positive resp | Used for | Confidence |
|---|---|---|---|---|
| `0x10` | StartDiagnosticSession | `0x50` | Td5 enters a diagnostic session (`10 A0` → `50`) | 🟢 |
| `0x27` | SecurityAccess | `0x67` | Td5 seed→key unlock (`27 01` seed → `67`, `27 02` key → `67`) | 🟢 |
| `0x21` | ReadDataByLocalIdentifier | `0x61` | the workhorse — read live data / faults (`21 xx`) | 🟢 |
| `0x31` | StartRoutineByLocalIdentifier | `0x71` | start a routine (e.g. injector / security routines) | 🟢 |
| `0x33` | RequestRoutineResultsByLocalIdentifier | `0x73` | read a routine's result | 🟢 |
| `0x30` | InputOutputControlByLocalIdentifier | `0x70` | actuator/output tests (`30 xx FF`) | 🟢 |
| `0x1A` | ReadEcuIdentification | `0x5A` | ECU ID / VIN (`1A 87` etc.) | 🟡 seen in captures; not yet a stack method |
| `0x3E` | TesterPresent | `0x7E` | keepalive | 🟢 |
| `0x20` | StopDiagnosticSession | `0x60` | end a diagnostic session (Td5) | 🟢 |
| `0x82` | StopCommunication | `0xC2` | tear down the communication link (all modules) | 🟢 |

**Negative response:** `7F <SID> <NRC>`. The layer raises `NegativeResponse` with
the decoded name. NRCs handled by name:

| NRC | Name |
|---|---|
| `0x10` | generalReject |
| `0x11` | serviceNotSupported |
| `0x12` | subFunctionNotSupported |
| `0x22` | conditionsNotCorrect |
| `0x31` | requestOutOfRange |
| `0x33` | securityAccessDenied |
| `0x35` | invalidKey |
| `0x36` | exceedNumberOfAttempts |
| `0x78` | **responsePending** |

**responsePending (`0x78`) 🟢:** a `7F <SID> 78` means "working on it, wait" — the
layer **waits for the next frame without resending** (up to a bounded number of
pending replies, default 6), then continues. Resending here would double-issue the
request.

**Tolerant service reads 🟢:** with `tolerant=True` (the setting for cheap cables),
each request reads the whole burst and searches it for a positive SID
(`service | 0x40`) or a negative `7F <service>`, preferring a two-byte match
(`61 <lid>`, `67 <level>`) for precision. The echo doesn't interfere because its SID
is the *request* value, not `service | 0x40`.

---

## 7. Session lifecycle: establish, keepalive, teardown

`EcuSession` is where the module layers share behaviour. A subclass sets `name` and
calls `_establish(after=…)`:

- **Td5:** `after=self.connect` — after init it runs StartDiagnosticSession and the
  SecurityAccess seed→key unlock. Has a session to close (`_has_session = True`).
- **SLABS:** `after=None` — no session, no unlock; services work immediately after
  fast init. `_has_session = False`.

### Keepalive timing

`tester_present()` (`3E` → `7E`) keeps a session alive between requests, within a
roughly **~2 s** window before the ECU times the link out. Two important details:

- **SLABS needs a bare `3E`** (no sub-function byte): the sniffed frame is
  `01 3e 3f` → `01 7e 7f`. A `3E 01` **kills its session.** SLABS overrides the
  keepalive sub-function to `None` for exactly this. 🟢
- Td5 and the others use the standard `3E 01`. 🟢

**SLABS must be polled lightly (🟢):** ~1 Hz keepalive plus a *few* reads. Block-
reading many LIDs every 0.5 s cycle killed the session after ~15 s. The dashboard's
SLABS source reads only the heights (`21 54`) per cycle and faults at most every
10th poll, and rotates the wider input block one LID per cycle to stay near 1 Hz.

### Teardown — the hard-won rules 🟢

These only bite against the real shared bus, and getting them wrong produces a bug
that outlives the process:

> **A `7F 81 10` (generalReject) on StartCommunication means a link is still open on
> the bus.**

There are **two** teardowns and both matter:

| Teardown | SID | Ends | Applies to |
|---|---|---|---|
| StopDiagnosticSession | `0x20` | a *diagnostic session* | Td5 only |
| StopCommunication | `0x82` | the *communication link* fast init created | **every** module |

Fast init opens a communication link even for modules with no diagnostic session
(SLABS). If you only close the serial port, that link **lives on inside the ECU**,
and the next StartCommunication — even from a completely fresh process — is met with
`7F 81 10` until the module's own timeout expires. **Proven in the car 2026-08-18:**
a fresh process, SLABS as the very first module talked to, got generalReject on the
first attempt because a previous run had died with the link open. The log shows the
pattern: three empty polls → `close()` without an `82` → every following init
rejected for ~90 s.

Therefore:

- **Always end a module with `EcuSession.release()`** — on module switch **and** on
  error paths — never a bare `close()`. `release()` = `end_session()` (best-effort
  `20` if there's a session, then always `82`) + `close()`.
- `_establish` sends a **best-effort `82` once before every init attempt**, to clear
  a stale link left by a previous run, *before* the quiet period — not between
  retries.

> **The quiet period is not a politeness pause.** Across every factory-tool sniff
> (2026-08-07/08/09), each successful SLABS init came on the **first** attempt after
> **25–28 s of no traffic to the module**, and the tool never made a fast retry.
> Sending *anything at all* during the wait — including an `82` — **resets the
> wait.** So `_establish` clears the link once, then goes silent; it does not try to
> fix a stuck link with a shorter idle or more frames. 🟢

---

## Provenance

Protocol *facts* learned from other open projects are credited; no code was copied.
- **muki01/OBD2_K-line** (MIT): 25 ms/25 ms fast init pulse, `0xC1` positive marker,
  permissive burst reading, 5-baud slow init.
- **Ekaitza_Itzali** (EA2EGA): real Td5 sniff logs confirming the checksum rule, the
  fast-init timing, Td5 addressing (`0x13` / tester `0xF7`) and identifiers.
- Timing measurements, the Linux/macOS platform split, the teardown behaviour and
  every 🟢 tag here were verified against RDL 016 on the dates cited.
