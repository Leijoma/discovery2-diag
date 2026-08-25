# reference tool weekend — sniff test plan & function TODO (Discovery 2)

> **Appendix.** The living backlog of what to test next is `references/test_plan.md`;
> this file holds the step-by-step detail it points at.

Goal: while the (borrowed) reference tool talks to the car's modules **we passively sniff pin 7**
and capture what we couldn't guess: **exact init, address, keybytes, header format,
service bytes, fault structure, any seed/key** — per module. Then we can build our own
d2diag layers (SLABS/BCU/EAT) on real traffic.

Sources: reference tool Evolution User Guide (v1.3), reference tool Wabco-SLABS and Valeo-BCU guides.

---

## ⚠️ SAFETY — read first

- **Bricking is real — but ONLY when writing/programming.** Reading +
  passive sniffing = safe.
- **Our rule: only READ on the reference tool. No writes, no programming.**
- **BCU immobiliser/EKA/key programming = absolutely forbidden** — can lock the car.
  The guide: *"A LOCKED BCU CANNOT BE UNLOCKED BY DIAGNOSTIC METHODS."*
- **SRS/Airbag: read ONLY fault codes.** Never run outputs/tests (pyrotechnics).
- **Never interrupt the reference tool mid-operation** (power/comms) → corrupt memory.
- **Our sniffer MUST be RX-only.** If it transmits it can interfere/damage. `sniff.py`
  only reads; run nothing that transmits. (ESP32+L9637D in pure RX is even safer.)
- If the reference tool freezes: avoid spamming buttons (it may crash/reboot it).

---

## PHASE 0 — Rig & check (before the reference tool is connected)

- [ ] **Y-cable, multimeter:** our branch has **pin 7 (K), pin 4+5 (ground), pin 16 (12V)**
      passed through (the KKL's transceiver needs 12V+ground). Continuity socket↔branches.
- [ ] Sniffer on our branch, **RX-only**. reference tool on the other branch.
- [ ] Stationary, **ignition on, engine off**. (SLABS loses comms >8–20 km/h.)
- [ ] Test that `sniff.py` logs with timestamps.

## PHASE 1a — Enumerate coverage (IMPORTANT — the unit is a reference tool 1)
The original (reference tool 1) is mostly a **Td5 engine tool**; broad D2 coverage
(SLABS/BCU/EAT/ACE/SRS) belongs to **Evolution** AND requires **unlock codes per
system group** enabled on this particular unit. We don't know in advance what it can do.
- [ ] Connect, **note which systems the menu offers** for the D2 (engine only? or more?).
- [ ] Note whether modules show as **locked** (require unlock code) vs available.
- Only Td5 → we validate the rig (steps below) but won't reach SLABS/BCU this time.
- More systems → run the whole per-module plan. **Anything beyond the engine = pure gain.**

## PHASE 1b — Validate the rig on a KNOWN module (the engine)

- [ ] New log `sniff_engine.log`. reference tool → **Td5 Engine (EDC)** → Read faults + live.
- [ ] Confirm in the log: `81 13 F7 81`, `C1 57 8F`, any `27 01→seed`, `21 xx`.
      Matches our known Td5 knowledge ⇒ **rig + annotation proven correct.**

---

## PHASE 2 — The unknowns, ONE module at a time

**Priority:** SLABS → BCU (read) → EAT → ACE → SRS.
**For each function:** [ ] new/continued log · [ ] note **time + reference tool action**
(correlation!) · [ ] run · [ ] verify the bytes came through.
**Order per module:** connect (→init/address/keybytes) → **fault-code cycle (read+clear)** →
read inputs → read settings. Other write functions are skipped (see ⚠️).

### ★ Fault-code cycle — read AND clear (capture BOTH services)
We want to learn **both the read and the clear service** (clear = a *safe* write; needed
to build `clear_faults`). Do this for each module, and **note time+action for each
step** so bytes can be paired up:
1. [ ] **Read fault codes** → capture read service + response structure (Current/Intermittent/counter).
2. [ ] **Clear fault codes** → capture the **clear service** (cf. Td5 `14` / `31 DD`).
3. [ ] **Read again** → capture what an **empty/cleared** response looks like (important reference).
   (Truly current faults may come back immediately — that's also useful info.)

### ★★ (Optional, HIGH value) Induce a KNOWN fault — ground truth for the decoder
To map **raw byte/index ↔ fault number** exactly (otherwise we're guessing): unplug a
**known, harmless, reversible** sensor and read → a *specific* fault appears whose
number we know from [slabs_fault_codes.md](slabs_fault_codes.md), so we see its raw
representation. Best candidate on SLABS: **a wheel-speed sensor connector** →
gives e.g. "Sensor Electric Fail" (064–067) for that wheel. Sequence:
read (empty) → unplug ONE sensor → read (fault N shows) → **reconnect** → clear → read (empty).
Then we have an exact anchor point; the rest of the systematic list falls into place.
⚠️ Only harmless/reversible sensors (wheel speed, height). **Never airbag/pyro.**
Stationary, ignition on. Note exactly which connector + timestamp.

### 🔵 SLABS (Wabco, ABS + air suspension) — PRIO 1 (three amigos)
| # | Function | Type | What we capture |
|---|---|---|---|
| [ ] | **Connect** to SLABS | — | init (slow/fast?), address, keybytes |
| [ ] | **Read Fault Codes** (Current/Intermittent + counter, 47 types) | READ | fault-read service + response structure |
| [ ] | **Clear Fault Codes** | (safe write) | clear service (cf. `14`/`31 DD`) |
| [ ] | **Inputs — ABS** (wheel speed FR/FL/RR/RL, 2.0–2.4 V) | READ | live-data service (`21 xx`?) |
| [ ] | **Inputs — SLS** (height sensors, 0–255 ≈ 1.4 mm/step) | READ | more LIDs |
| [ ] | **Inputs — Switch** | READ | switch block |
| [ ] | **Settings (READ)** — Test status, ECU calibrated, Transport mode, Suspension type, current heights | READ | settings-read service |
| [ ] | ⚠️ Store Target Heights / Suspension type / Test status | **WRITE** | **SKIP** (changes calibration) |
| [ ] | (optional) **Outputs** — pump, valves, lamps, compressor | write/activates | output control (`2F`/`31`); stationary, carefully |

### 🟢 Valeo BCU — PRIO 2 · **READ ONLY** (works even with ignition off)
| # | Function | Type | What we capture |
|---|---|---|---|
| [ ] | **Connect** to BCU | — | confirm address 0x40 + KWP2000 (our hypothesis) |
| [ ] | **Read Fault Codes** | READ | fault service |
| [ ] | **Read Inputs** (lock/CDL, ignition position 1/2/3, windows, reverse lights, diff lock, mileage…) | READ | input block |
| [ ] | **Settings (READ)** — lights/windows/seats/market config | READ | settings read |
| [ ] | ⛔ **Immobiliser / EKA / key programming / alarm** | **WRITE** | **NEVER TOUCH** — bricks/locks the car |

### 🟡 EAT — Automatic gearbox (ZF4HP22/24) — PRIO 3
| # | Function | Type | What we capture |
|---|---|---|---|
| [ ] | **Connect** to the auto gearbox | — | init/address/keybytes |
| [ ] | **Read Fault Codes** | READ | fault service |
| [ ] | **Read Inputs** (oil temp, gear position, rpm…) | READ | live data |
| [ ] | **Settings (READ)** | READ | settings read |

### 🟠 ACE (Active Cornering Enhancement) — PRIO 4
| # | Function | Type | |
|---|---|---|---|
| [ ] | Connect · Read faults · Inputs (pressure/valves) · Settings (read) | READ | init/address + services |

### 🔴 SRS / Airbag — PRIO 5 · **FAULT CODES ONLY**
| # | Function | Type | |
|---|---|---|---|
| [ ] | Connect · **Read Fault Codes** | READ | init/address + fault service |
| [ ] | ⛔ Outputs / actuator tests | **WRITE** | **NEVER** (pyrotechnics) |

---

## PHASE 3 — Correlation (make the log readable)
Note **time + exact reference tool action** for each step ("14:03 SLABS read fault codes").
Without it, bytes↔function is hard afterwards. (Alternative: the marker sniffer.)

## PHASE 4 — Finish
- [ ] Save all logs named per module.
- [ ] Note the **reference tool's firmware version**.
- [ ] No writes made (except any Clear faults).

---

## What we want to get out per module (capture goals)
1. **Init** — slow (5-baud) or fast, and the **exact address** (settles the SLABS question).
2. **Keybytes** → protocol (ISO9141 vs KWP2000).
3. **Header format** post-init (the part we could NOT guess).
4. **Fault-read service** + response structure (bit/counter layout).
5. **Live-data service** (`21 xx` equivalent) + which LIDs give which signals.
6. **Any security** (seed/key) → we can build a keygen as for Td5.

> After the weekend: feed the logs through `d2diag/sniff.py` (`describe`) for annotation,
> and build the SLABS/BCU/EAT layers on real traffic.
