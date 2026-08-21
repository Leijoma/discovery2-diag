#!/usr/bin/env python3
"""BCU-prob: koppla upp mot Valeo BCU och läs EKA-koden. **Endast läsning.**

Målet är EKA-koden (Emergency Key Access) — fyra siffror som matas in via
förardörrlåset om fjärrnyckeln slutar fungera, och som låter en kringgå
startspärren. Vi läser den; vi skriver aldrig.

Underlaget:
  * **Adress `0x40`, 5-baud SLOW init.** Vår adressjakt 2026-08-05 fick komplett
    handskakning med KWP2000-nycklar `E5 8F`. Att det ÄR BCU:n är en slutsats —
    modulen svarar med tändningen av, och BCU:n är den enda permanent matade
    D2-modulen. Skriptet frågar därför modulen vem den är (`1A xx`) innan något
    annat.
  * **EKA läses med `21 CC`** — belagt ur sniffen 2026-08-09, där den ramen
    skickades exakt en gång under operatörsmarkören "read set eka".
  * **Svarsformatet är INTE belagt** (sniffens svar var trasigt). Skriptet visar
    råbytes och båda rimliga tolkningarna så du kan jämföra mot en känd kod.

⚠️ **Tändningscykel krävs.** BCU:n går in i diagnostikläge vid en tändnings-
övergång. Reference tool ber operatören slå AV tändningen, trycka en tangent, och
sedan slå PÅ den. Skriptet guidar dig genom samma sekvens.

    PYTHONPATH=src python3 tools/bcu_probe.py
    PYTHONPATH=src python3 tools/bcu_probe.py --address 0x18   # testa annan kandidat
    PYTHONPATH=src python3 tools/bcu_probe.py --no-prompt       # hoppa över guidningen
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from d2diag.bcu import BCU_ADDRESS, Bcu  # noqa: E402
from d2diag.bcu.bcu import EKA_LID, find_digits  # noqa: E402
from d2diag.kline import KLine  # noqa: E402
from d2diag.kwp2000 import KWP2000  # noqa: E402
from d2diag.kwp2000.kwp2000 import NegativeResponse  # noqa: E402
from d2diag.transport import LoggingTransport, SerialTransport  # noqa: E402
from d2diag.web.sources import resolve_serial_port  # noqa: E402

_log_fh = None


def say(msg: str = "") -> None:
    line = f"{dt.datetime.now().strftime('%H:%M:%S')} {msg}" if msg else ""
    print(line, flush=True)
    if _log_fh:
        _log_fh.write(line + "\n")
        _log_fh.flush()


def ascii_of(data: bytes) -> str:
    """Läsbara tecken ur ett svar — så en modul som anger delnummer syns direkt."""
    txt = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
    return txt if any(c.isalnum() for c in txt) else ""


def main() -> int:
    global _log_fh
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--serial", default="auto")
    ap.add_argument("--address", default=hex(BCU_ADDRESS),
                    help=f"diagnosadress (default {hex(BCU_ADDRESS)}; 0x18 är den andra "
                         "slow-init-kandidaten ur adressjakten)")
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--no-prompt", action="store_true",
                    help="hoppa över tändningscykel-guidningen")
    ap.add_argument("--expect", metavar="KOD",
                    help="känd EKA-kod (t.ex. 1234) att söka efter i svaret. Med facit "
                         "behöver formatet inte gissas — skriptet visar exakt hur koden "
                         "är kodad. Skickas som argument och sparas ALDRIG i repot.")
    args = ap.parse_args()

    addr = int(args.address, 0)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    os.makedirs("logs", exist_ok=True)
    raw_path = f"logs/bcu_probe-{stamp}.raw.log"
    _log_fh = open(f"logs/bcu_probe-{stamp}.log", "w", encoding="utf-8")

    say(f"BCU-prob {stamp} — adress 0x{addr:02X}, 5-baud slow init")
    say(f"rå TX/RX → {raw_path}")
    say("ENDAST LÄSNING: inga skrivningar, ingen nyckelprogrammering.")

    if not args.no_prompt:
        say()
        say("BCU:n går in i diagnostikläge vid en TÄNDNINGSÖVERGÅNG.")
        input("  1. Slå AV tändningen helt, tryck sedan Enter …")
        input("  2. Slå PÅ tändningen (läge II), tryck sedan Enter …")
        say("tack — kör init direkt medan modulen är mottaglig")

    try:
        port = resolve_serial_port(args.serial)
    except FileNotFoundError as exc:
        say(f"ingen kabel hittad: {exc}")
        return 1

    transport = LoggingTransport(SerialTransport(port, timeout=1.0), logfile=raw_path)
    try:
        transport.open()
    except Exception as exc:  # noqa: BLE001
        say(f"kunde inte öppna {port}: {type(exc).__name__}: {exc}")
        return 1

    bcu = Bcu(KWP2000(KLine(transport, target=addr), tolerant=True))
    try:
        try:
            kw = bcu.establish(attempts=args.attempts, progress=lambda m: say(f"  {m}"))
        except Exception as exc:  # noqa: BLE001
            say(f"\n✗ ingen kontakt: {exc}")
            say("  Prova: cykla tändningen igen, eller --address 0x18.")
            return 1
        say(f"\n✓ UPPKOPPLAD — keybytes {kw[0]:02X} {kw[1]:02X}")

        # 1) Vem är du? Avgör om 0x40-gissningen håller.
        say("\n[identitet] frågar modulen vem den är (1A xx)")
        ident = bcu.identify()
        if not ident:
            say("  inga 1A-svar — modulen stöder kanske inte ReadEcuIdentification")
        for opt, data in ident.items():
            say(f"  1A {opt}: {data[:24].hex(' ')}   {ascii_of(data[:24])}")

        # 1b) SecurityAccess-SEED. Reference tool gör 27 01 → 27 02 DIREKT efter
        # uppkoppling (sniff 2026-08-09), innan varje läsning. Utan unlock returnerar
        # BCU:n en fast platshållare på allt (belagt i bilen 2026-08-20). Vi kan inte
        # skicka nyckeln — Valeo seed→key är okänd — men vi fångar seeden så den
        # kan matas till framtida keygen-arbete.
        say("\n[security] hämtar en seed (27 01) — vi kan inte låsa upp än, bara fånga")
        try:
            seed = bcu._kwp.request_seed(0x01)
            say(f"  seed: {seed.hex(' ')}  ← spara loggen; behövs för Valeo-keygen")
        except Exception as exc:  # noqa: BLE001
            say(f"  seed-begäran svarade inte ({type(exc).__name__})")

        # 2) Målet: EKA. Utan unlock är detta troligen en platshållare.
        say(f"\n[EKA] läser 21 {EKA_LID:02X}  (låst utan SecurityAccess)")
        try:
            eka = bcu.read_eka()
        except NegativeResponse as exc:
            say(f"  ✗ nekat: {exc}")
            if exc.nrc == 0x33:
                say("  securityAccessDenied → EKA kräver SecurityAccess (27 01/27 02).")
                say("  Sniffen visar att reference tool gör det, men seed→key-algoritmen")
                say("  för BCU:n är okänd. Hämtar en seed så vi har data att jobba med:")
                try:
                    seed = bcu._kwp.request_seed(0x01)
                    say(f"    seed: {seed.hex(' ')}  ← spara, behövs för keygen-arbetet")
                except Exception as sexc:  # noqa: BLE001
                    say(f"    seed-begäran misslyckades: {type(sexc).__name__}")
            return 1
        except Exception as exc:  # noqa: BLE001
            say(f"  ✗ läsfel: {type(exc).__name__}: {exc}")
            return 1

        say(f"  rå: {eka['raw'].hex(' ')}")
        say(f"  tolkat som en siffra per byte:   {eka['bytes']}")
        say(f"  tolkat som två siffror per byte: {eka['nibbles']}")
        say(f"  rimlig tolkning: {eka['plausible']}")

        if args.expect:
            digits = [int(c) for c in args.expect if c.isdigit()]
            hit = find_digits(eka["raw"], digits)
            if hit:
                say(f"\n  ✓ FACIT HITTAT i svaret: kodning '{hit['encoding']}' "
                    f"på offset {hit['offset']} ({hit['bytes']})")
                say("    → formatet är därmed belagt. Skriv in det i "
                    "references/valeo_bcu_capabilities.md (men INTE koden).")
            else:
                say("\n  ✗ facit hittades inte — troligen en LÅST platshållare.")
                say("    BCU:n gav samma data på 1A som på 21 CC → EKA är gated bakom")
                say("    SecurityAccess (27 01/27 02), som vi ännu inte kan göra (Valeo")
                say("    seed→key okänd). Seeden ovan är första pusselbiten.")
        else:
            say("\n  Kör med --expect <kod> om du vet koden, så avgörs formatet direkt.")
        return 0
    finally:
        try:
            bcu.release()   # 20 + 82 — lämna inte en session öppen på delad buss
        except Exception:  # noqa: BLE001
            pass
        try:
            transport.close()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    raise SystemExit(main())
