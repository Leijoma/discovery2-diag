# Discovery 2 Td5 — platform overview

The Land Rover Discovery 2 (1998–2004) with the **Td5** engine is a **pre-CAN** car:
its modules talk over a single shared **K-line** wire (ISO 9141-2 / ISO 14230
KWP2000) at 10 400 baud. A cheap KKL 409.1 USB cable can read all of them. This
section documents each module — proven facts, working assumptions, and open
questions — reverse-engineered from sniffed traffic and verified on the reference
car **RDL 016**.

Confidence tags: 🟢 Proven · 🟡 Assumed · 🔴 Unknown ([legend](../README.md)).

## The bus

K-line on the D2 is a **shared multi-drop bus**, *not* a BCU-gateway (a common
misconception): one module holds the line at a time, and a session left open on one
module blocks the others with a `7F 81 10` generalReject. This is why every module
must be released cleanly. The details, framing, init timing and services are in
[kline-protocol.md](kline-protocol.md).

Each module answers at its own address and init style:

| Module | Address | Init | Session/unlock | Doc |
|---|---|---|---|---|
| **Engine (Td5 Lucas)** | 0x13 | fast | StartDiagnosticSession + SecurityAccess | [engine-td5.md](engine-td5.md) |
| **SLABS** (Wabco ABS + rear SLS) | 0x29 | fast | none (services work right after init) | [slabs.md](slabs.md) |
| **BCU** (Valeo body/immobiliser) | 0x40 | 5-baud slow | keepalive `3E 01`; EKA gated | [bcu.md](bcu.md) |
| **ACE / EAT / Airbag** | see doc | mixed | Airbag addressed @ 0x5B, read-only | [other-modules.md](other-modules.md) |

## Module status

| Module | What works 🟢 | Assumed 🟡 | Open 🔴 |
|---|---|---|---|
| **Td5 engine** | Connect, security access, immobiliser status, ~20 live signals incl. MAF, cylinder balance, faults (210 bits), outputs (fuel pump, glow, gauges), injector tests | ext_temp phantom, EGR/wastegate position (37/38), maf scale | Injection quantity → fuel consumption, switch bitfields (1E/36), VIN read |
| **SLABS** | Connect, corner heights, ABS sensor volts, wheel speeds, battery, faults; ABS bleed routines | wheel-order mapping, several input LIDs | full reference tool input block (42–59) decode |
| **BCU** | Connect (slow init), immobiliser status, identity | — | EKA code (SecurityAccess-gated, Valeo seed→key unknown) |
| **ACE** | address known | fault block isolated | live decoding |
| **EAT autobox** | ReadFaults confirmed | — | payload decode |
| **Airbag/SRS** | read-only fault read | — | decode |

## Fault codes

Every module's fault memory is readable. The catch: the numbers a factory tool
*displays* differ from the raw K-line bit indices, and even between reference lists —
so raw ↔ display must be sniff-mapped, not assumed. See
[fault-codes.md](fault-codes.md), including the confirmed RDL 016 fault baseline.

## Verification backlog

What's being actively confirmed (and how you can help) is in
[verification-todo.md](verification-todo.md) — including the path to live fuel
consumption.
