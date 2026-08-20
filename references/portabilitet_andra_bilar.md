# Portabilitet — verktyget på andra bilmodeller (roadmap, ej påbörjad)

Skriven 2026-08-20. **Strategi och förberedelse — ingen kod ändrad än.** Fångar
varför plattformen är portabel, vilka modeller som är realistiska, och hur ett
"vehicle profile"-lager skulle se ut. Bygg först när det efterfrågas.

## Varför det är portabelt

Lagerstacken (se `CLAUDE.md`) skiljer generiskt från modellspecifikt:

| Lager | Innehåll | Portabelt? |
|---|---|---|
| Transport | råa bytes (pyserial) | **generiskt** |
| K-Line | framing (adresserad + oadresserad), fast + 5-baud slow init, eko, retries, **den rättade init-pulsen** | **generiskt** (ISO 14230/9141) |
| KWP2000 | tjänste-ID:n, negativa svar, responsePending, SecurityAccess, tolerant läsning | **generiskt** |
| Modul-lager | adress, init-typ, LID→betydelse, ev. seed→key, felkodstabeller | **modellspecifikt** |
| Web/källor | mock + live per modul | mest generiskt |

Den **hårdvunna delen (nedersta tre lagren) är leverantörsneutral** — samma
K-line-protokoll oavsett bilmärke. En ny modul = tunn `EcuSession`-subklass +
en signalstore-JSON. Ingen kod i botten behöver röras.

## Realistiska mål — i ökande arbetsinsats

### 1. Defender Td5 (1998–2006) — nästan gratis
Samma **Td5 Lucas-motorstyrenhet** som vår Discovery 2 → `Td5`-klassen, keygenen
(`td5/keygen.py`) och LID-mappningarna borde fungera **rakt av**: samma seed→key,
samma `21`-fält. Ingen SLABS (ingen luftfjädring), men motordiagnostiken portar
direkt. **Otestat** men mycket hög sannolikhet. Lägsta hängande frukten.

### 2. Discovery 2:s egna moduler (samma bil) — underlag finns
BCU, ACE, EAT (autobox), Airbag är oklara på vår EGEN bil. Allt sniff-underlag
finns i `logs/`. "Samma plattform, fler moduler" före andra bilar.
- BCU: protokoll belagt, EKA blockerad av okänd seed→key (se `valeo_bcu_capabilities.md`).
- EAT ReadFaults bekräftad (`72 05 04 00 73` → svar), payload odekodad.
- ACE/Airbag: adresser kända, decoding ofärdig.

### 3. Freelander 1 / Range Rover P38 — riktigt arbete
K-line-lagret fungerar, men varje modul (motor, ABS, EAS, HEVAC) har egna
adresser/LID:er att kartlägga från noll. Andra motorer än Td5 (Freelander: Rover
K-serie / BMW-baserad Td4; P38: BMW M51 diesel / Rover V8). P38:ans fyrhjulsluft
är **EAS — en egen ECU**, inte SLABS (se nedan). Datainsamlingsjobb, inte kod.

### 4. Range Rover L322 tidig (2002–2005) — i praktiken ett BMW-projekt
BMW-eran → diagnostik ~identisk med BMW E38/E39 (DS2/KWP). K-line-lagret kanske
biter, men modul-uppsättningen är BMW:s. Minst aligned.

## Verifierade hårdvarufakta (att inte gissa om)

- **SLABS är Discovery 2-specifik** (Wabco, integrerad ABS + BAKRE nivåreglering i
  EN ECU, monterad i alla D2 även spiralfjädrade). **Delas inte** med Range Rover.
  P38 splittar ABS och EAS i två separata ECU:er. Det finns ingen 4-hjuls-variant
  av SLABS → `21 53/55`-byten är INTE fram-höjder (fram är alltid spiral på D2).
  Fyr-kanalsdatat i SLABS är broms-sidan (`21 43` hjulhastigheter, `21 50` ABS-V),
  som redan är mappat.
- **D2 = delad multi-drop K-line-buss, INTE en BCU-gateway.** Förstahandsbevis: en
  kvarlämnad session ger `7F 81 10` och blockerar andra moduler för att alla delar
  samma tråd — inte för att BCU:n dirigerar trafik. (Google/forum kallar BCU:n
  "gateway"; det är imprecist och påverkar hur en generisk modulväxlare designas.)

## Framtida abstraktion: "vehicle profile" (skiss, ej byggd)

Idag är modul-registret (`menus.py`, källorna i `web/sources.py`) D2-centrerat. För
flera bilar: lyft ut en deklarativ profil så en ny bil blir DATA, inte kod.

```
# skiss — inte implementerat
profiles/
  discovery2.json     # {modul: {address, init: fast|slow, framing, session, keygen?, signals: "slabs"}}
  defender_td5.json   # {motor: samma som d2:s td5}
```

En `VehicleProfile` skulle mappa modulnamn → (adress, init-typ, framing, ev.
seed→key-ref, signalstore-ref). `EcuSession`-subklasserna finns redan; profilen
väljer och parametriserar dem. Då blir Defender Td5 ett par rader och P38/Freelander
en datainsamlingsuppgift.

**Gör INTE detta förrän en andra bil faktiskt ska stödjas** — annars är det
abstraktion utan andra användare (YAGNI). Defender Td5 är det naturliga första
provet eftersom det återanvänder allt utan ny modulkunskap.

## Källor (2026-08-20)
- reference tool Wabco SLABS-preview; a commercial vendor SM016 (SLABS = D2, ABS + bakre SLS i en ECU).
- Community: SLABS monterad i alla D2; P38 EAS separat ECU.
