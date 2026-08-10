# Felkoder — index (kanonisk ordbok ligger i registret)

**Kanonisk felkodsordbok:** `Discovery 2/discovery2_reference tool_fault_dictionary.md`
(registret) — reverse-engineering-struktur med confidence, rå-bytes-kolumn,
status-encoding, occurrence, källor och markerade display-vs-raw-konflikter. Fylls
på parallellt med sniff-arbetet. Kapaciteter: TD5 >200 (256 slots), SLABS 47,
ACE 45, Auto Gearbox GS8.87.0 39, Airbag TRW SPS 2A 37.

Detta är bara ett **index** till våra kod-inbäddade och sniffade källor:

| Modul | Rå-mappat i kod | Publik lista | Sett på RDL 016 |
|---|---|---|---|
| **Td5** | `src/d2diag/td5/faults.py` (210, `21 3B`-bit-per-fel) | reference tool Lucas TD5-guide + **forumlista (Kelvin, komplett X-Y)** — forumnot: `28-7` topside switch ≈ ECU-haveri (ej sett här) | `01-07` EGR, `04-01` IAT (intermittent); air flow+IAT under last |
| **SLABS** | ✅ `21 11`=loggade / `21 47`=aktuella (bit-per-fel, index=byte*8+bit), `14 FF FF`=clear. Bekräftat: `020-05`→byte3.bit4, `027-05`→byte10.bit4 | `references/slabs_fault_codes.md` (012–114) | `020-05` RF-givare + `027-05` shuttle valve (×254, loggade) |
| **ACE** | — (rå ej ren-sniffad, se not) | dicten **fullständig 0001–0048** (the factory tool# = display-index, forumbekräftad) | `04-02/04/05` riktningsventiler + `06-01` lågt tryck (aktuella) — **omläst 2026-08-10**, raderade + kalibrerade accelerometrar |
| **EAT** | — | dicten (39, RAVE) — **forumbekräftad** the factory tool# 1–39 | ❌ **går ej läsa** — Nanacom "unable to perform the function" (2026-08-10, även efter tänd-cykling). Rå visar `72`-ramad trafik = ej helt tyst, men fel format för vår 10400-parser |
| **Airbag** | — | dicten **position=display-kod löst** (RDL 016-ankare 4/8/22/32); full strängdump 1–65 | `004` varningslampa + `022` v. bältessträckare (intermittent) — **omläst + raderade 2026-08-10** |
| **BCU** | — | ingen konventionell fault-kapacitet (reference tool) | ej sniffad. EKA `XXXX` läst (tänd-cykling för anslutning) |

> ⚠️ **ACE & EAT sniffas INTE rent med nuvarande ESP32 (fast 10400 baud).** Deras
> K-line-ramar kommer **dubblerade** i loggen (`8a 8a`, `f5 f5`, `04 04 00`) — annan
> hastighet/format än SLABS/TD5. Därför kan vi bygga vår **egen** felkod-avläsare för
> SLABS/TD5 (rena captures) men **inte** för ACE/EAT ur dessa loggar. Felkoderna för
> ACE/Airbag kom i stället ur Nanacom-skärmen (belagt). Att sniffa ACE/EAT skulle
> kräva auto-baud/annan ESP32-firmware.

**Arbetsgång:** sniffa → analysera (`decode_session.py`) → fyll **rå-bytes + status-
encoding** i dicten (registret) → uppdatera vår kod (`faults.py` / SLABS-avkodare).
Sniffen löser display-vs-raw-konflikter (t.ex. SLABS `027-05` = `0B10`; TD5 `01-07`).
