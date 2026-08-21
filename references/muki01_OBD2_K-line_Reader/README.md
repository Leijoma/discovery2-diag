# muki01 / OBD2_K-line_Reader — reference

Saved reference (via the Wayback Machine 2025-10) of **muki01/OBD2_K-line_Reader**,
an OBD2 K-line library (ISO 9141 / ISO 14230 KWP2000, slow + fast init) for
Arduino/ESP32. **License: MIT** (per the PlatformIO/Arduino registry). Author: muki01.

- PlatformIO: https://registry.platformio.org/libraries/muki01/OBD2%20K-Line
- Archived source (the repo has been removed from GitHub): `web.archive.org/.../muki01/OBD2_K-line_Reader`

## What we take from here (into the ESP32 port)

- **Fast init** (`K_Line.ino`): `digitalWrite(TX, LOW); delay(25); digitalWrite(TX, HIGH); delay(25)`
  — 25 ms low + 25 ms high with **real-time GPIO**. Positive StartCommunication = `resultBuffer[3] == 0xC1`
  (the same `C1` we saw against the Td5). Confirms our approach.
- **5-baud slow init**: sends address `0x33` at 200 ms/bit.
- **Permissive read** (`readData`): reads the whole burst until ~60 ms of silence (`DATA_REQUEST_INTERVAL`)
  and indexes fixed positions — does NOT reject on checksum. Tolerates noise better. We recreated
  the technique in `tools/live_raw.py`.
- **Inter-byte `WRITE_DELAY`** when sending.
- **Addressing:** muki01 is standard OBD-II (`C1 33 F1 81`, functional address 0x33, tester 0xF1),
  NOT the Td5's physical `81 13 F7 81` (ECU 0x13 / tester 0xF7). The Td5 addressing + identifiers
  come from Ekaitza_Itzali.

## Schematics (`Schematics/`)

- `L9637D.png` — K-line transceiver (ST L9637D) as the interface. The robust path.
- `Transistor_Schematic.png` — discrete transistor interface (equivalent to the one the user built for the ESP32).

The Ekaitza note and these schematics point the same way: **real-time timing + noise filtering** give
reliable K-line — what a cheap USB-KKL + non-real-time OS cannot manage stably.
