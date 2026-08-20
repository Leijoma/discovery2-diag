# Biltest — SLABS-signaler/luftning + BCU/EKA (plan)

Skriven 2026-08-19. Verifierar protokolländringarna sedan förra biltestet.
Kör **stillastående, handbroms**. K-line är delad → en session i taget; verktygen
släpper sessionen rent (`82`) själva. Bocka av i loggen.

## Förutsättningar

- SLABS kopplar bäst upp **med motorn igång** (mätt 2026-08-19). Init-pulsfixen
  sitter, så uppkoppling på 1–2 försök är väntat.
- BCU kräver **tändningscykel** (off → tangent → on) och kan köras med motorn av.
- Var noga med vilken port: `PYTHONPATH=src` behövs för `tools/*.py`.

---

## DEL A — SLABS live-signaler (motorn igång, ~10 min)

Målet: bekräfta att de nya fälten avkodar rimligt, och fånga rådata för de
kandidater vi ännu inte kan skala.

### A1. Koppla upp + fånga en baslinje-CSV
```
PYTHONPATH=src python3 tools/dashboard.py --serial /dev/cu.usbserial-XXXX --slabs --csv
```
- Öppna `:8080`, byt till SLABS, låt stå ~1 min.
- **Kolla i Inputs (v2 på `/v2` om du vill testa nya UI:t):**
  - `height_left/right` ~110–160, L≈R på plan mark. ✅ om stabilt.
  - `wheel_speed_fl/fr/rl/rr` — alla ~124 (råvärde, ≠ km/h) stillastående.
  - `abs_sensor_*` ~2,3 V.
  - `battery`/`ecu_supply` ~12,5–14 V.
  - `any_door` = closed; **öppna en dörr** → ska bli open. ✅ bekräftar interlocken.
- CSV:n hamnar i `logs/livedata-*-slabs.csv` (roteras per modul).

### A2. Hjul-ordningstest (bekräftar fl/fr/rl/rr — HYPOTES idag)
Kräver att ett hjul kan snurras: **palla upp ETT hjul säkert** (pallbockar, handbroms
på övriga), motorn igång, SLABS uppkopplad.
- Snurra det upplyfta hjulet för hand och se **vilket `wheel_speed_*`-fält som ändras**.
- Notera: upplyft hjul = X → fältet som rör sig är det rätta namnet för X.
- Gör om för minst två hjul → då är hela byteordningen belagd (annars fortsatt kandidat).
- ⚠️ Utan att palla upp: hoppa detta; ordningen förblir en hypotes.

### A3. MAF + gaspedal (för framtida skalning)
Fortfarande motorn igång, SLABS är fel modul här — **väx­la till motor (TD5)** i UI:t
(eller kör `--serial … ` utan `--slabs`). Med CSV-loggen på:
- **MAF:** notera `maf_raw`-råvärdet på **tomgång** och vid **~2000 rpm** (håll gaspedal
  stilla en stund vid varje). Facit: tomgång 55–65 kg/hr, 2000 rpm ~185–200. Vi kan
  sedan räkna ut råvärde→kg/hr-skalan ur de två punkterna.
- **accel_way3 (Euro 3-test):** tryck ner gaspedalen långsamt och se om `accel_way3`
  rör sig. Rör den sig → bilen är Euro 3 och fältet är giltigt. Står den på 0 → Euro 2,
  fältet är en spökkanal (märk kandidat/ej tillämpligt).
- **Gaspedal-spegling:** bekräfta att `accel_way1` stiger medan `accel_way2` sjunker.

---

## DEL B — SLABS ABS-luftning (ENDAST om du faktiskt luftar bromsar)

⚠️ **Bromssystem.** Kör bara om du gör en riktig bromsluftning. Stillastående,
handbroms, ingen under bilen. Kommandona är belagda ur sniffen men aldrig körda från
vår kod mot bilen — detta är första gången.

- I dashboarden (SLABS → ABS bleed-sektionen), eller från Python:
  ```
  PYTHONPATH=src python3 -c "
  from d2diag.slabs import Slabs, SLABS_ADDRESS
  from d2diag.kwp2000 import KWP2000; from d2diag.kline import KLine
  from d2diag.transport import SerialTransport
  s=Slabs(KWP2000(KLine(SerialTransport('/dev/cu.usbserial-XXXX'),target=SLABS_ADDRESS),tolerant=True))
  s.open(); s.establish()
  s.abs_power_bleed(True)   # pumpen startar
  # ... lufta ...
  s.abs_power_bleed(False)  # stopp
  s.abs_module_bleed()      # 4-stegssekvens
  s.release()"
  ```
- **Verifiera:** varje kommando ska svara `71 22 20` (verktyget kastar annars). Lyssna
  efter pump/ventiler. Om det bara ska **verifieras utan att lufta**: kör `power_bleed`
  on→off snabbt och bekräfta ack:en, kör INTE hela module-sekvensen i onödan.

---

## DEL C — BCU / EKA-kod (egen session, ~5 min)

Första gången vi kopplar upp mot BCU:n. Endast läsning — inga skrivningar.

### C1. Kör proben med facit
```
PYTHONPATH=src python3 tools/bcu_probe.py --expect XXXX
```
Den guidar tändningscykeln (off → Enter → on → Enter), kör 5-baud slow init mot
`0x40`, frågar `1A xx` (vem är du), och läser `21 CC` (EKA).

### C2. Tre möjliga utfall — alla informativa
1. **`FACIT HITTAT`** → EKA-formatet är belagt (en siffra/byte eller nibbles). Skriv in
   kodningen i `references/valeo_bcu_capabilities.md` — men INTE koden (publikt repo).
2. **`securityAccessDenied` (7F … 33)** → EKA kräver SecurityAccess. Proben hämtar då
   en **seed** åt dig. Spara `logs/bcu_probe-*.raw.log` — den behövs för keygen-arbetet
   (Valeo seed→key är okänd).
3. **Ingen kontakt på 0x40** → prova `--address 0x18` (andra slow-init-kandidaten), och
   cykla tändningen igen.

### C3. Bekräfta identiteten
`1A`-svaret ska innehålla läsbar ASCII (Valeo-delnummer) om `0x40` verkligen är BCU:n.
Notera vad som kom — det avgör 0x40-gissningen.

---

## Efter testet
- Klistra in `logs/connection.log`-svansen + relevanta `bcu_probe`/`slabs_probe`-loggar.
- Uppdatera konfidens i signalstoren för det som bekräftades (hjulordning, MAF-skala).
- BCU-fynd → `references/valeo_bcu_capabilities.md` (kod ALDRIG i repot).
