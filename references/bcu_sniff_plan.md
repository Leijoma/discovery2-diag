# BCU sniff — checklist (while the reference tool is available)

Goal: capture **Valeo BCU** traffic passively with the ESP32 tap while the reference
tool runs. **Main prize: the EKA code** (Read-set EKA). Same rig as the SLABS sniff.

## Rig (like SLABS)
- ESP32 tap (RX-only, GPIO16) on pin 7 via Y-cable; the reference tool on the other branch.
- Mac: `python3 tools/esp32_read.py /dev/cu.usbserial-0001 logs/bcu.log`
- I watch `logs/bcu.log` live. Write **a marker + Enter** before each step.

## BCU quirks to know
- **BCU = SLOW init (5-baud):** the address itself does NOT show up in the UART stream
  (bit-bang = `00`). **But the post-init session** (EKA read, fault codes, inputs) runs
  at normal baud and is **captured cleanly** — that's the important part.
- **Ignition position:** the method says **position II** for EKA. But the BCU is
  permanently powered and often responds with ignition OFF; you recall an "off → init →
  on" sequence. **Try it and note what works** (write markers with the ignition position).

## ★ MAIN GOAL — the EKA code (LOW RISK, pure read)
1. [ ] Marker `bcu connect (ignition II)` → select **Valeo Body Control Unit** in the reference tool.
2. [ ] Marker `read eka` → **Read-set EKA** → ENT. The code (4 digits) is displayed.
3. [ ] **NOTE the 4 digits** + write them as a marker, e.g. `eka shows 4-7-1-9`.
   → **Perfect ground truth:** then we find exactly which bytes = EKA (like the VIN trick).
4. [ ] ⛔ **Do NOT press MOD** (don't overwrite the EKA) unless you deliberately want to change it.

## Other READ functions (harmless, run if there's time — marker before each)
- [ ] `bcu faults` — read fault codes
- [ ] `bcu inputs` — lock/CDL, ignition positions 1/2/3, windows, reverse light, mileage…
- [ ] `bcu settings` — lights/windows/market config (READ only)
- [ ] `bcu market` — **read the market/build setting** (controls DRL etc.; a Swedish car
      should be Scandinavia). NOTE the value as a marker.
- [ ] `bcu drl setting` — **read the DRL setting** (RDL 016 = disabled; ⛔ do NOT change it).
      Background: factory DRL is left off — the car has an aftermarket SEPAB box (see
      register `blinkersspak-ljus.md` section 6). We only want to **confirm** the values.

## ⛔ NEVER TOUCH
- Key/transponder programming (brick zone).
- Overwriting the EKA (unless you deliberately set a known value).
- Alarm/immobiliser writes.
- Our tap never transmits (RX-only) — but on the reference tool: **only read**.

## After logging — capture goals
- **BCU init type + keybytes** (post-init is visible; address ~0x40 known).
- **EKA read service + the code bytes** (cross-reference against the noted 4 digits).
- **Fault-read service**, **input LIDs**.
- → then a `d2diag.bcu` layer with `read_eka()` (+ possibly `set_eka()` behind a guard).

## Marker tips
Write short + ignition position: `bcu connect II` · `read eka` · `eka=4-7-1-9` · `faults` ·
`inputs` · `settings`. A marker right before each click is enough.
