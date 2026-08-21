# Portability — the tool on other car models (roadmap, not started)

Written 2026-08-20. **Strategy and preparation — no code changed yet.** Captures
why the platform is portable, which models are realistic, and what a
"vehicle profile" layer would look like. Build only when it's needed.

## Why it's portable

The layer stack (see `CLAUDE.md`) separates generic from model-specific:

| Layer | Content | Portable? |
|---|---|---|
| Transport | raw bytes (pyserial) | **generic** |
| K-Line | framing (addressed + unaddressed), fast + 5-baud slow init, echo, retries, **the fixed init pulse** | **generic** (ISO 14230/9141) |
| KWP2000 | service IDs, negative responses, responsePending, SecurityAccess, tolerant reading | **generic** |
| Module layer | address, init type, LID→meaning, possible seed→key, fault-code tables | **model-specific** |
| Web/sources | mock + live per module | mostly generic |

The **hard-won part (the bottom three layers) is vendor-neutral** — the same
K-line protocol regardless of car make. A new module = a thin `EcuSession` subclass +
a signal-store JSON. No code at the bottom needs touching.

## Realistic targets — in increasing effort

### 1. Defender Td5 (1998–2006) — almost free
The same **Td5 Lucas engine ECU** as our Discovery 2 → the `Td5` class, the keygen
(`td5/keygen.py`) and the LID mappings should work **as-is**: same seed→key,
same `21` fields. No SLABS (no air suspension), but the engine diagnostics port
directly. **Untested** but very high probability. Lowest-hanging fruit.

### 2. Discovery 2's own modules (same car) — the material exists
BCU, ACE, EAT (autobox), Airbag are unclear on our OWN car. All the sniff material
is in `logs/`. "Same platform, more modules" before other cars.
- BCU: protocol proven, EKA blocked by an unknown seed→key (see `valeo_bcu_capabilities.md`).
- EAT ReadFaults confirmed (`72 05 04 00 73` → response), payload undecoded.
- ACE/Airbag: addresses known, decoding unfinished.

### 3. Freelander 1 / Range Rover P38 — real work
The K-line layer works, but every module (engine, ABS, EAS, HEVAC) has its own
addresses/LIDs to map from scratch. Different engines than the Td5 (Freelander: Rover
K-series / BMW-based Td4; P38: BMW M51 diesel / Rover V8). The P38's four-wheel air
suspension is **EAS — its own ECU**, not SLABS (see below). A data-collection job, not code.

### 4. Range Rover L322 early (2002–2005) — effectively a BMW project
The BMW era → diagnostics ~identical to BMW E38/E39 (DS2/KWP). The K-line layer might
bite, but the module set is BMW's. Least aligned.

## Verified hardware facts (not to guess about)

- **SLABS is Discovery 2-specific** (Wabco, integrated ABS + REAR levelling in
  ONE ECU, fitted in all D2s including coil-sprung ones). **Not shared** with the Range Rover.
  The P38 splits ABS and EAS into two separate ECUs. There is no 4-wheel variant
  of SLABS → the `21 53/55` bytes are NOT front heights (the front is always coil on the D2).
  The four-channel data in SLABS is the brake side (`21 43` wheel speeds, `21 50` ABS V),
  which is already mapped.
- **D2 = shared multi-drop K-line bus, NOT a BCU gateway.** First-hand evidence: a
  left-open session gives `7F 81 10` and blocks other modules because they all share
  the same wire — not because the BCU routes traffic. (Google/forum call the BCU a
  "gateway"; that's imprecise and affects how a generic module switcher is designed.)

## Future abstraction: "vehicle profile" (sketch, not built)

Today the module register (`menus.py`, the sources in `web/sources.py`) is D2-centric. For
multiple cars: lift out a declarative profile so a new car becomes DATA, not code.

```
# sketch — not implemented
profiles/
  discovery2.json     # {module: {address, init: fast|slow, framing, session, keygen?, signals: "slabs"}}
  defender_td5.json   # {engine: same as d2's td5}
```

A `VehicleProfile` would map module name → (address, init type, framing, possible
seed→key ref, signal-store ref). The `EcuSession` subclasses already exist; the profile
selects and parameterizes them. Then Defender Td5 becomes a couple of lines and P38/Freelander
a data-collection task.

**Do NOT do this until a second car is actually to be supported** — otherwise it's
abstraction without other users (YAGNI). Defender Td5 is the natural first
test since it reuses everything with no new module knowledge.

## Sources (2026-08-20)
- reference tool Wabco SLABS preview; a commercial vendor SM016 (SLABS = D2, ABS + rear SLS in one ECU).
- Community: SLABS fitted in all D2; P38 EAS separate ECU.
