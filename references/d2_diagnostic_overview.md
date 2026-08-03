# Discovery 2 — diagnostiskt modullandskap

Översikt över D2:ans styrdon på diagnostiken, för att bredda plattformen bortom
Td5-motorn. Sammanställt ur verkstadsmanualen, community-research och reference tool/
a commercial vendor modul-guider (protokollfakta; ingen kod kopierad).

## Fysisk anslutning (BELAGT)
- **En enda K-line på OBD-stift 7** (ISO 9141-2 / KWP2000). Ingen L-line (pin 15).
  Anslutna stift: 16 (batteri), 7 (K), 4 (chassijord), 5 (signaljord), 13 (valfri).
- **Delad buss:** motor, SLABS, ACE, BCU m.fl. hänger på samma K-line; **BCU
  fungerar som gateway**. Att dra ur ett styrdon kan störa hela länken.
  ⇒ **Vår befintliga kabel (pin 7) når alla moduler** — det som skiljer dem är
  adress + init + tjänster, inte stift.
- Skiljer sig per modul: **diagnosadress, init-typ (fast/slow), tjänstebytes** —
  detta är kvarvarande research/probe-arbete per modul.

## Moduler att kartlägga
| Modul | Vad | Källor / status |
|---|---|---|
| **Td5 EDC** (motor) | Adress 0x13, fast init, seed/key. **KLART** i d2diag. | Ekaitza + reference tool (felkarta korsvaliderad) |
| **Wabco SLABS** | ABS/SLS/EBD/ETC/HDC/EAS. 47 feltyper, Current/Intermittent + räknare. | `wabco_slabs_capabilities.md`. Adress/init okänt → probe |
| **Valeo BCU** | Centralelektronik + **immobiliser/larm/EKA/nyckelprogrammering**. | `valeo_bcu_capabilities.md`. Adress/init okänt |
| **SRS/airbag** | Krockkuddar. | Ej kartlagt |
| **ACE** | Active Cornering Enhancement (krängningsstyrning). | Egen K-line-diagnostikstift; ej kartlagt |
| **HEVAC** | Klimat. | Ej kartlagt |
| **EAT** | Automatlåda (ej relevant — vår bil är manuell). | — |

## Resurs: reference tool/a commercial vendor modul-guider (funktionella kapabiliteter)
a commercial vendor publicerar per-modul-guider (PDF) som beskriver *vad* varje
modul exponerar (inputs/settings/outputs/fault codes) — utmärkt för att bygga
respektive lager. Extraherbara med `pdftotext`. Kända URL:er:
- BCU: `reference tool-diagnostics.com/uploads/downloads/Discovery II Valeo BCU ECU Guide.pdf`
- SLABS: `reference tool-diagnostics.com/downloads/preview/wabco-slabs`
- Hjälpsidor per modul: `a commercial vendor/help/SMxxx.html` (SLABS = SM016).
Fler moduler (SRS/HEVAC/ACE/EAT) har troligen motsvarande guider på samma
download-sökväg — värt att prova när vi tar oss an dem.

## SLABS felkodsformat (samma som Td5!)
Community-koder anges som **(X,Y)** eller **X-Y** — samma bit-per-fel-indexering
som Td5:ans `21 3B` (X = byte-offset+1, Y = bit+1). Kända exempel:
- `(1,1)` at start of sequence
- `(2,12)…(2,15)` air gap: RH front / LH rear / LH front / RH rear (hjulhastighetsgivare)
- `(15,4)` front left outlet valve open circuit
- front right outlet valve short to ground; shuttle valve switch electrical failure
Detta antyder att SLABS-felminnet kan avkodas med **samma teknik som Td5**
(offset*8+bit → feltext) när vi väl har adress/init och kan läsa blocket. Full
lista (47 typer) finns i Nancom-firmware men är inte publikt dumpad — **läses ut
när vi väl kopplar upp mot SLABS.**

## Bussavsökning 2026-08-03 (BELAGT) — SLABS kräver slow init
`tools/probe_addresses.py` mot bilen (stillastående, tändning på):
- **Endast 0x13 (motorn) svarar på fast init** (positivt C1).
- Med motorsessionen dormant och 0x13 orörd: **ingen adress 0x01–0x3F svarar på
  fast init.** ⇒ SLABS m.fl. använder **inte** fast init.
- (Obs: en ÖPPEN motorsession generalRejectar alla adresser och maskerar bussen —
  motorn måste vara dormant vid skanning, och 0x13 får ej adresseras.)
- **Slutsats:** SLABS/BCU m.fl. kräver **5-baud slow init (ISO 9141)** — nästa
  bygge. Referenskod finns: muki01 `send5baud()` + `references/.../exempelkod`.

## Nästa steg för att nå en ny modul (mönster)
1. **Implementera 5-baud slow init** i transportlagret (adressbyte @ 5 baud →
   ECU svarar 0x55 + 2 keybytes → skicka inverterad keybyte). Sedan slow-init-skanning.
2. **Tjänster:** identifiera läs-DTC / read-inputs / clear (KWP2000-tjänster).
3. **Tunt modul-lager** ovanpå det generiska KWP2000-lagret (återanvänd Td5-mönstret).
