# TODO — discovery2-diag

Uppdaterad 2026-08-03. Kryssa av när klart.

## Nästa gång i bilen (kräver ansluten bil)
Kör stillastående där det står. Verktyg körs `python3 tools/<x>.py ...`.

- [ ] **Dashboard mot riktiga bilen:** `python3 tools/dashboard.py --serial /dev/cu.usbserial-12345678`
      → öppna :8080, verifiera live-data + motorschema med äkta värden.
- [ ] **Radera felkoder på riktigt** (dashboard-knappen) → kör en stund → kom
      `inlet air temp`/`air flow (Current)` tillbaka? Avgör **intermittent vs konstant** (B-009).
- [ ] **MAF/IAT-givarens kontakt** (fysiskt): okulär + rengör/sätt om. Loggad både
      Low och High → intermittent glapp. Kolla ihop med **ECU-kablaget (B-001)** — samma område.
- [ ] **SLABS slow-init-skanning** (stillastående, motorn dormant, 0x13 orörd):
      `python3 tools/probe_slow.py /dev/cu.usbserial-12345678 01 3F` → hitta SLABS-adress.
- [ ] **Motor-ECU:ns SLABS-länkkoder** — läs redan nu (P1590-serien/HDC-länk syns via Td5).
- [ ] *Om lånat verktyg finns:* **sniffa** SLABS via OBD-splitter (pin 7 måste gå igenom):
      `python3 tools/sniff.py /dev/cu.usbserial-XXXX 7 sniff_slabs.log` medan verktyget läser SLABS
      → ger adress/init/tjänster/felstruktur. Knäcker BCU/SRS/ACE/HEVAC på köpet.

## Pi (discopi) — provisionering
Status 2026-08-03: **uppe på 192.168.68.62, SSH öppen, lösenordsinlogg funkar**
(vår nyckel ej auktoriserad, `discopi.local`/mDNS löser inte ut).

- [ ] Bekräfta inlogg: `ssh pi@192.168.68.62` (lösenord från userconf.txt).
- [ ] Lägg in nyckel: `ssh-copy-id -i ~/.ssh/id_ed25519 pi@192.168.68.62` → nyckelbaserad inlogg.
- [ ] **Fast IP:** DHCP-reservation i routern (MAC → .62) [renast], eller sätt inifrån.
- [ ] Fixa mDNS/hostname så `discopi.local` funkar (avahi/hostnamn).
- [ ] Deploya: klona/rsynca repot till Pi:n, `python3 -m venv .venv`, `pip install -e .[dev]`, `pytest`.
- [ ] Kör dashboarden på Pi:n → öppna från **mobilen** i bilen.

## Bygg/klart offline (referens)
Klart: Td5 (livedata + felkoder + skalning korsvaliderad), tolerant läsning, 5-baud slow init,
SLABS-skelett, passiv sniffer, realtidsdashboard (motorschema + radera-felkoder). 76 pytest gröna.

## Kräver hårdvara/extern
- OBD-splitter med **pin 7 genomkopplad** (för sniffning).
- Ev. lånat D2-verktyg (reference tool/a commercial tool) att sniffa.
- ESP32 + L9637D som robust RX-front (bäst för sniffning).
