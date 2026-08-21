# BCU — Valeo Body Control Unit / Immobiliser

The BCU is the Discovery 2's central body electronics module: **lighting,
indicators, wipers, central locking, alarm, and the engine immobiliser**. It is a
customer-configured Valeo unit — much of its behaviour is driven by market/build
*settings*. It sits on the same shared K-line (pin 7) as every other module.

> ⚠️ **Read-only by construction.** This module layer only reads. There is no
> key programming, no settings write, no actuator test, and no EKA write in the
> code — deliberately. Community and factory documentation are unambiguous:
> *"a locked BCU cannot be unlocked by diagnostic methods."* Writing or coding a
> BCU blind is a **brick risk**. Reading fault codes and identity is safe;
> everything that changes BCU state is out of scope here.

## At a glance

| Property | Value | Confidence |
|---|---|---|
| Diagnostic address | `0x40` | 🟢 Proven — RDL 016, 2026-08-20 |
| Init | 5-baud **slow** init (ISO 9141 style) | 🟢 Proven — RDL 016, 2026-08-20 |
| Key bytes (KWP2000) | `E5 8F` (complement address `0xBF`) | 🟢 Proven — RDL 016, 2026-08-20 |
| Session framing | Unaddressed length-prefixed `<len> <SID> <data…> <cs>` | 🟢 Proven — sniff 2026-08-09 |
| Keepalive | `3E 01` **with sub-byte** (on the wire `02 3E 01 41`) | 🟢 Proven — sniff 2026-08-09 |
| Diagnostic-mode entry | Requires an **ignition transition** (off → key → on) | 🟡 Assumed (factory-tool procedure; connects reliably after it) |
| EKA read service | `21 CC` (ReadDataByLocalIdentifier) | 🟢 Proven service, but **gated** — see below |
| EKA / SecurityAccess unlock | Valeo seed→key algorithm | 🔴 Unknown |

## Connection

The BCU is **permanently powered**, so it will often answer a slow init with the
ignition off. But it only enters diagnostic mode reliably after an **ignition
transition** — the factory-tool procedure is: ignition off, press a key, ignition
on. Following that sequence, our slow init to `0x40` connected **first try** on the
car (RDL 016, 2026-08-20).

- **5-baud slow init**, address `0x40`. The address byte itself is bit-banged at
  5 baud and does not appear in the normal UART stream; the post-init session runs
  at 10 400 baud and captures cleanly.
- Handshake returns KWP2000 **key bytes `E5 8F`**, exactly as the 2026-08-05
  address sweep predicted. `0x40 = BCU` is therefore no longer a guess.
- The session that follows is **unaddressed** length-prefixed frames (the same
  shape as Td5/SLABS, *unlike* the airbag module which is addressed throughout).
- **Keepalive is `3E 01` — with the sub-byte** (`02 3E 01 41` on the wire). This
  is the opposite of SLABS, which needs a bare `3E`; the sub-byte matters per
  module. Implemented as `_keepalive_sub = 0x01` on the `Bcu` session.
- Init is **not perfectly stable**: roughly 1 timeout in 4 attempts observed, and
  one session where `1A`/`27 01` did not answer. It connects most of the time, not
  every time — the same init sensitivity seen on SLABS and airbag. The layer
  retries three times with a 2 s bus-quiet pause between attempts.

Because the D2 K-line is a **shared multi-drop bus** (not a BCU-routed gateway —
see the platform overview), a link left open by a previous run blocks other
modules with `7F … 10` (generalReject). Always end via the session's `release()`.

## Identity — `1A xx` (ReadEcuIdentification)

The `identify()` helper queries `1A 80 / 8A / 8B / 8D / 9B`. On the car these all
returned the **same fixed identity/status block**:

```
1A xx → 11 99 07 01 01 01 01 0a eb   (identical for every option)
```

🟢 Proven (RDL 016, 2026-08-20) that this block is constant and does **not** vary
by option. It is a fixed identity/status readout, not decoded further yet
(🔴 field meanings open).

## EKA (Emergency Key Access) — read is gated behind SecurityAccess 🔴

The **EKA code** is a four-digit code (each digit 1–16) that lets you get past the
immobiliser via the driver-door emergency procedure if the remote fob fails.
Reading it is a pure read operation — but on the BCU it is **locked behind
KWP2000 SecurityAccess**, and the Valeo seed→key algorithm is **unknown**.

**What the car proved (RDL 016, 2026-08-20):**

- The EKA read service is `21 CC`. It is a **valid, checksum-clean frame** — not
  noise — but **without an unlock it does not return the EKA code**.
- Careful characterization (running the probe as bus master, three sessions in a
  row) showed that **`21 CC` without SecurityAccess returns the current session
  *seed*, not the EKA code**:

  ```
  session 1:  27 01 → 04 67 01 AF 18 33      seed = AF 18
              21 CC → 06 61 CC AF 18 33 01 2E   ← echoes the seed, not EKA
  session 2:  27 01 → 04 67 01 4A 4D 03      seed = 4A 4D
              21 CC → 06 61 CC 4A 4D 03 01 CE
  ```

  > Note on an earlier reading: on the *morning* of 2026-08-20 the gated `21 CC`
  > (and every `1A xx`) looked like a fixed placeholder `11 99 07 01…`. Later,
  > clean master-side captures showed `21 CC`'s payload is actually that session's
  > **rolling seed**; the fixed `11 99 07 01…` block belongs to `1A xx`. Either
  > way the conclusion is identical: **the EKA code is not obtainable without a
  > successful unlock.**

- The **seed is 2 bytes and rolls per session** (`AF 18` → `4A 4D`) — standard
  anti-replay. A captured seed→key pair from one session can never unlock a new
  one.

**SecurityAccess protocol (proven) vs algorithm (blocked):**

The SecurityAccess *protocol* is standard KWP2000 `0x27` and is fully documented
from the logs:

| Step | Bytes | Source |
|---|---|---|
| Request seed | `02 27 01 2a` | `faultread-20260809-4.log` |
| Seed response | `04 67 01 <seed_hi> <seed_lo> <cs>` | same |
| Send key | `04 27 02 <key_hi> <key_lo> <cs>` | same |
| Denied | `7F 27 83` (NRC 0x83) | same (our captured attempt) |

But `key = f(seed)` is 🔴 **unknown and cannot be recovered from our data**:

- The **Td5 keygen does not apply**: `td5keygen(EB CD) = 04 2f`, not the `C0 10`
  the reference tool sent. Different algorithm.
- No public Valeo/Discovery-2 BCU seed→key implementation has been found (the
  reference tool guide documents *functions*, not the low-level algorithm).
- Every seed→key pair we sniffed passively is corrupt or incomplete — the passive
  KKL tap loads the bus and bit-7-flips the BCU's RX frames. Clean pairs would
  require us to be master, but as master we can only *send* seeds, not *compute*
  keys.

**Conclusion:** stop chasing EKA via SecurityAccess. Brute force is inappropriate
(rolling seed plus a likely attempt-counter/lockout). The protocol scaffolding is
cheap to keep ready if the algorithm ever surfaces publicly, but it is otherwise a
dead end with our tooling.

### The EKA code itself

For **RDL 016 the EKA code is known to be `XXXX`** — but that was read with a
borrowed **reference tool** (a tool that *does* implement the algorithm) and is stored in
the sister maintenance project. It was **not** obtained by this tool. A reference
tool sniff separately captured a write frame `3B CC XX XX XX XX` corresponding to
EKA `XXXX`, which suggests the on-wire encoding is one digit per byte (`07 09 08
06` = 7-9-8-6) behind an unlocked session — but this remains 🟡 Assumed for the
write path and is **never** exercised by our read-only layer.

## Reference-tool capability map (not yet reached by us)

The BCU exposes a large factory-tool menu — Read Inputs (lights, doors, locks,
ignition positions, mileage), Settings (market/build config, DRL, immobiliser
options, EKA option), and Outputs (locking, indicators, wipers, horn). All of it
is `todo` in our layer: none has been sniffed and decoded on this bus yet, and the
Outputs/Settings/key-programming sections are **write/actuator territory that we
will not touch**. The menu structure is carried in `src/d2diag/bcu/menu.py` for
future mapping only.

## Source files

- `src/d2diag/bcu/bcu.py` — the `Bcu(EcuSession)` read-only layer (`establish`,
  `identify`, `read_eka`).
- `src/d2diag/bcu/menu.py` — reference-tool menu map + our coverage status.
- `references/valeo_bcu_capabilities.md` — capability reference + the 2026-08-20
  car-test findings (connect confirmed, EKA gated, seed characterization).
- `references/bcu_sniff_plan.md`, `references/bcu_key_coding.md` — sniff plan and
  EKA/key-coding background.
