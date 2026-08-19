# Handover — d2diag (Discovery 2 Td5 K-line-diagnostik)

_Skrivet 2026-08-18. Syfte: föra över pågående arbete till en ny session utan att tappa kontext._

## Vad projektet är

Öppet K-line-diagnostikverktyg för Land Rover Discovery 2 **Td5** (reg RDL 016,
VIN SALLXXXXXXXXXXXXX). Två delar:

- **`d2diag`** — Python-bibliotek (lager: Transport → KLine → KWP2000 →
  modulklasser Td5/Slabs/Airbag via gemensam `EcuSession`-bas) + en
  webb-dashboard (stdlib `http.server` + SSE + vanilla JS, noll beroenden,
  mobil-först, offline-tålig).
- Publikt på GitHub: `Leijoma/discovery2-diag`. Systerregister (svenska
  underhållsanteckningar + felkodsfacit) ligger i syskonmappen `../Discovery 2/`.

Repo-rot: `/Users/magnus/Documents/Privat/discovery2-diag`. Branch: `main`,
195 tester gröna. Projektkonventioner för Claude Code finns i repots `CLAUDE.md`.

## 🔴 DÄR VI ÄR JUST NU — SLABS-stabilitet (aktivt arbete)

Detta är den pågående tråden. **Läs `references/slabs_protocol.md` och minnet
`slabs-light-poll.md` först.**

### Problemet
SLABS (Wabco ABS+luftfjädring, adress `0x29`) kopplade upp men **dog efter
~15 s**, och reconnect blev trögt. Diagnos via en ny **anslutningslogg**
(`logs/connection.log`) visade en stapel regressioner sedan 7 aug.

### Vad som är löst (commits aced99b, 72f12a6, dd775cc)
1. **Bar `3E`-keepalive** — SLABS vill ha `3E` utan sub-byte (sniffad ram
   `01 3e 3f`); vi skickade `3E 01` som fick tomt svar och rev sessionen.
   Styrs av `EcuSession._keepalive_sub` (bas `0x01`, `Slabs` = `None`).
2. **Best-effort keepalive + nåd-period** — ett tappat `3E` eller en enstaka
   tyst pollcykel river inte längre sessionen (`_SLABS_EMPTY_GRACE = 3`).
3. **Revert till lätt baslinje-poll** — den viktigaste insikten: SLABS tål
   INTE aggressiv pollning. Reference tool körde ~1 Hz keepalive + enstaka
   läsningar. Vår store-drivna `read_block` (5 LID + felkoder VARJE 0.5 s-cykel,
   ~7× busstrafik) dödade sessionen. `SlabsDataSource.poll` läser nu bara
   höjder (`21 54`); felkoder högst var 10:e poll. `establish` tillbaka till
   `idle=0.3, attempts=3`.

### ✅ LÖST 2026-08-19 — orsaken var vår egen init-puls

Efter en dags mätande: **TiniH (höga perioden mellan låg-pulsen och
StartCommunication) var ~32 ms i stället för ISO:s 25 ± 1.** Två orsaker —
UART-stoppbiten efter puls-byten (~2,8 ms) räknades inte, och `time.sleep(25 ms)`
överskjuter till 25,3–32,0 ms (median 29,1) på macOS.

| | Träffkvot per initförsök |
|---|---|
| Före | 3/32 = **9 %** |
| Efter | 6/11 = **55 %** |

Fishers exakta test **p = 0,007**. Dashboarden kopplar nu upp SLABS på **första
försöket**, en sekund efter start, och sessionen är stabil (1 Hz-strypningen från
i går håller: 95/95 läsningar i tvåminuterstester).

**Alla andra hypoteser var återvändsgränder** — och flera av dem var mätfel:
adressläge (sammanblandat med försöksnummer), tyst period (sammanblandad med
tidpunkt), batterispänning (överlappande intervall), motorstatus (p=0,27), dörr
(n=2). Se `references/slabs_init_problem_brief.md` för hela genomgången.

**Lärdomen:** TD5 (Lucas) accepterade den felaktiga pulsen i månader. SLABS
(Wabco) har ett smalare toleransfönster och avslöjade felet. Att en modul är
nyckfull medan en annan fungerar betyder inte att modulen är trasig.

**Metodlärdomar värda att minnas:** lås aldrig ett experiment till en variant
innan frågan är avgjord (ett tortyrpass låst till `fysisk/F7` gav 0/50 och såg ut
som att modulen dött); blanda ordningen, annars mäter man positionen; och kör inte
betingelser som separata tidsblock — då mäter man klockan.

### Kodändringar 2026-08-18/19 (alla committade, 220 tester gröna)
`60e7bce` TD5-sessionsstädning vid modulbyte · `cd13085` CSV svarar direkt
(inline-kommandon) · `56c56d7` StopCommunication `82` · `36d7d2a` SLABS-trafik
strypt till 1 Hz på klockan · `ec5440f` anslutningsloggen nycklad på (modul, status)
· `261fe9d` `1A 8A` som sessionskvittens · `7c31c2c` hoppa över ekot vid C1-sökning
· `144210e` + `acf7eb5` **init-pulsen: stoppbit + exakt väntan** ← den avgörande
· `11e17e5` P4 och to_frame_ms mäter rätt sak.

Nya verktyg: `tools/slabs_probe.py` (kontrollerad init-matris med rå TX/RX och
pulsmätning) och `tools/slabs_torture.py` (statistiskt experiment över tyst
period, TD5-före och strömläge, blandad ordning med loggad seed).

### Vad som återstår
- **Verifiera i drift** över flera dagar och kalla starter — vi har mätt en
  eftermiddag.
- **W5 och P4** är implementerade (`init_idle`, `write_gap`) men avstängda och
  obevisade. P4-mätningen gjordes dessutom innan väntan blev exakt.
- **Fysiska flanker** är fortfarande omätta — vi ser bara vår mjukvarusida.
  ESP32-tappen kan tidsstämpla dem om det behövs.
- **Övrigt oförändrat:** ACE/EAT/BCU ej implementerade, airbag experimentell.

### Kör dashboarden
```bash
cd discovery2-diag
PYTHONPATH=src python3 tools/dashboard.py --public --port 8080
# öppna http://localhost:8080 ; kabeln autodetekteras (--serial /dev/cu.xxx för explicit)
# INTE --fault-watch när SLABS testas (se ovan)
```
En bakgrundsserver kan redan köra på 8080 (starta om: döda pid på porten först).

## Anslutningsloggen (nytt diagnosverktyg)

`logs/connection.log` — tidsstämplat, hela etableringsförloppet + connected/error-
övergångar. Live-progressen visas också i UI:t (banner + statuspill med spinner)
via `EcuSession._establish(progress=…)` → `source.on_progress` →
`DiagServer._connect_progress` → `self.latest` → SSE. Det var den här loggen som
avslöjade 3E-keepalive-buggen. Mock loggas inte; övergångar loggas bara vid ändring.

## Arkitektur (snabbkarta)

- `src/d2diag/session.py` — `EcuSession`-bas: open/close, `read_block(lids)`,
  `tester_present`, `_establish(after, idle, attempts, retry_sleep, progress)`,
  `end_session`/`release` (ren sessionsavslutning vid modulbyte, `_has_session`).
- `src/d2diag/td5/td5.py` — Td5: StartDiagnosticSession 0xA0 + SecurityAccess
  (seed→key), live-LID:er, felkoder (0x3B), output-tester. `establish(after=connect)`.
- `src/d2diag/slabs/slabs.py` — SLABS: fast init 0x29, `after=None`, `_keepalive_sub=None`.
- `src/d2diag/airbag/` — adress 0x5B, 5-baud slow init, ADDRESSED framing, **read-only**.
- `src/d2diag/kwp2000/kwp2000.py` — KWP2000; `tolerant` burst-läsning; `tester_present(sub)`.
- `src/d2diag/web/sources.py` — `Td5DataSource`/`SlabsDataSource`/`Mock*`; `poll()`,
  `on_progress`, `is_connected`, autodetektering av serieport (macOS `/dev/cu.*`).
- `src/d2diag/web/server.py` — `DiagServer` (poll-tråd + SSE), `/snapshot /events
  /command /signals /fields /community …`, CSV-logg, connection-logg.
- `src/d2diag/web/dashboard.html` — publikt UI: startsida med modulkort, ingen
  flik-rad i public, Verified/Experimental-toggle, connection-banner, disclaimer.
- `src/d2diag/signals/<module>.json` — deklarativ signalstore (mappnings-loopen).
  OBS: store-läsning är AV för SLABS-pollen just nu (stabilitet, se ovan).
- `server/endpoint.py` — opt-in bidrags-endpoint, driftsatt på
  `driftwoodstudios.se/d2diag` (Caddy + sqlite). `src/d2diag/community/` = klienten.

## Övrig status (inte aktivt just nu)

- **Publik v1 klar & deployad.** Two-tier trust (Verified/Experimental),
  read+clear-only i public (inga ställdon), opt-in anonym crowdsourcing med
  offline-outbox, CSV-live-logg. Bidrags-loopen verifierad end-to-end.
- **Modultäckning:** Td5 + SLABS belagda. Airbag experimentell (read-only).
  ACE/EAT/BCU ej implementerade. Airbag=0x5B, EAT bekräftad, BCU-banker.
- **Facit finns:** felkoder + live-värden lästa med lånad reference tool 2026-08-07
  (minne `reference tool-d2-fault-baseline`). Tre-amigos-orsak: SLABS RF-givare (020)
  + shuttle valve (027). EKA-kod läst (minne `rdl016-eka-code`).
- **Hårdvara (sidospår):** fristående ESP32 K-line-verktyg designat i
  `hardware/README.md` (ST L9637D, OBD-matning). Kommer göra fast-init-timingen
  mycket stabilare än USB-KKL (som är inneboende trög — 2–4 försök normalt).

## Backlog (dokumenterat, ej gjort)

- PyInstaller-distribution (.app/.exe).
- Torque-proxy RE: hitta TD5:s fuel quantity/demand-LID (för gaspedal/torque-logg).
- Översätt kodkommentarer/docstrings till engelska (koden är fortf. svensk).
- Ev. återinföra SLABS store-läsning FÖRSIKTIGT (långsammare kadens) efter att
  baslinjen bekräftats stabil.

## Konventioner (från CLAUDE.md)

Svenska, ISO 8601-datum, km (inte mil). Skilj strikt på **belagt** vs
**slutsatsdraget** (och på vad RDL 016 faktiskt visat vs forumrapporter —
minne `attribution-discipline`). Verkstadsmanual sökbar via `pdfgrep` i
`../Discovery 2/referens docs/`. Verifiera alltid momentvärden mot manualen.
