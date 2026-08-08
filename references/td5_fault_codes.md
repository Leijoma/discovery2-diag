# Discovery 2 TD5 (Lucas motor-ECU) — felkoder

Motor-ECU:ns felminne. **Till skillnad från de andra modulerna är TD5 redan
rå-mappad** — vi läser felen direkt på K-line och avkodar dem bit-för-bit i kod.

- **Rå-avkodare (kod):** `src/d2diag/td5/faults.py` — 210 namngivna felbitar
- **Facit (display-koder + orsaker):** felkodsordboken (register-repot),
  TD5-sektionen inkl. Kelvins kompletta forumlista (`X-Y`-format)
- **Live-signaler:** `src/d2diag/td5/identifiers.py` (LID:er `21 xx`)

## Rå-kodning (BELAGT)
Td5 läser **inte** standard-DTC:er. Felminnet hämtas som ett **statusblock** via
ReadDataByLocalIdentifier `21 3B` (bytes efter positiv `61 3B`), och raderas via
StartRoutine `0xDD` med 18 nollbytes.

- Blocket är **35 byte** (offset 0–34) och **bitkodat**: varje bit = ett fel.
- **Felindex = offset·8 + bit** (bit 0 = mask `0x01` … bit 7 = `0x80`).
- Satta bitar utan känd text rapporteras generiskt som `byte<off>.bit<n>` så
  inget fel försvinner tyst.

Kartan är **belagd** ur referensverktyget Ekaitza_Itzali *och* korsvaliderad mot
**reference tool v1.12** — båda ger samma namn på samma offset/bit (ingen kod kopierad,
se `THIRD_PARTY_LICENSES.md`).

## Status-encoding (offset-band)
reference tool skiljer finare än Ekaitzas grova Logged/Current. Mönstret i blocket:

| Offset-band | Betydelse |
|---|---|
| 0–1 | **Logged Low** — lagrat, signal låg (kortslutning/låg spänning) |
| 2–3 | **Logged High** — lagrat, bruten krets (hög) |
| 4–5 | **Current** — givarkretsfel som är aktiva just nu |
| 6–13 | Drivsteg (over-temp / open-load / short), Logged resp. Current |
| 14–25 | Vevaxel, CAN, boost, driver demand, hastighet, cruise |
| 26–34 | Injektorer 1–6 (peak long/short, open/short/partial) + topside switch |

## Display-kod ↔ rå (korsning kvar att sniffa på RDL 016)
reference tool visar `X-Y` (t.ex. `28-7` topside switch). Vår rå-mappning ger
`offset.bit`. De ska korsvalideras genom att **sniffa reference toolen** när den läser
TD5-fel (fånga råblock + visad kod samtidigt) — samma metod som för SLABS.
Facit-tabellen i dicten håller display-koderna; denna fil + `faults.py` håller
råkodningen.

> 🔴 **`28-7` / `topside switch failed pre-injection`** (offset 27 bit 6, Logged;
> offset 29 bit 6, Current): forumets starkaste ledtråd för *motorn stannar helt /
> reference tool kommer inte in* — topside-switchen är en solenoid **inuti ECU:n** som
> havererar (särskilt efter fukt). Se dicten för hela resonemanget. Ej sett på
> RDL 016.

## Sett på RDL 016 (belagt)
`01-07` EGR, `04-01` IAT (intermittent), samt air flow + IAT under senare körning.
Inget injektor-/topside-fel observerat. (Facit: se dicten, kolumn "Sett på RDL 016".)
