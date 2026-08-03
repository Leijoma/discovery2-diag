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
