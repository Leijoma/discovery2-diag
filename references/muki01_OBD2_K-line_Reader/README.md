# muki01 / OBD2_K-line_Reader — referens

Sparad referens (via Wayback Machine 2025-10) av **muki01/OBD2_K-line_Reader**,
ett OBD2 K-line-bibliotek (ISO 9141 / ISO 14230 KWP2000, slow + fast init) för
Arduino/ESP32. **Licens: MIT** (enligt PlatformIO/Arduino-registret). Upphovsman: muki01.

- PlatformIO: https://registry.platformio.org/libraries/muki01/OBD2%20K-Line
- Arkiverad källa (repot är borttaget från GitHub): `web.archive.org/.../muki01/OBD2_K-line_Reader`

## Vad vi tar härifrån (till ESP32-porten)

- **Fast init** (`K_Line.ino`): `digitalWrite(TX, LOW); delay(25); digitalWrite(TX, HIGH); delay(25)`
  — 25 ms låg + 25 ms hög med **realtids-GPIO**. Positivt StartCommunication = `resultBuffer[3] == 0xC1`
  (samma `C1` vi såg mot Td5:an). Bekräftar vårt angreppssätt.
- **5-baud slow init**: skickar adress `0x33` med 200 ms/bit.
- **Permissiv läsning** (`readData`): läser hela bursten tills ~60 ms tystnad (`DATA_REQUEST_INTERVAL`)
  och indexerar fasta positioner — avvisar INTE på checksumma. Tål brus bättre. Vi återskapade
  tekniken i `tools/live_raw.py`.
- **Inter-byte `WRITE_DELAY`** vid sändning.
- **Adressering:** muki01 är standard-OBD-II (`C1 33 F1 81`, funktionell adress 0x33, tester 0xF1),
  INTE Td5:ans fysiska `81 13 F7 81` (ECU 0x13 / tester 0xF7). Td5-adresseringen + identifiers
  kommer från Ekaitza_Itzali.

## Scheman (`Schematics/`)

- `L9637D.png` — K-line-transceiver (ST L9637D) som interface. Den robusta vägen.
- `Transistor_Schematic.png` — diskret transistorinterface (motsvarar det användaren byggde till ESP32).

Ekaitza-noten och dessa scheman pekar åt samma håll: **realtids-timing + brusfiltrering** ger
pålitlig K-line — det som en billig USB-KKL + icke-realtids-OS inte klarar stabilt.
