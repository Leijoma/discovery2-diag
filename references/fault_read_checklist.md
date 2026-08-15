# Felkodsläsning — krysslista (innan reference tool lämnas tillbaka)

Mål: läs **Read Faults** på så många moduler som möjligt. Du behöver **inte**
sniff-verktyget för detta — läs på reference tools skärm och notera. För varje kod:
**kod + text + current/logged/intermittent (+ occurrence om det visas).**

> ⚠️ **Airbag/SRS: bara LÄSA.** Aktivera aldrig outputs (pyroteknik).

---

## 1. Auto Gearbox (D2 Autogearbox) — **PRIORITET** (luckan)
Detta är enda modulen vi inte fått ut felkoder från (gick ej läsa förra gången).

- [ ] Välj **D2 Autogearbox** → **Read Faults**
- [ ] Om "no comms"/inget svar: notera **exakt** vad som står, och prova:
      tändning på / **motor igång**, växelväljare i **P/N**, läs igen
- [ ] Notera koder (P-koder, t.ex. `P0705`) + text + current/logged

## 2. TD5 (motor)
- [ ] TD5 → **Read Faults** → notera koder + text + current/logged

## 3. SLABS
- [ ] SLABS → **Read Faults** → notera **både** loggade och aktuella
      (vi har sedan tidigare `020-05` RF-givare + `027-05` shuttle valve)

## 4. ACE
- [ ] ACE → **Read Faults** → notera koder + text
      (tidigare: `04-02/04-05` riktningsventiler + `06-01` lågt tryck — aktuella)

## 5. Airbag (SRS / TRW SPS)
- [ ] Airbag → **Read Faults** (LÄS ENDAST) → notera koder + text + intermittent
      (tidigare: `004` varningslampa + `022` v. bältessträckare)

## 6. BCU (Valeo) — ingen konventionell felkodslista
- [ ] Anslut: reference tool säger *"turn off ignition then press a key"* → slå **av** tänd, tryck tangent →
      *"turn on transmission then press a key"* → slå **på** tänd, tryck tangent → ansluter
- [ ] (Ingen felkodslista att läsa; hoppa om tidsbrist. EKA-koden `XXXX` är redan noterad.)

---

**Skriv av allt du ser och klistra in i chatten** — jag lägger in det i felkods-
ordboken med rätt confidence. Fresh slutläsning på TD5/SLABS/ACE/Airbag är billig
försäkring även om vi redan har dem.
