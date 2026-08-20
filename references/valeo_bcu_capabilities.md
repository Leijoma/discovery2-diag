# Valeo BCU (Discovery 2) — diagnostikkapabiliteter

Funktionell referens för ett framtida **BCU-lager**. Beskriver *vad* Valeo Body
Control Unit exponerar diagnostiskt — inte råprotokollet (adress/init okänt).

**Källa:** a commercial vendor/reference tool "Discovery II Valeo BCU ECU Guide" (20 s). Faktauppgifter
sammanställda i egen struktur; ingen text kopierad ordagrant.

## Om modulen
BCU:n är D2:ans centralelektronik: **belysning, blinkers, torkare, låsning,
larm och motorimmobiliser**. Sitter på samma delade K-line (pin 7). Kundanpassad
Valeo-enhet där mycket beteende styrs av **inställningar** (marknadsanpassning).

## Kapabiliteter

### Read Inputs (livedata från givare/brytare)
Sidoljus, LH/RH blinkers, varningsblinkers, passagerar-/förardörrbrytare,
**nyckel lås/lås upp** (två brytare i förardörren, används även för EKA-inmatning),
CDL lås/lås upp, tröghetsbrytare (inertia — bränsleavstängning/upplåsning),
**tändningsnyckel isatt**, transfer box neutral, backväxel-brytare m.fl.

### Settings (läs/skriv konfiguration)
Courtesy headlamps, elfönster (kan spärras), programmerad wash-wipe, autographics,
**odometer error**, key warning (nyckel kvar + dörr öppen), bulb failure-detektion,
alarm disarm-beteende, **EKA option**, passive immobilisation. Kan sparas som HTML
och återskrivas.

### Outputs — ställdonstester (ON/OFF)
- **Body:** LH/RH indicator enable, front wiper, tail wiper, headlamp power wash,
  heated rear screen, check engine lamp, horn, ignition interlock.
- **Locking/Security:** Lock, Unlock, **Superlock**.

### Key programming / EKA / Utility  (SÄKERHETSKÄNSLIGT)
- **Nyckelprogrammering:** lär in fjärrnycklar/fobbar (även tillbehörsfob).
- **EKA (Emergency Key Access):** fyrsiffrig kod, **varje siffra 1–16**. Läs/sätt.
  Används för att av-immobilisera via dörrlåsen om fjärrnyckeln fallerar.
- **Immobiliser:** passiv immobilisering (immobiliserar motorn 30 s efter att
  förardörren öppnats / 5 min efter tändning av), remobilisering via giltig
  upplåsning eller EKA-kod. Motorns immobiliseringsstatus syns via säkerhets-LED.

## Relevans
BCU-läsning ger stöldskydds-/låsdiagnos och (via EKA/nyckelprogrammering) en väg
runt immobiliserproblem — men är **säkerhetskänsligt** (kräver manuellt läge om
auto-klassificeraren blockerar, jfr Td5 seed/key). BCU är dessutom **gateway** på
K-line-bussen, så den är central för hur övriga moduler nås.

## Kvarvarande lucka
Adress + init-typ + tjänstebytes för BCU är okända → bussavsökning/research, samma
mönster som SLABS. Se `d2_diagnostic_overview.md`.

## Protokoll — vad vi vet inför första uppkopplingen (2026-08-19)

| Sak | Värde | Konfidens |
|---|---|---|
| Diagnosadress | `0x40` | **kandidat** — svarar på 5-baud slow init med tändningen AV, och BCU:n är enda permanent matade D2-modulen |
| Init | **5-baud slow init**, KWP2000-keybytes `E5 8F`, `~addr` 0xBF | belagt ur `logs/slow_sweep-*.log` (2/3 kompletta handskakningar) |
| Sessionsramar | oadresserade `<len> <SID> <data…> <cs>` | belagt ur sniff 2026-08-09 |
| Keepalive | `02 3E 01 41` — **med sub-byte**, till skillnad från SLABS | belagt ur sniff |
| **EKA-kod** | **`21 CC`** | belagt — ramen skickades exakt en gång under markören "read set eka" |
| Inputs-svep | `21 D8`–`21 E9`, `21 2C`, `21 2D` | belagt ur sniff |
| Settings | `21 C6, C7, CA, CB, CE, D3, D4, D5, D6, D7, EB` | belagt ur sniff |
| SecurityAccess | `27 01` seed → `27 02` key | observerat tidigt i sessionen; **oklart om `21 CC` kräver det**, och seed→key-algoritmen är okänd |
| EKA-svarets format | fyra siffror 1–16, kodning **okänd** | sniffens svar var trasigt (KKL som passiv tapp lastar bussen) |

**Anslutningsprocedur:** BCU:n går in i diagnostikläge vid en **tändningsövergång**
— reference tool ber operatören slå av tändningen, trycka en tangent, och slå på
den igen. `tools/bcu_probe.py` guidar genom samma sekvens.

**Nästa steg:** kör `tools/bcu_probe.py --expect <känd kod>`. Med facit i hand
söker skriptet koden i råsvaret och avgör kodningen (en siffra per byte, eller två
per byte) i stället för att gissa. ⚠️ Koden skickas som argument och lagras aldrig
här — repot är publikt.

## Biltest 2026-08-20 — uppkoppling BEKRÄFTAD, EKA låst

Första uppkopplingen mot BCU:n lyckades (`tools/bcu_probe.py`):

- **Adress `0x40`, 5-baud slow init, keybytes `E5 8F`** — precis som adressjakten
  2026-08-05 förutsade. `0x40 = BCU` är därmed inte längre en gissning.
- **EKA (`21 CC`) är gated bakom SecurityAccess.** Utan unlock svarar BCU:n med en
  fast platshållare `11 99 07 01` — identisk på alla `1A xx`-optioner OCH på
  `21 CC`. Facit (EKA XXXX) fanns inte i den, i någon kodning. Ramarna är giltiga
  (checksummor stämmer), så det är ett medvetet låst svar, inte brus.
- Sniffen 2026-08-09 visar att reference tool gör `27 01` → `27 02` omedelbart
  efter uppkoppling, före varje läsning. Vi hoppar det.

**Blockerare:** Valeo BCU seed→key-algoritm är okänd. Td5:ans keygen (portad från
td5keygen) gäller inte här. Nästa steg är research (community/reference tool-a commercial tool) eller
att samla seed→key-par för att reverse-engineera. Proben fångar nu alltid en färsk
seed via `27 01` så vi har data.

**Sniffat par (en session, seed roterar per session så det låser inte upp en ny):**
`27 01` → svar med seed, `27 02 4b 5c d4 82 f7 82` = nyckel (6 byte). Ligger i
`logs/faultread-20260809-2.log` t≈60 s.

## SecurityAccess-research 2026-08-20 (BELAGT protokoll, BLOCKERAD algoritm)

**Protokollet är löst och verifierat mot loggarna.** BCU:n använder standard KWP2000
SecurityAccess (0x27), gated framför EKA-läsning:

| Steg | Byte | Källa |
|---|---|---|
| Begär seed | `02 27 01 2a` | `faultread-20260809-4.log` @574038 |
| Seed-svar | `04 67 01 EB CD a4` (seed = `EB CD`) | samma |
| Skicka key | `04 27 02 C0 10 fd` (key = `C0 10`) | @574168 |
| **NEKAD** | `7F 27 83` (NRC 0x83) | samma |
| Lyckad key (annan session) | `27 02 4B 5C` → läste sedan `21 D8…` | `-2.log` @60031 |
| Key (annan session) | `27 02 4A 8A` | `-4.log` @621153 |

**Algoritmen `key = f(seed)` är okänd och kan INTE reverse-engineeras ur vårt data:**
- Td5-keygenen matchar inte: `td5keygen(EB CD) = 04 2f`, inte `C0 10`. Annan algoritm.
- Ingen publik Valeo/Discovery-2 BCU-algoritm hittad (reference tools guide dokumenterar
  funktioner, inte lågnivå-SA; inget github-keygen likt td5keygen finns).
- **Alla seed→key-par vi har är korrupta eller ofullständiga:**
  - `4A 8A`: seed-svaret fångades aldrig (passiva tappen tappade ramen).
  - `4B 5C`: seed = `86 f7 81 f0 86 f8`, inte ens giltig `04 67 01`-ram (mer än bit-7-fel).
  - `EB CD → C0 10`: seed-ramens cs är bit-7-korrupt (`a4` ska vara `24`), och nekad.
- Den passiva KKL-tappen lastar bussen → BCU:s RX-ramar bit-7-flippas och tappas.
  **Rena par kräver att VI är master** (som vår slow-init-capture) — men vi kan bara
  skicka seeds, inte beräkna keys. Att generera rena par kräver ett verktyg som KAN
  algoritmen (reference tool), vilket vi inte har.

**Slutsats:** EKA via SecurityAccess är blockerad tills antingen (a) algoritmen
hittas publikt, eller (b) rena seed→key-par kan genereras med ett fungerande verktyg.
Vi BEHÖVER inte läsa EKA — koden är redan känd och lagrad i systerprojektet. Ren
protokoll-scaffolding (`request_seed` finns i KWP2000; en `security_access(key_fn)`
kan läggas till) är billig att ha redo om algoritmen dyker upp.

**Read-only nästa gång i bilen (säkert, utan att gissa keys):** kör `27 01` upprepat
och notera om seeden ändras per request / per tändningscykel / om en redan upplåst
BCU ger en fast seed. Karakteriserar SA utan att röra skyddade skrivningar.

## Seed-karakterisering 2026-08-20 (DEFINITIVT: seeden rollar, EKA blockerad)

Körde `bcu_probe --no-prompt` tre gånger i rad och fångade rena seeds som master
(inte passiv tapp → inga bit-fel). Rå-loggen är entydig:

```
session 1:  27 01 → 04 67 01 AF 18 33   → seed = AF 18  (33 = additiv cs)
            21 CC → 06 61 CC AF 18 33 01 2E   → returnerar SEEDET, inte EKA
session 2:  27 01 → 04 67 01 4A 4D 03   → seed = 4A 4D
            21 CC → 06 61 CC 4A 4D 03 01 CE
```

**Tre belagda fynd:**
1. **Seeden är 2 byte och ROLLAR per session** (AF 18 → 4A 4D). Standard anti-replay.
2. **`21 CC` utan SecurityAccess returnerar den aktuella SEEDEN** (+ dess checksumma
   + `01`), INTE EKA-koden. Det förklarar den tidigare "platshållaren" `11 99 07 01`
   (2026-08-19 morgon) — det var bara den sessionens seed.
3. `1A xx` returnerar ett fast identitets-/statusblock (`11 99 07 01 01 01 01 0a eb`),
   samma varje gång.
4. Init är lite ostadigt: 1 timeout av 4 försök, och en session där 1A/27 01 inte
   svarade. Kopplar upp oftast men inte alltid (jfr SLABS/airbag init-känslighet).

**Konsekvens — EKA-via-SA är definitivt blockerad:**
- Rullande seed → ett gammalt seed→key-par kan aldrig låsa upp en ny session.
- Att reverse-engineera `key = f(seed)` kräver MÅNGA färska (seed, key)-par, och
  nyckeln kan bara fås ur ett verktyg som redan kan algoritmen (reference tool). Vi kan
  fånga hur många seeds som helst, men inga keys.
- Brute-force är olämpligt (rullande seed + trolig attempt-counter/lockout).
- **Slutsats: sluta jaga EKA via SecurityAccess.** Koden är känd och lagrad i
  systerprojektet. Protokollet är fullständigt dokumenterat här om det någonsin
  behövs; det enda som saknas är `f(seed)`, som inte går att få fram med vårt data.
