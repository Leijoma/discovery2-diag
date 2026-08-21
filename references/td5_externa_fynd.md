# Td5 — fynd ur externa repos (research 2026-08-21)

Genomgång av EA2EGA/Ekaitza_Itzali (Python, riktiga sniff-loggar), SimonRafferty
och muki01. Syfte: hitta vad vi INTE redan har. Vi visade oss ligga bra till.

## Redan implementerat hos oss (bekräftat av Ekaitzas riktiga sniffar)
- **Immobiliser/security status** — `security_status()` = `31 C0` + `33 C0`,
  RDL016 = **0x03 (ej immobiliserad), belagt**. OBS: Ekaitzas README listar detta
  som "Not yet" (oimplementerat) — VI har det oberoende. "Learn code" görs medvetet EJ.
  ⚠️ Ännu inte visat i v2-UI:t ("security status: planned").
- **Outputs `0x30`** — vårt `_OUTPUTS` matchar Ekaitzas fångade bytes exakt:
  A1 fuel pump · A2 MIL · A3 A/C-koppling · A4 A/C-fläkt · B3 glödstift · B7 varvräknar-
  svep · BA temp-mätarsvep · BD EGR-modulator (PWM).
- **Injektortester** `31 C2 01…05` (cylinderbalans) — har `injector_pulse`.
- **Seed→key** LFSR (taps bit 1,2,8,9) — har keygen.
- **Checksumma = summa(alla bytes inkl. längd) mod 256** — bekräftar `raw_analyze`-parsern.
- **Fast init 25 ms låg + 25 ms hög** — matchar vår (muki01 i
  `references/muki01_OBD2_K-line_Reader/`, Wayback-capture, MIT).

## Nytt att ev. adoptera (overifierat mot RDL016 — bekräfta först)
- **`21 1D` = "fuel-usage params"** (Ekaitza) → bekräftar att MAF (1D@5) OCH
  bränsle-/injektionsdata bor i 1D-blocket. **Vägen till bränsleförbrukning** går via
  injektionsmängd (mg/stroke) i 1D — jaga fältet ur en LASTAD körning (byte1 27→65,
  byte11 50→127 rörde sig med rpm; last skiljer injektion från rena rpm-fält).
- **ECU-identifiering `1A xx`**: `1A 87` VIN · `1A 9A` ECU-typ · `1A 9B/9C` fler ID.
  (Läs-only, lätt att lägga till — vi läser inte VIN idag.)
- **Digitala ingångar / switchar `21 1E` och `21 36`** (bitfält): broms, koppling,
  cruise, A/C-begäran, transfer-läge. Ekaitza ger pin-mappning (A33 transfer, B10/B16
  broms, B35 koppling, B15/B17/B11 cruise, B9/B23 A/C). Vi fångar 1E i råloggen men
  **avkodar inte bitfältet** — konkret mappnings-uppgift.
- **`21 32` / `21 0E`** homologation/map-variant (ASCII) · **`21 3D`** 14-byte statusblock.
- **`30 BE` wastegate-modulator** (vi har BD EGR men ev. inte BE wastegate — kolla).

## Låg återanvändning
- colinbourassa/libcomm14cux (Rover V8 14CUX) + memsgauge (MEMS 1.6): EJ KWP2000,
  bara K-line-/FTDI-wiring-referens.
- Zi-x/OBD-KLINE: generisk ISO14230, inget Td5-specifikt.

## Attribution
Ekaitzas sniff-loggar = hög tillit (fångat från riktig Td5). SimonRafferty läser som
delvis rekonstruerad och krockar med vårt bilverifierade LID-schema (MAF@1B m.m.) →
lägre tillit; verifiera dess `21 37/38` (EGR/wastegate-position) mot bilen först.
