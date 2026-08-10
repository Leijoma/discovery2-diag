# Handoff — Discovery 2 diagnostik: protokoll-läge (för parallellt arbete)

Detta dokument sammanfattar vad som är **belagt** vs **kandidat** vs **öppet**, så
en andra analytiker kan bygga vidare utan att härleda om. Bilen: RDL 016, Td5 ES,
ZF4HP22/24. Sniff = passiv ESP32 (RX-only) på K-line pin 7, medan Nanacom kör.

## Loggfiler (rådata)
| Fil | Innehåll |
|---|---|
| `logs/session.log` | **Renaste** — TD5 (fuelling/outputs/security) + full SLABS-svep |
| `logs/faultread-20260809.log` | Auto gearbox (EAT), ACE, Airbag — read faults/inputs/outputs |
| `logs/faultread-20260809-2.log` | BCU (RF-test, EKA-läsning) |
| `logs/labeled_captures.jsonl` | Märkta fångster: `{module, lid, raw, text}` (klartext-facit) |
| `logs/analysis-all.txt` | Maskinkörd analys av alla loggar (`tools/analyze_capture.py`) |

## Framing & konventioner
- **Loggformat:** rader `[ms] hh hh …` (ESP32 gap-ramar + tidsstämpel), `>>> text` = operatörsmarkör.
- ⚠️ **Markörer hamnar MITT i en sensors flöde** — inte före/efter. Ankra retroaktivt:
  sök bakåt (~2–6 s) efter en trafik-regim som skiljer sig från föregående.
- **Skärm-fingerprint:** varje reference tool-skärm pollar en fast uppsättning `21 xx` — så
  koppla annoteringar till *regimen*, inte närmaste paket.

## TD5 (Lucas) — KWP2000, **löst grundprotokoll**
- **Ram:** `<len> <SID> <data…> <cs>`, `cs = summa(alla föregående) mod 256`. **Verifierat.**
- **Fast init:** addr `0x13` → `C1 57 8F`. Session `10 A0`→`50`. Security `27 01`(seed)→`67`,
  `27 02`(key)→`67`. **Keygen belagd** (seed `d3 e6`→key `ad 87`).
- **Tjänster:** 21→61 (ReadLocalId), 30→70 (IOControl), 31→71 (StartRoutine),
  33→73 (RoutineResults), 3E→7E (TesterPresent), 1A→5A (ReadEcuId), 14→54 (Clear), 18→58 (ReadDTC).
- **Felkoder:** `21 3B` = 35-byte bitblock (index = offset·8+bit). Avkodat i `td5/faults.py` (210 bitar).
- **Fuelling (BELAGT mot bil, se labeled_captures):** `09`=rpm, `0D`=road speed,
  `10`=batteri(u16/1000), `1A`=temp×4 (u16/10−273.2; ext_temp@8 = oansluten 150°C),
  `1B`=accel way1/2/3+supply (4×u16/1000 V), `1C`@0=MAP, `21`=idle err(s16), `23`=ambient×2,
  `40`=cyl-balans 1–5 (s16). OBS Nanacom visar tryck i **kPa** = vår bar × 100.
- **Outputs (30 xx FF):** A1 fuel pump, A2 MIL, A3 AC-clutch, A4 AC-fan, B3 glow, B7 rev-counter,
  BA temp-gauge, BE wastegate(+PWM), BD EGR(+PWM). **Injektorer:** `31 C2 0<n>` (cyl 1–5). Kodat.
- **Security:** `31 C0` + `33 C0` → `73 C0 03` (03 = ej immobiliserad). Kodat.
- **ÖPPET:** switch-inputs = `21 1E` + `21 36` **bitfält** (1E växlade `00 CA`↔`00 EA` = bit `0x20`;
  36 konstant `00 0D`). Settings hämtas i **bulk** (`21 3D 20 0E 32 24`, engångs). Behöver
  differential (ändra en switch/setting → se biten).

## SLABS (Wabco) — KWP2000, löst grundprotokoll
- **Fast init addr `0x29`** → `C1 57 8F`. Fel: `21 11`=loggade / `21 47`=aktuella (bitblock),
  clear `14 FF FF`→`54`. Avkodat. RDL 016: `020-05` RF-givare + `027-05` shuttle valve (loggade).
- **Skärm-fingerprints:** SLS-inputs `21 53/54/55`; ABS-inputs `21 43/44/49/50/57`;
  switchar `21 42/48/56/58`; settings `21 45/46/49/59`.
- **Belagt:** `21 54` = live höjd L/R (byte0/1). `21 43` = hjulhastighet, stillastående `7c 00 ×4`
  (≈124 baslinje ≠ 0). any-door = `21 56` byte0 bit0.
- **ÖPPET:** analog-skalning för 53/55 (supplies), 44/49/57 (ventiler/spänningar), 50 (ABS-sensor V).
  Settings **LID→funktion OLÖST** (ordningsbaserad märkning motsäger sig själv över körningar —
  kräver differential). "Stored height" ≠ `21 54` (annan källa, ej fångad).

## Airbag (TRW SPS 2A) — **felformat avkodat**
- `21 02` → `61 02` + poster **`[status][fault-number]`**; number = display-nr direkt
  (`90 04`=004, `90 16`=022). Status `0x90` = open circuit intermittent (kandidat).
  `21 01` var tomt (annan fault-klass?). Clear `14`→`54`. Kodat i `airbag/faults.py`.
- **ÖPPET:** statusbytens bit-betydelser (fler captures); 01 vs 02.

## Auto Gearbox (EAT, Bosch GS8.87) — **annat protokoll (`72`-ramat)**
- Nanacom sa "unable to perform the function", MEN ECU:n **svarar med datablock**.
- Funktioner: read faults `72 05 04 00 73`, clear `72 04 05 73`, settings `72 05 93 00 E4`,
  inputs pressure `72 05 0B 00 7C`, inputs general `72 05 0B 03 7F`, reset adaptive `72 06 83 FF 07 08 FF`.
  Svar: `72 <len> 60 <data> <cs>` (t.ex. settings `72 18 60 69 65 15 95 …`, inputs `72 16 60 01 …`).
- **ÖPPET:** ramformat (`72 <len> <func> …`? checksum?), innehållstolkning — vänta på lyckad session.

## ACE (Lucas) — bulk-block
- Fault-block (engångs): `67 67 11 e0 e0 f0 f0 00 00 00 1a 00 00 08 09 80 92 00 00` = fel-set
  {`004-02`, `004-04`, `004-05`, `006-1`}. Sedan pollas bara `04 04 00`/`07 07 00` (keepalive).
- Utilities: calib acc1 `15 15 FF`, calib acc2 `16 16 FF`, set calibrated `10 10 00`.
- Inputs = **ett bulk-block** som streamas ~1/s (offset/bit-mappning, inte en request per sensor).
- ⚠️ **Öppen fråga (dubblering):** många byte kommer par-vis (`67 67`, `e0 e0`, `f0 f0`, `04 04`).
  Är det protokollet eller en sampling-artefakt? Behöver avgöras (påverkar all ACE/EAT-tolkning).

## BCU (Valeo) — EKA löst
- **EKA:** läs `21 CC`, skriv `3B CC <4 byte>`. Fångat: `3B CC XX XX XX XX` → **EKA XXXX**.
- Settings-ID:n (BCU settings-skärm): `C7 CA CB D3 EB C6 CE D4 D5 D6 D7 …` (matcha mot dokumenterade grupper).

## Verktyg
- `tools/analyze_capture.py <logg>` — checksum-validerad KWP req→resp, fingerprints,
  retroaktiv ankring, känner igen 72/67/90/CC-ramar. Output i `logs/analysis-all.txt`.

## Förslag på arbetsdelning
- **Claude (kod):** analyze_capture → maskinläsbart protokollbibliotek (JSON), fälla in
  funktions-ID:n/decoders i `d2diag`, tester.
- **ChatGPT (hypoteser):** djup byte-fält-analys på **ett** bulk-block i taget — börja med
  (a) ACE-dubbleringsfrågan + ACE fault-block-struktur, eller (b) TD5 settings-bulk (`21 3D/32/0E`),
  eller (c) EAT `72`-ramformat. Leverera kandidat-offset/bit + vilket differentialtest som bekräftar.
