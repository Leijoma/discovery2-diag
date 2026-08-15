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
| **ACE** | — (bulk-block isolerat) | dicten **fullständig 0001–0048** (the factory tool# = display-index, forumbekräftad) | `04-02/04/05` riktningsventiler + `06-01` lågt tryck (aktuella) — **omläst 2026-08-10**, raderade + kalibrerade accelerometrar. Fault-block: `67 67 11 e0 e0 f0 f0 … 08 09 80 92`. Utilities: calib1=`15 15 ff`, calib2=`16 16 ff`, set cal=`10 10 00` |
| **EAT** | — (annat protokoll, `72`-ramat) | dicten (39, RAVE) — **forumbekräftad** the factory tool# 1–39 | reference tool "unable to perform the function" 2026-08-10, MEN ECU:n **svarar** med datablock. Funktioner: read faults `72 05 04 00`, clear `72 04 05`, settings `72 05 93 00`, inputs `72 05 0b 00/03` |
| **Airbag** | ✅ **`src/d2diag/airbag/faults.py`** (`21 02`→poster `[status][num]`) | dicten **position=display-kod löst**; full strängdump 1–65 | `004` + `022` (intermittent) — **omläst + raderade 2026-08-10**; rå `61 02 90 04 90 16` avkodat |
| **BCU** | — (EKA via LID `CC`) | ingen konventionell fault-kapacitet (reference tool) | EKA `XXXX` läst: `21 CC`=läs, `3B CC XX XX XX XX`=skriv (tänd-cykling för anslutning) |

> ✅ **RÄTTELSE (tidigare fel):** ACE/EAT/Airbag/BCU är **strukturerade protokoll**,
> inte "skräp" — de använder bara annan framing än TD5/SLABS-KWP. Analysera loggarna
> med **`tools/analyze_capture.py`** (checksum-validerar KWP, känner igen `72`/`67`/
> `90 xx`/`CC`-ramar, ankrar annoteringar retroaktivt). Airbag-felformatet är nu
> avkodat i kod; Autobox/ACE/BCU-funktions-ID:n identifierade. ACE-inputs är ett
> **bulk-block** → kräver differential-captures för fält-mappning.

**Arbetsgång:** sniffa → analysera (`decode_session.py`) → fyll **rå-bytes + status-
encoding** i dicten (registret) → uppdatera vår kod (`faults.py` / SLABS-avkodare).
Sniffen löser display-vs-raw-konflikter (t.ex. SLABS `027-05` = `0B10`; TD5 `01-07`).
