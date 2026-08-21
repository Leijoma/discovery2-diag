# Valeo BCU (Discovery 2) — diagnostic capabilities

Functional reference for a future **BCU layer**. Describes *what* the Valeo Body
Control Unit exposes diagnostically — not the raw protocol (address/init unknown).

**Source:** a commercial vendor "Discovery II Valeo BCU ECU Guide" (20 pp.). Facts
compiled into our own structure; no text copied verbatim.

## About the module
The BCU is the D2's central electronics: **lighting, indicators, wipers, locking,
alarm and engine immobiliser**. Sits on the same shared K-line (pin 7). A customized
Valeo unit where much behaviour is governed by **settings** (market adaptation).

## Capabilities

### Read Inputs (live data from sensors/switches)
Side lights, LH/RH indicators, hazards, passenger/driver door switches,
**key lock/unlock** (two switches in the driver's door, also used for EKA entry),
CDL lock/unlock, inertia switch (fuel cut-off/unlock),
**ignition key inserted**, transfer box neutral, reverse switch, and more.

### Settings (read/write configuration)
Courtesy headlamps, electric windows (can be disabled), programmed wash-wipe, autographics,
**odometer error**, key warning (key left in + door open), bulb-failure detection,
alarm disarm behaviour, **EKA option**, passive immobilisation. Can be saved as HTML
and written back.

### Outputs — actuator tests (ON/OFF)
- **Body:** LH/RH indicator enable, front wiper, tail wiper, headlamp power wash,
  heated rear screen, check engine lamp, horn, ignition interlock.
- **Locking/Security:** Lock, Unlock, **Superlock**.

### Key programming / EKA / Utility  (SECURITY-SENSITIVE)
- **Key programming:** learn remote keys/fobs (including an accessory fob).
- **EKA (Emergency Key Access):** four-digit code, **each digit 1–16**. Read/set.
  Used to de-immobilise via the door locks if the remote key fails.
- **Immobiliser:** passive immobilisation (immobilises the engine 30 s after the
  driver's door is opened / 5 min after ignition off), remobilisation via a valid
  unlock or the EKA code. The engine's immobilisation status shows via a security LED.

## Relevance
Reading the BCU gives theft-protection/locking diagnostics and (via EKA/key programming) a way
around immobiliser problems — but is **security-sensitive** (requires a manual mode if
the auto-classifier blocks, cf. Td5 seed/key). The BCU is also the **gateway** on
the K-line bus, so it is central to how the other modules are reached.

## Remaining gap
Address + init type + service bytes for the BCU are unknown → bus scan/research, the same
pattern as SLABS. See `d2_diagnostic_overview.md`.

## Protocol — what we know ahead of the first connection (2026-08-19)

| Item | Value | Confidence |
|---|---|---|
| Diagnostic address | `0x40` | **candidate** — responds to 5-baud slow init with ignition OFF, and the BCU is the only permanently powered D2 module |
| Init | **5-baud slow init**, KWP2000 keybytes `E5 8F`, `~addr` 0xBF | proven from `logs/slow_sweep-*.log` (2/3 complete handshakes) |
| Session frames | unaddressed `<len> <SID> <data…> <cs>` | proven from the sniff 2026-08-09 |
| Keepalive | `02 3E 01 41` — **with sub-byte**, unlike SLABS | proven from the sniff |
| **EKA code** | **`21 CC`** | proven — the frame was sent exactly once under the marker "read set eka" |
| Inputs sweep | `21 D8`–`21 E9`, `21 2C`, `21 2D` | proven from the sniff |
| Settings | `21 C6, C7, CA, CB, CE, D3, D4, D5, D6, D7, EB` | proven from the sniff |
| SecurityAccess | `27 01` seed → `27 02` key | observed early in the session; **unclear whether `21 CC` requires it**, and the seed→key algorithm is unknown |
| EKA response format | four digits 1–16, encoding **unknown** | the sniff's response was corrupt (the KKL as a passive tap loads the bus) |

**Connection procedure:** the BCU enters diagnostic mode on an **ignition transition**
— the reference tool asks the operator to turn the ignition off, press a key, and turn
it on again. `tools/bcu_probe.py` guides through the same sequence.

**Next step:** run `tools/bcu_probe.py --expect <known code>`. With the reference in hand
the script searches for the code in the raw response and determines the encoding (one digit per byte, or two
per byte) instead of guessing. ⚠️ The code is passed as an argument and never stored
here — the repo is public.

## Car test 2026-08-20 — connection CONFIRMED, EKA locked

The first connection to the BCU succeeded (`tools/bcu_probe.py`):

- **Address `0x40`, 5-baud slow init, keybytes `E5 8F`** — exactly as the address hunt
  2026-08-05 predicted. `0x40 = BCU` is therefore no longer a guess.
- **EKA (`21 CC`) is gated behind SecurityAccess.** Without unlock the BCU responds with a
  fixed placeholder `11 99 07 01` — identical on all `1A xx` options AND on
  `21 CC`. The reference (EKA XXXX) was not in it, in any encoding. The frames are valid
  (checksums match), so it is a deliberately locked response, not noise.
- The sniff 2026-08-09 shows that the reference tool does `27 01` → `27 02` immediately
  after connecting, before every read. We skip it.

**Blocker:** the Valeo BCU seed→key algorithm is unknown. The Td5's keygen (ported from
td5keygen) does not apply here. The next step is research (community/reference tool-a commercial tool) or
collecting seed→key pairs to reverse-engineer. The probe now always captures a fresh
seed via `27 01` so we have data.

**Sniffed pair (one session, the seed rotates per session so it won't unlock a new one):**
`27 01` → response with seed, `27 02 4b 5c d4 82 f7 82` = key (6 bytes). Located in
`logs/faultread-20260809-2.log` t≈60 s.

## SecurityAccess research 2026-08-20 (PROVEN protocol, BLOCKED algorithm)

**The protocol is solved and verified against the logs.** The BCU uses standard KWP2000
SecurityAccess (0x27), gated in front of the EKA read:

| Step | Bytes | Source |
|---|---|---|
| Request seed | `02 27 01 2a` | `faultread-20260809-4.log` @574038 |
| Seed response | `04 67 01 EB CD a4` (seed = `EB CD`) | same |
| Send key | `04 27 02 C0 10 fd` (key = `C0 10`) | @574168 |
| **DENIED** | `7F 27 83` (NRC 0x83) | same |
| Successful key (other session) | `27 02 4B 5C` → then read `21 D8…` | `-2.log` @60031 |
| Key (other session) | `27 02 4A 8A` | `-4.log` @621153 |

**The algorithm `key = f(seed)` is unknown and CANNOT be reverse-engineered from our data:**
- The Td5 keygen doesn't match: `td5keygen(EB CD) = 04 2f`, not `C0 10`. A different algorithm.
- No public Valeo/Discovery 2 BCU algorithm found (the reference tool guide documents
  functions, not low-level SA; no github keygen like td5keygen exists).
- **All the seed→key pairs we have are corrupt or incomplete:**
  - `4A 8A`: the seed response was never captured (the passive tap dropped the frame).
  - `4B 5C`: seed = `86 f7 81 f0 86 f8`, not even a valid `04 67 01` frame (more than a bit-7 error).
  - `EB CD → C0 10`: the seed frame's cs is bit-7 corrupt (`a4` should be `24`), and denied.
- The passive KKL tap loads the bus → the BCU's RX frames get bit-7-flipped and dropped.
  **Clean pairs require that WE are master** (as in our slow-init capture) — but we can only
  send seeds, not compute keys. Generating clean pairs requires a tool that KNOWS the
  algorithm (the reference tool), which we don't have.

**Conclusion:** EKA via SecurityAccess is blocked until either (a) the algorithm
is found publicly, or (b) clean seed→key pairs can be generated with a working tool.
We do NOT need to read EKA — the code is already known and stored in the sister project. Pure
protocol scaffolding (`request_seed` exists in KWP2000; a `security_access(key_fn)`
can be added) is cheap to have ready if the algorithm turns up.

**Read-only next time in the car (safe, without guessing keys):** run `27 01` repeatedly
and note whether the seed changes per request / per ignition cycle / whether an already unlocked
BCU gives a fixed seed. Characterizes SA without touching protected writes.

## Seed characterization 2026-08-20 (DEFINITIVE: the seed rolls, EKA blocked)

Ran `bcu_probe --no-prompt` three times in a row and captured clean seeds as master
(not a passive tap → no bit errors). The raw log is unambiguous:

```
session 1:  27 01 → 04 67 01 AF 18 33   → seed = AF 18  (33 = additive cs)
            21 CC → 06 61 CC AF 18 33 01 2E   → returns the SEED, not EKA
session 2:  27 01 → 04 67 01 4A 4D 03   → seed = 4A 4D
            21 CC → 06 61 CC 4A 4D 03 01 CE
```

**Three proven findings:**
1. **The seed is 2 bytes and ROLLS per session** (AF 18 → 4A 4D). Standard anti-replay.
2. **`21 CC` without SecurityAccess returns the current SEED** (+ its checksum
   + `01`), NOT the EKA code. That explains the earlier "placeholder" `11 99 07 01`
   (2026-08-19 morning) — it was just that session's seed.
3. `1A xx` returns a fixed identity/status block (`11 99 07 01 01 01 01 0a eb`),
   the same every time.
4. Init is a bit unstable: 1 timeout of 4 attempts, and one session where 1A/27 01 didn't
   respond. Connects usually but not always (cf. SLABS/airbag init sensitivity).

**Consequence — EKA-via-SA is definitively blocked:**
- Rolling seed → an old seed→key pair can never unlock a new session.
- Reverse-engineering `key = f(seed)` requires MANY fresh (seed, key) pairs, and
  the key can only be obtained from a tool that already knows the algorithm (the reference tool). We can
  capture as many seeds as we like, but no keys.
- Brute force is inappropriate (rolling seed + likely attempt counter/lockout).
- **Conclusion: stop chasing EKA via SecurityAccess.** The code is known and stored in
  the sister project. The protocol is fully documented here should it ever be
  needed; the only thing missing is `f(seed)`, which cannot be derived from our data.
