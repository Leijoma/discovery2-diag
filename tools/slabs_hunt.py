"""Utökat SLABS-jakttest — hela pin-7-matrisen i EN körning med gemensam logg.

    PYTHONPATH=src python3 tools/slabs_hunt.py PORT [profil] [logg-katalog]

profil:  quick  = bara kandidatadresser i alla lägen + sniff  (~3 min)
         full   = 0x01–0xFF (fast/func) + kandidat-slow + sniff (~15 min)  [default]

Kör stillastående, tändning på. Detta är sista uttömmande försöket med VÅR KKL
(pin 7) INNAN vi sniffar ett lånat verktyg. Faser:

  1. LÄNKKOLL   fast init mot motorn 0x13 → förväntar C1 57 8F. Bevisar att
               kabel/OBD/jord/tajming är OK, så att tystnad från SLABS är ETT SVAR
               (inte trasig länk). Sedan lång idle så motorsessionen dör.
  2. SNIFF      passiv RX-only ~20 s vid nyckel-på — BCU=gateway kan polla moduler
               på delade bussen → fånga SLABS adress/init UTAN att gissa. (K-line
               är ofta tyst utan testare; låg sannolikhet men gratis.)
  3. MATRIS     aktiv skanning i lägena fast-f1 / func-f1 / func-f7 / slow. Söker
               C1 (positivt) eller 7F (svar-men-avvisat) resp. 0x55 (slow-sync).
               Motorn 0x13 hoppas alltid över (öppen session maskerar bussen).

KREATIV VARIABEL: kör en gång med motorn AV (tändning på) och en gång med motorn
på TOMGÅNG — SLABS/EAS/SLS är då aktiva och modulen kan vara "vaken" på ett annat
sätt. Total tystnad i BÅDA → starkt stöd för pin-8-hypotesen; svar med motorn på
→ modulen kräver aktiv drift. Allt loggas per körning så de kan jämföras.
"""
import sys
import time

import serial

from d2diag.kline import TESTER_ADDRESS, KLine, encode
from d2diag.sniff import describe
from d2diag.transport import SerialTransport

# Kandidatadresser att alltid prova (även i quick). Kända ur research + vanliga
# KWP-ABS/kroppsadresser. 0x29/0x34 = pyTD5Tester/Android-fynd; övriga = gissningar.
CANDIDATES = [0x29, 0x34, 0x28, 0x38, 0x18, 0x08, 0x33, 0x14, 0x40, 0x44, 0x50]

MODES = ("fast-f1", "func-f1", "func-f7", "slow")


def build_frame(mode: str, addr: int) -> bytes:
    tester = 0xF1 if mode.endswith("f1") else 0xF7
    fmt = 0xC1 if mode.startswith("func") else 0x81   # funktionell vs fysisk
    b = bytes([fmt, addr, tester, 0x81])
    return b + bytes([sum(b) & 0xFF])


def log_line(fh, msg: str) -> None:
    print(msg)
    fh.write(msg + "\n")
    fh.flush()


def phase_linkcheck(port: str, fh) -> None:
    log_line(fh, "\n=== FAS 1: LÄNKKOLL (motor 0x13, förväntar C1 57 8F) ===")
    t = SerialTransport(port, timeout=1.0)
    t.open()
    try:
        time.sleep(3.0)
        kl = KLine(t, target=0x13)
        kl._fast_init_pulse()
        raw = kl.converse(b"\x81", addressed=True)
        echo = encode(b"\x81", target=0x13, source=TESTER_ADDRESS, addressed=True)
        idx = raw.find(echo)
        resp = raw[idx + len(echo):] if idx >= 0 else raw
        if 0xC1 in resp:
            log_line(fh, f"  ✓ LÄNK OK — motorn svarar C1  ({resp.hex(' ')})")
        else:
            log_line(fh, f"  ✗ INGEN C1 — kolla kabel/OBD/tändning FÖRST!  ({raw.hex(' ') or 'tyst'})")
    finally:
        t.close()
    log_line(fh, "  idle 15 s (låt motorsessionen dö)...")
    time.sleep(15)


def phase_sniff(port: str, fh, seconds: float = 20.0) -> None:
    log_line(fh, f"\n=== FAS 2: PASSIV SNIFF {seconds:.0f} s (RX-only, BCU kan polla) ===")
    ser = serial.serial_for_url(
        port, baudrate=10400, bytesize=8, parity="N", stopbits=1, timeout=0.007
    )
    t0 = time.monotonic()
    cur = bytearray()
    last = None
    n = 0
    try:
        while (time.monotonic() - t0) < seconds:
            b = ser.read(1)          # SÄND ALDRIG
            now = time.monotonic()
            if b:
                cur += b
                last = now
            elif cur and last is not None and (now - last) > 0.007:
                ann = describe(bytes(cur))
                log_line(fh, f"  [{now-t0:6.2f}s] {bytes(cur).hex(' ')}"
                             + (f"   ({ann})" if ann else ""))
                cur = bytearray()
                n += 1
    finally:
        ser.close()
    log_line(fh, f"  {n} meddelanden fångade" + (" — TYST (väntat utan testare)" if n == 0 else ""))


def phase_matrix(port: str, fh, addrs, do_slow: bool) -> list:
    log_line(fh, f"\n=== FAS 3: AKTIV MATRIS ({len(addrs)} adresser, lägen {', '.join(MODES)}) ===")
    hits = []
    t = SerialTransport(port, timeout=1.0)
    t.open()
    kl = KLine(t)
    try:
        for mode in MODES:
            if mode == "slow" and not do_slow:
                continue
            log_line(fh, f"\n  -- {mode} --")
            for addr in addrs:
                if addr == 0x13:
                    continue
                time.sleep(0.8)
                if mode == "slow":
                    raw = t.slow_init(addr)
                    if raw and 0x55 in raw:
                        log_line(fh, f"  0x{addr:02X}: SLOW-SYNC 0x55!  {raw.hex(' ')}")
                        hits.append((mode, addr, "0x55"))
                    continue
                frame = build_frame(mode, addr)
                kl._fast_init_pulse()
                kl._flush_input()
                t.send(frame)
                raw = kl._burst_read(0.06, 1.0)
                i = raw.find(frame)
                resp = raw[i + len(frame):] if i >= 0 else raw
                if 0xC1 in resp:
                    log_line(fh, f"  0x{addr:02X}: C1! POSITIVT  {resp.hex(' ')}")
                    hits.append((mode, addr, "C1"))
                elif 0x7F in resp:
                    log_line(fh, f"  0x{addr:02X}: 7F (svar!)  {resp.hex(' ')}")
                    hits.append((mode, addr, "7F"))
    finally:
        t.close()
    return hits


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    profile = sys.argv[2] if len(sys.argv) > 2 else "full"
    logdir = sys.argv[3] if len(sys.argv) > 3 else "logs"
    if profile not in ("quick", "full"):
        print(f"okänt profil: {profile} (quick|full)")
        return 2

    stamp = time.strftime("%Y%m%d-%H%M%S")
    import os
    os.makedirs(logdir, exist_ok=True)
    path = os.path.join(logdir, f"slabs_hunt-{stamp}.log")
    fh = open(path, "w", encoding="utf-8")

    if profile == "quick":
        addrs = CANDIDATES
        do_slow = True
        slow_addrs = CANDIDATES
    else:
        addrs = list(range(0x01, 0x100))
        do_slow = True
        slow_addrs = CANDIDATES   # slow är långsamt (2,6 s/adr) → bara kandidater

    log_line(fh, f"SLABS-JAKT ({profile}) — {stamp} — port {port}")
    log_line(fh, "Stillastående, tändning på. Ctrl-C avbryter (loggen sparas).")

    all_hits = []
    try:
        phase_linkcheck(port, fh)
        phase_sniff(port, fh)
        # fast/func över full lista, slow bara kandidater
        all_hits += phase_matrix(port, fh, addrs, do_slow=False)
        if do_slow:
            log_line(fh, f"\n  -- slow (bara kandidater, 2,6 s/adr) --")
            t = SerialTransport(port, timeout=1.0)
            t.open()
            try:
                for addr in slow_addrs:
                    time.sleep(0.8)
                    raw = t.slow_init(addr)
                    if raw and 0x55 in raw:
                        log_line(fh, f"  0x{addr:02X}: SLOW-SYNC 0x55!  {raw.hex(' ')}")
                        all_hits.append(("slow", addr, "0x55"))
            finally:
                t.close()
    except KeyboardInterrupt:
        log_line(fh, "\n[avbrutet av användaren]")

    log_line(fh, "\n=== SAMMANFATTNING ===")
    if all_hits:
        for mode, addr, tag in all_hits:
            log_line(fh, f"  TRÄFF  {mode:8s} 0x{addr:02X} = {tag}")
        log_line(fh, "  ⇒ ny modul svarar på pin 7! Notera läge+adress, bygg lager.")
    else:
        log_line(fh, "  inga träffar — SLABS tyst i alla lägen på pin 7.")
        log_line(fh, "  ⇒ nästa: (a) fysisk pin-koll (pin 8?), (b) sniffa lånat verktyg.")
    log_line(fh, f"\nlogg: {path}")
    fh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
