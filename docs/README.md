# Land Rover K-Line Diagnostics — Open Knowledge Base

An open, honest, reverse-engineered reference for diagnosing Land Rover vehicles
over the **K-line** (ISO 9141-2 / ISO 14230 KWP2000) with cheap hardware. Every
fact here is tagged with how confident we are in it, and **where the evidence came
from**. The goal is a single place where the community can compile — and correct —
what is actually known about these buses, module by module.

This started as the diagnostics platform for a **Discovery 2 Td5** (reg. RDL 016),
reverse-engineered from sniffed bus traffic and verified against the real car. It
is being written to extend to the **Rover V8** platforms (14CUX / GEMS / Thor) over
time.

> If you have a reference tool, a factory tool trace, a wiring diagram, or a different
> car that fills a gap or contradicts something here — please open an issue or PR.
> Contradictions are welcome; that is how "assumed" becomes "proven."

## Confidence legend

Every claim in these docs carries one of three tags. Keep them honest — the value
of this reference is that the tags mean something.

| Tag | Meaning |
|---|---|
| 🟢 **Proven** | Verified against a real vehicle: we sent the bytes and confirmed the decoded value/behaviour against a known reference. The car, date, and how it was confirmed are cited. |
| 🟡 **Assumed** | Derived, transcribed, or matched to a published range but **not** yet confirmed on our car. Plausible, usable, but treat with caution. |
| 🔴 **Unknown** | An open question: a LID/byte/routine we can see but can't yet interpret, or a capability we haven't located. Listed so others can help. |

**Attribution discipline:** we distinguish strictly between *what a real car
demonstrated to us* and *what a forum, a factory tool transcription, or another
project reports*. Both are recorded, but only the former is 🟢 Proven, and the
source is always named.

## How this is organised

```
docs/
  README.md                 ← you are here (hub + legend + conventions)
  discovery-2-td5/
    README.md               ← platform overview + module status
    kline-protocol.md       ← the shared K-line / KWP2000 layer (init, framing, services)
    engine-td5.md           ← Td5 Lucas engine ECU (signals, security, outputs, faults)
    slabs.md                ← SLABS (Wabco ABS + rear self-levelling)
    bcu.md                  ← BCU (Valeo body control / immobiliser / EKA)
    other-modules.md        ← ACE, EAT autobox, Airbag/SRS
    fault-codes.md          ← fault-code index and raw↔display mapping
  rover-v8/
    README.md               ← roadmap: 14CUX / GEMS / Thor (not started)
```

## Platform status at a glance

| Vehicle | Module | Bus / init | State |
|---|---|---|---|
| Discovery 2 Td5 | Engine (Td5 Lucas) | K-line, fast init, addr 0x13 | 🟢 Live data, faults, security, outputs |
| Discovery 2 Td5 | SLABS (Wabco) | K-line, fast init, addr 0x29 | 🟢 Heights/ABS/faults; more inputs 🟡 |
| Discovery 2 Td5 | BCU (Valeo) | K-line, 5-baud slow, addr 0x40 | 🟢 Connect + immobiliser status; EKA 🔴 gated |
| Discovery 2 Td5 | ACE / EAT / Airbag | K-line | 🟡 Addresses known, decoding partial |
| Rover V8 | 14CUX / GEMS / Thor | K-line / serial | 🔴 Roadmap only |

## Hardware

A cheap **KKL 409.1 USB-to-K-line cable** (FTDI-based) is enough to read everything
here. K-line is a single shared, half-duplex wire at 10 400 baud, 8N1. Details and
the exact init timing that actually works are in
[`discovery-2-td5/kline-protocol.md`](discovery-2-td5/kline-protocol.md).

## Licence & provenance

This documentation is our own reverse-engineering, published openly. Where we
learned a protocol *fact* from another open project, that project is credited and
**no code was copied** — facts about how a car's bus behaves are not copyrightable,
but source code is. Notable references: `td5keygen` (BSD-2, seed→key), Ekaitza_Itzali
(EA2EGA, sniff logs), muki01/OBD2_K-line (MIT, init timing). See the per-module docs
for specific citations.

**Nothing here should be used to defeat security systems on a vehicle you do not
own.** Reading fault codes and live data is safe; clearing codes and actuator tests
change ECU state — do those stationary, engine off (or as noted), at your own risk.
