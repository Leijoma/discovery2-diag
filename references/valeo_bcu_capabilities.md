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
