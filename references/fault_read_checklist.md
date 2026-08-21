# Fault reading — cross-off list (before the reference tool is returned)

Goal: read **Read Faults** on as many modules as possible. You do **not** need the
sniff tool for this — read off the reference tool's screen and note it down. For each code:
**code + text + current/logged/intermittent (+ occurrence if shown).**

> ⚠️ **Airbag/SRS: read ONLY.** Never activate outputs (pyrotechnics).

---

## 1. Auto Gearbox (D2 Autogearbox) — **PRIORITY** (the gap)
This is the only module we haven't got fault codes out of (couldn't read it last time).

- [ ] Select **D2 Autogearbox** → **Read Faults**
- [ ] If "no comms"/no response: note **exactly** what it says, and try:
      ignition on / **engine running**, gear selector in **P/N**, read again
- [ ] Note codes (P-codes, e.g. `P0705`) + text + current/logged

## 2. TD5 (engine)
- [ ] TD5 → **Read Faults** → note codes + text + current/logged

## 3. SLABS
- [ ] SLABS → **Read Faults** → note **both** logged and current
      (we already have `020-05` RF sensor + `027-05` shuttle valve from before)

## 4. ACE
- [ ] ACE → **Read Faults** → note codes + text
      (earlier: `04-02/04-05` directional valves + `06-01` low pressure — current)

## 5. Airbag (SRS / TRW SPS)
- [ ] Airbag → **Read Faults** (READ ONLY) → note codes + text + intermittent
      (earlier: `004` warning lamp + `022` left seatbelt pretensioner)

## 6. BCU (Valeo) — no conventional fault-code list
- [ ] Connect: the reference tool says *"turn off ignition then press a key"* → turn **off**
      ignition, press a key → *"turn on transmission then press a key"* → turn **on** ignition,
      press a key → connects
- [ ] (No fault-code list to read; skip if short on time. The EKA code `XXXX` is already noted.)

---

**Write down everything you see and paste it into the chat** — I'll enter it into the
fault-code dictionary with the right confidence. A fresh final read on TD5/SLABS/ACE/Airbag
is cheap insurance even though we already have them.
