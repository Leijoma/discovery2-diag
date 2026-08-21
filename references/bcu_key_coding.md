# BCU — EKA code (read/set) + key coding (goal & research)

Valeo BCU (immobiliser/body electronics). Slow init, permanently powered. Not yet
**sniffed** — this is the target and plan. Two levels, different risk.

## ⭐ MAIN GOAL: read the EKA code (LOW RISK — read operation)
**EKA (Emergency Key Access)** = a 4-digit code. If you know it, you get **past the
immobiliser** via the driver's door emergency-unlock procedure (without a reference
tool, if the car has locked itself out). **Reading** the code out of the BCU is a
pure read → **harmless**.

**reference tool method (to sniff):**
1. Connect, **ignition position II**.
2. Menu → **Valeo Body Control Unit**.
3. Scroll sideways → **"Read-set EKA"** → ENT.
4. The car's **4-digit EKA code is displayed**.
5. (Optional) MOD → overwrite with e.g. `1-2-3-4` so you can never lock yourself out.

**Our plan (while the reference tool is available):**
1. Sniff **BCU init** (slow-init address ~0x40 + keybytes; cf. the slow sweep).
2. Sniff the **"Read-set EKA" read** → capture the exact request and the response
   carrying the 4 digits. Pure read → safe to capture and to implement.
3. Implement `bcu.read_eka()` in a `d2diag.bcu` layer.
4. (Secondary) `bcu.set_eka(code)` — a defined *write* but reversible (change to a
   known value). Behind an explicit confirmation.

## Ignition quirk (verify during BCU sniff)
The method above says **ignition position II** for EKA. But the BCU generally
responds even with ignition OFF, and the user recalls a sequence "**ignition off →
init → ignition on**" for some function. **Capture the init in different ignition
positions** while logging, and note what the EKA read actually requires.

## ⚠️ SECONDARY (HIGH RISK): key/transponder programming
Programming in a completely **new key** is the real brick zone:
> *"A LOCKED BCU CANNOT BE UNLOCKED BY DIAGNOSTIC METHODS."*
Only done with **EKA known + spare key + stable power**, never interrupted. Requires
a sniff of a real key session + possibly a security algorithm (seed→key). **Only once
the EKA read + the BCU read protocol are in place.**

## Status
BCU not sniffed. Known: slow init, permanently powered, read by this car's reference
tool 1. **Next:** log the BCU with the ESP32 tap — init + **Read-set EKA** + the other
read functions. See [[valeo_bcu_capabilities.md]], `references/d2_diagnostic_overview.md`.
