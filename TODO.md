# TODO — discovery2-diag

Uppdaterad 2026-08-19. Kryssa av när klart.

## Läget

TD5 och SLABS fungerar båda tillförlitligt sedan init-pulsen rättades 2026-08-19
(TiniH var ~32 ms i stället för 25 ± 1 — se `references/slabs_protocol.md`).
Dashboarden kopplar upp båda på första försöket och växlar modul utan problem.
220 tester gröna.

## Nästa gång i bilen

- [ ] **Verifiera SLABS över flera tillfällen.** Fixen är testad under en enda
      eftermiddag. Kör `tools/slabs_probe.py --quiet 5 --hold 30 --no-td5` vid
      kall start, efter längre stillestånd och i kyla. Träffkvoten ska ligga kvar
      runt 50 %+ per försök, och dashboarden koppla upp på första försöket.
- [ ] **Sänk `retry_sleep`.** SLABS `establish` väntar 28 s mellan försöken — ett
      arv från när init misslyckades av timing-skäl. Prova 3–5 s och mät; troligen
      onödigt nu och gör reconnect onödigt trögt.
- [ ] **Avgör W5 och P4.** Båda är implementerade men avstängda och obevisade:
      `--init-idle 1000` respektive `--write-gaps 0,5`. P4-mätningen gjordes
      dessutom innan väntan blev exakt, så den mätte fel värde.
- [ ] **Läs fler SLABS-LID:er nu när sessionen är pålitlig.** Öppet enligt
      `slabs_protocol.md`: analogskalning för `21 53/55` (supplies), `44/49/57`
      (ventiler/spänningar), `50` (ABS-sensor V), och settings-LID:erna där
      LID→funktion är olöst (kräver differential: ändra EN setting, se vilken
      råbyte som rör sig).
- [ ] **Bilens egna fel:** `020` höger fram hjulhastighetsgivare (output too low)
      och `027` shuttle valve switch (electrical failure) ligger loggade, 027 har
      setts som Current. Riktig verkstadsåtgärd, inte kod.

## Kod / offline

- [ ] **ACE, EAT och BCU** — underlag finns i sniffarna men är oimplementerat.
      EAT ReadFaults är bekräftad: `72 05 04 00 73` → `72 09 60 01 00 00 00 00 1B`
      (svarets innebörd okänd — tolka inte som felräknare än).
- [ ] **Airbag** är read-only och experimentell; overifierad live.
- [ ] **PyInstaller-distribution** (.app/.exe) för icke-tekniska användare.
- [ ] **Torque-proxy:** hitta TD5:s fuel quantity/demand-LID (mg/slag = ECU:ns
      momentkommando, i samma session som rpm/temp/gaspedal).
- [ ] Översätt kodkommentarer och docstrings till engelska (koden är svensk).
- [ ] Ev. återinföra store-driven SLABS-läsning — men inom 1 Hz-budgeten, som är
      det som gör sessionen stabil.

## Pi (discopi)

- [ ] Nyckelbaserad inloggning (`ssh-copy-id`), fast IP, fungerande `discopi.local`.
- [ ] Deploya repot, kör `pytest`, starta dashboarden → nå den från mobilen i bilen.

## Hårdvara

- [ ] **ESP32 i master-läge** — sketchen finns (`esp32/kline_test/`) och bit-bangar
      pulsen med mikrosekundsnoggrannhet. Inte längre nödvändig för SLABS, men den
      enda vägen att mäta de **fysiska** flankerna (vi ser bara vår mjukvarusida)
      och ett stabilare alternativ till USB-KKL.
- [ ] OBD-splitter med stift 7 genomkopplat för fortsatt sniffning.

## Metodlärdomar (kostade en hel dag 2026-08-19)

- **Lås aldrig ett experiment till en variant innan frågan är avgjord.** Ett pass
  låst till `fysisk/F7` gav 0/50 och såg ut som att modulen slutat svara.
- **Blanda ordningen.** Fast variantordning gjorde att vi mätte försöksnumret och
  trodde det var adressläget.
- **Kör inte betingelser som separata tidsblock** — då mäter man klockan. En
  "signifikant" skillnad (p=0,017) visade sig vara två olika tidpunkter.
- **Mät det du påstår att du mäter.** Flera hypoteser föll på att mätvärdet
  innehöll något annat (ekot i bursten, burst-läsningen i `to_frame_ms`,
  `sleep`-överskjutning i P4).
