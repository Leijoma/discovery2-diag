#!/usr/bin/env python3
"""SLABS-tortyr (snäll): mät vad som faktiskt påverkar anslutningen.

`slabs_probe.py` svarar på "kommer vi in just nu?". Det här skriptet svarar på
"VAD gör att vi kommer in?" — genom att köra många korta försök och variera EN
sak i taget:

  * **tyst period före init** (``--gaps``) — hur länge måste bussen vara tyst?
  * **TD5-session före** (``--td5 both``) — värmer motorsessionen upp bussen?
  * **adressläge** — fysisk/F7, funktionell/F1, funktionell/F7

Ordningen **blandas** (seedad, seeden loggas) så att tid, temperatur och
batteridrift inte sammanfaller med ett visst tillstånd — annars mäter man klockan
i stället för hypotesen.

Snällt mot bilen: inga ställdon, korta hållperioder, och varje session avslutas
rent med ``82`` (StopCommunication) så nästa försök inte möts av ``7F 81 10``.

Resultatet skrivs som JSONL (en rad per försök) + en sammanfattning per faktor:

    PYTHONPATH=src python3 tools/slabs_torture.py --rounds 3
    PYTHONPATH=src python3 tools/slabs_torture.py --gaps 0,5,15,30 --hold 15
    PYTHONPATH=src python3 tools/slabs_torture.py --td5 both --rounds 4

Kör STILLASTÅENDE.

**Data ackumuleras mellan körningar.** Varje körning skriver en egen JSONL, och
``--summary`` slår ihop dem. Kör därför hellre flera KORTA block än ett långt —
motorn ska inte gå på tomgång i tjugo minuter. Med ``--max-minutes`` stannar
skriptet av sig självt och sammanfattar det som hanns med.

Statistiken kräver ungefär 50 försök per strömläge för att kunna skilja 30 % från
7 % (Fishers exakta test på materialet 2026-08-19 gav p = 0,27 — inte
signifikant). Det blir ~3 block à 5 minuter per läge.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import random
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from d2diag.kline import KLine, encode  # noqa: E402
from d2diag.kline.kline import KLineTimeout  # noqa: E402
from d2diag.kwp2000 import KWP2000  # noqa: E402
from d2diag.slabs import SLABS_ADDRESS, Slabs  # noqa: E402
from d2diag.td5 import Td5  # noqa: E402
from d2diag.transport import LoggingTransport, SerialTransport  # noqa: E402
from d2diag.web.sources import resolve_serial_port  # noqa: E402

# (funktionellt läge, testar-adress, måladress). Init-ramen är
# <fmt> <mål> <källa> 81 <cs>, där fmt = 0x81 fysiskt / 0xC1 funktionellt och
# checksumman är summan av de fyra föregående. Frågan vi mäter: måste det vara
# EN specifik följd, eller duger flera?
#
# Läget 2026-08-19: fysisk/F7, funktionell/F1 och funktionell/F7 har alla gett
# kontakt minst en gång — alltså krävs ingen enda specifik följd. fysisk/F1 har
# aldrig lyckats (0 av 8 försök), och broadcast till 0x33 är otestat: det är den
# ram muki01-referensen använder (C1 33 F1 81 66) och den adresserar alla
# OBD-moduler funktionellt i stället för SLABS fysiska adress 0x29.
VARIANTS = {
    "fysisk/F7":          (False, 0xF7, SLABS_ADDRESS),
    "funktionell/F1":     (True,  0xF1, SLABS_ADDRESS),
    "funktionell/F7":     (True,  0xF7, SLABS_ADDRESS),
    "fysisk/F1":          (False, 0xF1, SLABS_ADDRESS),
    "broadcast/33/F1":    (True,  0xF1, 0x33),   # muki01: C1 33 F1 81 66
    "broadcast/33/F7":    (True,  0xF7, 0x33),
}


def frame_for(variant: str) -> bytes:
    functional, source, target = VARIANTS[variant]
    return encode(b"\x81", target, source, addressed=True, functional=functional)


_log_fh = None
_jsonl = None


def say(msg: str) -> None:
    line = f"{dt.datetime.now().strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    if _log_fh:
        _log_fh.write(line + "\n")
        _log_fh.flush()


def record(**row) -> None:
    row["t"] = dt.datetime.now().isoformat(timespec="seconds")
    _jsonl.write(json.dumps(row, ensure_ascii=False) + "\n")
    _jsonl.flush()


def quiet(seconds: float) -> None:
    """Vänta UTAN att skicka något — varje byte nollställer modulens väntan."""
    if seconds > 0:
        time.sleep(seconds)


def td5_context(transport) -> "dict":
    """Kort TD5-session: läs rpm/fart/batteri, avsluta rent UTAN att stänga porten."""
    td5 = Td5(KWP2000(KLine(transport, target=0x13), tolerant=True))
    ctx: "dict" = {}
    try:
        td5.establish(attempts=2)
        vals = td5.read_all()
        ctx = {k: vals.get(k) for k in ("rpm", "speed", "battery")}
    except Exception as exc:  # noqa: BLE001
        ctx = {"td5_error": f"{type(exc).__name__}"}
    finally:
        try:
            td5.end_session()  # 20 + 82, porten delas med SLABS-försöken
        except Exception:  # noqa: BLE001
            pass
    return ctx


def attempt(transport, variant: str, hold: float) -> "dict":
    """Ett initförsök + kort hållperiod. Returnerar mätresultatet som dict."""
    functional, source, target = VARIANTS[variant]
    # Init går mot måladressen (0x29 eller broadcast 0x33); sessionen därefter är
    # oadresserad, så SLABS-objektet pratar med den modul som svarade.
    kwp = KWP2000(KLine(transport, target=target), tolerant=True)
    slabs = Slabs(kwp)
    try:
        kwp.start_communication(tolerant=True, functional=functional, source=source)
    except KLineTimeout:
        return {"result": "tyst"}
    except Exception as exc:  # noqa: BLE001
        return {"result": "lokalt_fel", "error": f"{type(exc).__name__}: {exc}"}
    # Kvittens: ett C1 kan vara vårt eget eko eller brus. 1A 8A avgör.
    try:
        slabs.read_ecu_id(0x8A)
    except Exception:  # noqa: BLE001
        return {"result": "falsk_c1"}

    reads = misses = 0
    t0 = time.monotonic()
    while time.monotonic() - t0 < hold:
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
        else:
            misses += 1
            if misses >= 3:
                break
    try:
        slabs.end_session()  # 82 — lämna inte länken öppen till nästa försök
    except Exception:  # noqa: BLE001
        pass
    return {"result": "träff", "reads": reads, "misses": misses,
            "held": round(time.monotonic() - t0, 1)}


def summarise(paths: "list[str]") -> int:
    """Läs ihop flera körningar och korstabulera träffkvot per strömläge.

    Poängen med tre lägen (motor igång / tändning med laddare / tändning utan):
    laddaren ger hög spänning UTAN att motorn går, vilket skiljer spänning från
    motorstatus — den enda fråga mätningen 2026-08-19 inte kunde svara på.
    """
    rows = []
    for pattern in paths:
        for path in sorted(glob.glob(pattern)):
            with open(path, encoding="utf-8") as fh:
                rows += [json.loads(line) for line in fh if line.strip()]
    if not rows:
        print("inga rader hittades")
        return 1

    def rate(rs):
        hits = sum(1 for r in rs if r.get("result") == "träff")
        return f"{hits:3}/{len(rs):-3} ({100 * hits / len(rs):3.0f}%)"

    print(f"{len(rows)} försök från {len(paths)} mönster\n")
    for key, title in (("label", "strömläge"), ("gap", "tyst period"),
                       ("variant", "variant"), ("td5_first", "TD5 före")):
        groups = defaultdict(list)
        for r in rows:
            groups[r.get(key)].append(r)
        if len(groups) < 2:
            continue
        print(f"  per {title}:")
        for k in sorted(groups, key=str):
            v = [r["battery"] for r in groups[k] if r.get("battery")]
            volt = f"   batteri {min(v):.2f}–{max(v):.2f} V" if v else ""
            print(f"    {str(k):16} {rate(groups[k])}{volt}")
        print()
    return 0


def main() -> int:
    global _log_fh, _jsonl
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--serial", default="auto")
    ap.add_argument("--rounds", type=int, default=3, help="varv genom hela matrisen")
    ap.add_argument("--gaps", default="5,15,30",
                    help="tysta perioder att testa, sekunder (default 5,15,30)")
    ap.add_argument("--hold", type=float, default=15.0,
                    help="hållperiod vid träff, sekunder (default 15)")
    ap.add_argument("--variants", default="fysisk/F7,funktionell/F1,funktionell/F7",
                    help=f"kommaseparerat. Tillgängliga: {', '.join(VARIANTS)}")
    ap.add_argument("--td5", choices=("never", "always", "both"), default="both",
                    help="TD5-session före SLABS: aldrig / alltid / båda (default both)")
    ap.add_argument("--seed", type=int, default=None, help="seed för ordningen")
    ap.add_argument("--max-minutes", type=float, default=None,
                    help="stoppa när så här många minuter gått (motorn ska inte gå "
                         "på tomgång i onödan). Resultatet sammanfattas ändå.")
    ap.add_argument("--td5-every", type=int, default=5,
                    help="läs motorkontext var N:e försök i stället för varje (default 5). "
                         "Sparar ~7 s per försök; åldern på kontexten loggas.")
    ap.add_argument("--label", default="",
                    help="strömläge för körningen, t.ex. motor / laddare / tandning. "
                         "Sparas på varje rad så körningarna kan jämföras efteråt.")
    ap.add_argument("--summary", nargs="+", metavar="JSONL",
                    help="summera tidigare körningar i stället för att mäta")
    args = ap.parse_args()

    if args.summary:
        return summarise(args.summary)

    gaps = [float(g) for g in args.gaps.split(",") if g.strip()]
    variants = [v.strip() for v in args.variants.split(",") if v.strip() in VARIANTS]
    td5_modes = {"never": [False], "always": [True], "both": [False, True]}[args.td5]
    seed = args.seed if args.seed is not None else int(time.time())
    rng = random.Random(seed)

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    os.makedirs("logs", exist_ok=True)
    _log_fh = open(f"logs/slabs_torture-{stamp}.log", "w", encoding="utf-8")
    _jsonl = open(f"logs/slabs_torture-{stamp}.jsonl", "w", encoding="utf-8")

    trials = [(g, v, t) for g in gaps for v in variants for t in td5_modes] * args.rounds
    rng.shuffle(trials)   # blandad ordning: tid/temperatur ska inte följa tillståndet

    # grov uppskattning: tyst period + init + ev. hållperiod + andning, plus TD5
    # -kontexten som numera bara läses var N:e försök
    per_td5 = 7.0 / max(1, args.td5_every)
    est = sum(g + 2 + args.hold * 0.3 + 1 + per_td5 for g, _, t in trials) / 60
    say(f"SLABS-tortyr {stamp} — seed {seed}" + (f" — läge: {args.label}" if args.label else ""))
    say(f"{len(trials)} försök · gap {gaps} · varianter {variants} · TD5 {td5_modes}")
    budget = f" (stoppar efter {args.max_minutes:.0f} min)" if args.max_minutes else ""
    say(f"uppskattad tid: ~{est:.0f} min{budget}. Stillastående. Ctrl-C sparar resultatet.")

    try:
        port = resolve_serial_port(args.serial)
    except FileNotFoundError as exc:
        say(f"ingen kabel: {exc}")
        return 1
    transport = LoggingTransport(SerialTransport(port, timeout=1.0),
                                 logfile=f"logs/slabs_torture-{stamp}.raw.log")
    try:
        transport.open()
    except Exception as exc:  # noqa: BLE001
        say(f"kunde inte öppna {port}: {exc}")
        return 1

    results = []
    t_start = time.monotonic()
    last_ctx: "dict" = {}
    last_ctx_at = 0.0
    try:
        for i, (gap, variant, use_td5) in enumerate(trials, 1):
            if args.max_minutes and (time.monotonic() - t_start) / 60 >= args.max_minutes:
                say(f"\ntidsbudgeten ({args.max_minutes:.0f} min) slut — stoppar här. "
                    f"Kör fler block senare och slå ihop med --summary.")
                break
            # Motorkontexten kostar ~7 s. Läs den var N:e försök och återanvänd
            # däremellan — spänningen rör sig långsamt, och åldern loggas.
            if use_td5 and (i == 1 or (i - 1) % max(1, args.td5_every) == 0):
                last_ctx = td5_context(transport)
                last_ctx_at = time.monotonic()
            ctx = dict(last_ctx) if use_td5 else {}
            if ctx:
                ctx["ctx_age"] = round(time.monotonic() - last_ctx_at, 1)
            quiet(gap)
            r = attempt(transport, variant, args.hold)
            row = {"n": i, "label": args.label, "gap": gap, "variant": variant,
                   "td5_first": use_td5, **ctx, **r}
            results.append(row)
            record(**row)
            rpm = ctx.get("rpm")
            motor = "?" if rpm is None else ("igång" if rpm else "av")
            say(f"[{i:3}/{len(trials)}] gap {gap:4.0f}s · {variant:15} · td5 "
                f"{'ja ' if use_td5 else 'nej'} · motor {motor:5} → {r['result']}"
                + (f"  ({r.get('reads')} läsningar)" if r.get("result") == "träff" else ""))
            if r["result"] == "lokalt_fel":
                say(f"   ✗ avbryter: {r.get('error')}")
                break
            quiet(1.0)  # låt bussen andas mellan försöken
    except KeyboardInterrupt:
        say("\navbrutet — sammanfattar det vi hann mäta")
    finally:
        try:
            transport.close()
        except Exception:  # noqa: BLE001
            pass

    say("\n=== SAMMANFATTNING ===")
    if not results:
        return 1

    def rate(rows):
        hits = sum(1 for r in rows if r["result"] == "träff")
        return f"{hits}/{len(rows)} ({100 * hits / len(rows):.0f}%)"

    for label, key in (("tyst period", "gap"), ("variant", "variant"),
                       ("TD5 före", "td5_first")):
        groups = defaultdict(list)
        for r in results:
            groups[r[key]].append(r)
        say(f"\n  per {label}:")
        for k in sorted(groups, key=str):
            say(f"    {str(k):16} {rate(groups[k])}")

    with_rpm = [r for r in results if r.get("rpm") is not None]
    if with_rpm:
        say("\n  per motorläge (bara försök med TD5-kontext):")
        for on in (True, False):
            rows = [r for r in with_rpm if bool(r["rpm"]) is on]
            if rows:
                v = [r["battery"] for r in rows if r.get("battery")]
                volt = f"  batteri {min(v):.2f}–{max(v):.2f} V" if v else ""
                say(f"    {'igång' if on else 'av':16} {rate(rows)}{volt}")

    held = [r for r in results if r["result"] == "träff"]
    if held:
        say(f"\n  stabilitet: {sum(r['reads'] for r in held)} läsningar, "
            f"{sum(r['misses'] for r in held)} tappade i {len(held)} sessioner")
    say(f"\nrådata: logs/slabs_torture-{stamp}.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
