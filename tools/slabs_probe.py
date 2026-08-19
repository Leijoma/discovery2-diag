#!/usr/bin/env python3
"""SLABS-prob: testa init-varianter systematiskt och logga ALLT.

Dashboarden är fel verktyg för att felsöka anslutningen — den kopplar om, byter
modul och skriver över kontexten. Det här skriptet gör tvärtom: en kontrollerad
sekvens, en variant i taget, med rå TX/RX till fil.

Bakgrund (se references/slabs_protocol.md):
  * Reference tool initierar FYSISKT med testar-adress 0xF7: ``81 29 F7 81 22``.
  * Vår egen adressjakt 2026-08-05 fick svar från 0x29 ENBART i FUNKTIONELLT läge
    med testar-adress 0xF1: ``C1 29 F1 81 5c`` → ``C1 57 8F``.
  * muki01-referensen (bekräftad korrekt) initierar funktionellt: ``C1 33 F1 81 66``.
  * Init lyckas i sniffen först efter 25–28 s UTAN trafik mot modulen.

Skriptet mäter därför båda adresslägena med tysta perioder emellan, och läser
motorkontext (varvtal/fart/batteri) före testet så ett tyst försök går att tolka
i efterhand — SLABS vägrar comms >8–20 km/h.

Kör stillastående med tändning på:

    PYTHONPATH=src python3 tools/slabs_probe.py                  # autodetektera kabel
    PYTHONPATH=src python3 tools/slabs_probe.py --quiet 30 --hold 120
    PYTHONPATH=src python3 tools/slabs_probe.py --no-td5 --rounds 2
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from d2diag.kline import KLine, encode  # noqa: E402
from d2diag.kline.kline import KLineTimeout  # noqa: E402
from d2diag.kwp2000 import KWP2000  # noqa: E402
from d2diag.slabs import SLABS_ADDRESS, Slabs  # noqa: E402
from d2diag.td5 import Td5  # noqa: E402
from d2diag.transport import LoggingTransport, SerialTransport  # noqa: E402
from d2diag.web.sources import resolve_serial_port  # noqa: E402

# (namn, funktionell, testar-adress) — ordningen är testordningen.
VARIANTS = (
    ("fysisk/F7  (reference tool)", False, 0xF7),
    ("funktionell/F1 (jakt+muki01)", True, 0xF1),
    ("funktionell/F7", True, 0xF7),
    ("fysisk/F1", False, 0xF1),
)

_log_fh = None


def say(msg: str) -> None:
    line = f"{dt.datetime.now().strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    if _log_fh:
        _log_fh.write(line + "\n")
        _log_fh.flush()


def quiet(seconds: float, why: str = "tyst period") -> None:
    """Vänta UTAN att skicka något. Varje byte nollställer modulens väntan."""
    if seconds <= 0:
        return
    say(f"  … {why} {seconds:.0f}s")
    time.sleep(seconds)


def engine_context(transport, sleep_after: float) -> "dict | None":
    """Läs rpm/fart/batteri ur TD5 och släpp sessionen rent (20 + 82).

    Ger tolkningsbar kontext till ett tyst SLABS-försök: stod bilen stilla?
    Gick motorn? Vad låg spänningen på?
    """
    td5 = Td5(KWP2000(KLine(transport, target=0x13), tolerant=True))
    try:
        td5.establish()
    except Exception as exc:  # noqa: BLE001
        say(f"  TD5 svarade inte ({type(exc).__name__}) — kabel/tändning?")
        return None
    try:
        vals = td5.read_all()
        ctx = {k: vals.get(k) for k in ("rpm", "speed", "battery")}
        say(f"  TD5: rpm {ctx.get('rpm')}, fart {ctx.get('speed')} km/h, "
            f"batteri {ctx.get('battery')} V")
        # Mätt 2026-08-19 (8 körningar): motorn igång gav 3 träffar av 4, motorn av
        # bara 1 av 4. Ingen skarp spänningströskel, men klart starkaste faktorn.
        if not ctx.get("rpm"):
            say("  ⚠️  MOTORN ÄR AV. SLABS svarade bara i 1 av 4 körningar så — "
                "starta motorn för bästa chans (SLS:s normala driftfall).")
        if (ctx.get("speed") or 0) > 5:
            say("  ⚠️  BILEN RULLAR. SLABS vägrar comms >8–20 km/h — stanna först.")
        return ctx
    except Exception as exc:  # noqa: BLE001
        say(f"  TD5 läsfel: {type(exc).__name__}: {exc}")
        return None
    finally:
        # end_session() = 20 + 82. INTE release()/close(): porten delas med
        # SLABS-försöken, och en stängd port får varje följande init att "misslyckas"
        # utan att en enda byte gått ut på bussen.
        try:
            td5.end_session()
        except Exception:  # noqa: BLE001
            pass
        quiet(sleep_after, "låt bussen tystna efter TD5")


def try_init(transport, name: str, functional: bool, source: int,
             write_gap: float = 0.0) -> "Slabs | None":
    """Ett enda initförsök med en given variant. Returnerar en levande Slabs eller None.

    ``write_gap`` är P4 — inter-byte-tiden i vår förfrågan. ISO 14230-2 anger
    5–20 ms och muki01-referensen använder 5 ms, medan vi alltid skickat hela ramen
    i ett svep. Det är en otestad hypotes om varför reference tool kommer in på
    första försöket och vi behöver flera.
    """
    frame = encode(b"\x81", SLABS_ADDRESS, source, addressed=True, functional=functional)
    gaptxt = "" if not write_gap else f" · P4 {write_gap*1000:.0f} ms"
    say(f"  → {name}{gaptxt}: {frame.hex(' ')}")
    kwp = KWP2000(KLine(transport, target=SLABS_ADDRESS, write_gap=write_gap), tolerant=True)
    slabs = Slabs(kwp)
    try:
        c1 = kwp.start_communication(tolerant=True, functional=functional, source=source)
    except KLineTimeout as exc:
        say(f"     tyst ({exc})")          # bussen svarade inte — ett giltigt mätvärde
        return None
    except Exception as exc:  # noqa: BLE001
        # Allt annat är VÅRT fel (stängd port, trasig kabel). Det får aldrig
        # rapporteras som "tyst" — då tolkas ett testfel som ett modulsvar.
        say(f"     ✗ LOKALT FEL, inget skickades: {type(exc).__name__}: {exc}")
        raise
    say(f"     C1! {c1[:4].hex(' ')}")
    # Kvittens: reference tool skickar alltid 1A 8A först — och svaret skiljer en
    # riktig session från ett C1 som bara låg i bruset.
    try:
        ident = slabs.read_ecu_id(0x8A)
        say(f"     kvittens 1A 8A → {ident[:8].hex(' ')}")
    except Exception as exc:  # noqa: BLE001
        say(f"     INGEN kvittens på 1A 8A ({type(exc).__name__}) — troligen falskt positiv")
        return None
    return slabs


def hold(slabs: Slabs, seconds: float) -> None:
    """Håll sessionen på 1 Hz (reference tools takt) och logga varje läsning."""
    say(f"  håller sessionen i {seconds:.0f}s på 1 Hz …")
    t0 = time.monotonic()
    reads = misses = 0
    try:
        faults = slabs.read_faults()
        say(f"  felkoder: {faults}")
    except Exception as exc:  # noqa: BLE001
        say(f"  felkodsläsning misslyckades: {type(exc).__name__}")
    while time.monotonic() - t0 < seconds:
        time.sleep(1.0)
        try:
            slabs.tester_present()
        except Exception:  # noqa: BLE001
            pass
        try:
            raw = slabs.read_data(0x54)
        except Exception:  # noqa: BLE001
            raw = b""
        if raw:
            reads += 1
            if reads % 10 == 1 or misses:
                say(f"   {time.monotonic() - t0:5.0f}s  höjder {raw[0]}/{raw[1]}"
                    f"  ({reads} ok, {misses} tappade)")
            misses = 0
        else:
            misses += 1
            say(f"   {time.monotonic() - t0:5.0f}s  TYST ({misses} i rad)")
            if misses >= 5:
                say("  ✗ sessionen tappad")
                return
    say(f"  ✓ höll hela perioden: {reads} lyckade läsningar")


def main() -> int:
    global _log_fh
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--serial", default="auto", help="serieport (default: autodetektera)")
    ap.add_argument("--quiet", type=float, default=30.0,
                    help="tyst period mellan försöken i sekunder (default 30)")
    ap.add_argument("--hold", type=float, default=120.0,
                    help="håll sessionen så här länge vid träff (default 120 s)")
    ap.add_argument("--rounds", type=int, default=1, help="antal varv genom matrisen")
    ap.add_argument("--no-td5", action="store_true",
                    help="hoppa över TD5-kontexten (ingen rpm/fart/batteri i loggen)")
    ap.add_argument("--write-gaps", default="0,5",
                    help="P4-värden att testa i ms (default 0,5). 0 = hela ramen i ett "
                         "svep som hittills, 5 = muki01:s inter-byte-fördröjning.")
    ap.add_argument("--order", choices=("shuffle", "fixed"), default="shuffle",
                    help="variantordning. SHUFFLE (default) krävs för att kunna skilja "
                         "variantens effekt från försöksnumrets — med fast ordning är "
                         "de perfekt sammanblandade (belagt 2026-08-19).")
    ap.add_argument("--seed", type=int, default=None, help="seed för ordningen")
    args = ap.parse_args()

    seed = args.seed if args.seed is not None else int(time.time())
    rng = random.Random(seed)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    os.makedirs("logs", exist_ok=True)
    raw_path = f"logs/slabs_probe-{stamp}.raw.log"
    _log_fh = open(f"logs/slabs_probe-{stamp}.log", "w", encoding="utf-8")

    try:
        port = resolve_serial_port(args.serial)
    except FileNotFoundError as exc:
        say(f"ingen kabel hittad: {exc}")
        return 1

    say(f"SLABS-prob {stamp} — port {port} — ordning {args.order} (seed {seed})")
    say(f"rå TX/RX → {raw_path}")
    say("Kör STILLASTÅENDE med tändning på. SLABS vägrar comms >8–20 km/h.")

    transport = LoggingTransport(SerialTransport(port, timeout=1.0), logfile=raw_path)
    try:
        transport.open()
    except Exception as exc:  # noqa: BLE001 — trasig/upptagen port ska ge ett svar, inte en trace
        say(f"kunde inte öppna {port}: {type(exc).__name__}: {exc}")
        say("sitter kabeln i? kör någon annan (dashboarden) mot porten samtidigt?")
        return 1
    results: "list[tuple[str, str]]" = []
    try:
        if not args.no_td5:
            say("\n[kontext] läser motorn först (och släpper sessionen rent)")
            engine_context(transport, args.quiet)

        if not transport.is_open:   # property, inte metod
            say("porten är stängd efter kontextfasen — avbryter (det vore inget mätvärde)")
            return 1

        wgaps = [float(g) / 1000 for g in args.write_gaps.split(",") if g.strip()]
        for rnd in range(1, args.rounds + 1):
            combos = [(n, f, s, w) for (n, f, s) in VARIANTS for w in wgaps]
            if args.order == "shuffle":
                rng.shuffle(combos)
            say(f"\n[matris] varv {rnd}/{args.rounds} — {len(combos)} kombinationer")
            for name, functional, source, wgap in combos:
                label = f"{name} · P4 {wgap*1000:.0f}ms"
                slabs = try_init(transport, name, functional, source, wgap)
                results.append((label, "TRÄFF" if slabs else "tyst"))
                if slabs is not None:
                    hold(slabs, args.hold)
                    try:
                        slabs.release()  # 82 — lämna inte länken öppen
                    except Exception:  # noqa: BLE001
                        pass
                    say("\n=== SAMMANFATTNING ===")
                    for n, r in results:
                        say(f"  {r:6} {n}")
                    return 0
                quiet(args.quiet)
    except KeyboardInterrupt:
        say("\navbrutet")
    finally:
        try:
            transport.close()
        except Exception:  # noqa: BLE001
            pass

    say("\n=== SAMMANFATTNING ===")
    for n, r in results:
        say(f"  {r:6} {n}")
    say("ingen variant gav kontakt — se rålogg för exakta burstar")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
