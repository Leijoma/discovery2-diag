"""Uttömmande 5-baud slow-init-svep över HELA adressrymden + auto-verifiering.

    PYTHONPATH=src python3 tools/slow_sweep.py PORT [lo] [hi] [logg-katalog]

Bakgrund: chassimodulerna svarar på slow init (0x18/0x33/0x40 hittade), men det
förra svepet testade bara en kandidatlista. Detta sveper HELA 0x01–0xFF och letar
KOMPLETTA handskakningar (0x55 sync + KW1 KW2 + korrekt ``~address``-bekräftelse =
äkta modul, inte artefakt). Varje träff omverifieras sedan 3× med ≥8 s lucka
(session-lås kräver det) så resultatet är reproducerbart.

Faser:
  1. LÄNKKOLL   fast init mot motorn 0x13 → C1 (bevisar kabel/OBD/tajming).
  2. SNIFF      20 s passiv RX (BCU=gateway kan polla).
  3. SVEP       slow init 0x01–0xFF; klassa KOMPLETT / SYNC-bara / tyst.
  4. VERIFIERA  varje KOMPLETT/SYNC-träff 3× med 8 s lucka; KW/protokoll-tolkning.

Stillastående, TÄNDNING PÅ (tändningsmatade moduler som SLABS syns bara då).
Kör motor AV. ~11 min för svepet + ~1 min per träff. Ctrl-C sparar loggen.
"""
import os
import sys
import time

from d2diag.kline import TESTER_ADDRESS, KLine, encode
from d2diag.transport import SerialTransport


def protocol_of(kw1: int, kw2: int) -> str:
    if (kw1, kw2) == (0x08, 0x08):
        return "ISO 9141-2"
    if kw2 == 0x8F:
        return "KWP2000"
    return "okänt"


def classify(addr: int, raw: bytes):
    """→ (tagg, kw1, kw2). tagg ∈ KOMPLETT / SYNC / TYST."""
    if not raw or raw[0] != 0x55 or len(raw) < 3:
        return "TYST", None, None
    kw1, kw2 = raw[1], raw[2]
    complete = ((~addr) & 0xFF) in raw[3:]
    return ("KOMPLETT" if complete else "SYNC"), kw1, kw2


def log_line(fh, msg: str) -> None:
    print(msg)
    fh.write(msg + "\n")
    fh.flush()


def linkcheck(port: str, fh) -> None:
    log_line(fh, "\n=== FAS 1: LÄNKKOLL (motor 0x13 → C1) ===")
    t = SerialTransport(port, timeout=1.0)
    t.open()
    try:
        time.sleep(3)
        kl = KLine(t, target=0x13)
        kl._fast_init_pulse()
        raw = kl.converse(b"\x81", addressed=True)
        echo = encode(b"\x81", target=0x13, source=TESTER_ADDRESS, addressed=True)
        i = raw.find(echo)
        resp = raw[i + len(echo):] if i >= 0 else raw
        log_line(fh, f"  {'✓ LÄNK OK' if 0xC1 in resp else '✗ INGEN C1 (kolla kabel!)'}  {resp.hex(' ') or 'tyst'}")
    finally:
        t.close()
    log_line(fh, "  idle 15 s (motorsession dör)...")
    time.sleep(15)


def sniff(port: str, fh, seconds: float = 20.0) -> None:
    import serial
    from d2diag.sniff import describe
    log_line(fh, f"\n=== FAS 2: PASSIV SNIFF {seconds:.0f} s ===")
    ser = serial.serial_for_url(port, baudrate=10400, bytesize=8, parity="N", stopbits=1, timeout=0.007)
    t0 = time.monotonic(); cur = bytearray(); last = None; n = 0
    try:
        while (time.monotonic() - t0) < seconds:
            b = ser.read(1); now = time.monotonic()
            if b:
                cur += b; last = now
            elif cur and last and (now - last) > 0.007:
                log_line(fh, f"  {bytes(cur).hex(' ')}  ({describe(bytes(cur))})"); cur = bytearray(); n += 1
    finally:
        ser.close()
    log_line(fh, f"  {n} meddelanden" + ("  — TYST (väntat)" if n == 0 else ""))


def sweep(port: str, fh, lo: int, hi: int):
    n = hi - lo + 1
    log_line(fh, f"\n=== FAS 3: SLOW-SVEP 0x{lo:02X}–0x{hi:02X} (~{n*2.6/60:.0f} min) ===")
    t = SerialTransport(port, timeout=1.0)
    t.open()
    hits = []
    try:
        for addr in range(lo, hi + 1):
            raw = t.slow_init(addr)
            tag, kw1, kw2 = classify(addr, raw)
            if tag != "TYST":
                proto = protocol_of(kw1, kw2)
                log_line(fh, f"  0x{addr:02X}: {tag:8s} KW={kw1:#04x} {kw2:#04x} [{proto}]  {raw.hex(' ')}")
                hits.append((addr, tag, kw1, kw2))
            time.sleep(0.8)
    finally:
        t.close()
    return hits


def verify(port: str, fh, hits):
    if not hits:
        log_line(fh, "\n=== FAS 4: inga träffar att verifiera ===")
        return {}
    log_line(fh, f"\n=== FAS 4: VERIFIERA {len(hits)} träffar (3× / 8 s lucka) ===")
    t = SerialTransport(port, timeout=1.0)
    t.open()
    verdicts = {}
    try:
        for addr, _tag, _k1, _k2 in hits:
            log_line(fh, f"\n  == 0x{addr:02X} ==")
            oks = 0
            for i in range(3):
                raw = t.slow_init(addr)
                tag, kw1, kw2 = classify(addr, raw)
                if tag == "KOMPLETT":
                    oks += 1
                proto = protocol_of(kw1, kw2) if kw1 is not None else "-"
                log_line(fh, f"    #{i+1}: {tag:8s} {(raw.hex(' ') or 'tyst'):18s} [{proto}]")
                time.sleep(8)
            verdicts[addr] = oks
    finally:
        t.close()
    return verdicts


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    lo = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x01
    hi = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0xFF
    logdir = sys.argv[4] if len(sys.argv) > 4 else "logs"
    os.makedirs(logdir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(logdir, f"slow_sweep-{stamp}.log")
    fh = open(path, "w", encoding="utf-8")
    log_line(fh, f"SLOW-SVEP {stamp} — port {port} — 0x{lo:02X}–0x{hi:02X}")
    log_line(fh, "TÄNDNING PÅ, motor AV. Ctrl-C sparar loggen.")
    hits = []
    try:
        linkcheck(port, fh)
        sniff(port, fh)
        hits = sweep(port, fh, lo, hi)
        verdicts = verify(port, fh, hits)
    except KeyboardInterrupt:
        log_line(fh, "\n[avbrutet]")
        verdicts = {}
    log_line(fh, "\n=== SAMMANFATTNING ===")
    if hits:
        for addr, tag, kw1, kw2 in hits:
            oks = verdicts.get(addr)
            v = f"{oks}/3 komplett" if oks is not None else "ej verif."
            note = " ← KÄND (motorns OBD)" if addr == 0x33 else (" ← trolig BCU (permanent)" if addr == 0x40 else "")
            proto = protocol_of(kw1, kw2)
            real = "ÄKTA MODUL" if (oks or 0) >= 2 else ("osäker" if (oks or 0) == 1 else tag)
            log_line(fh, f"  0x{addr:02X} [{proto:11s}] {real}  ({v}){note}")
        log_line(fh, "  ⇒ nya adresser utöver 0x33(OBD)/0x40(BCU) = kandidat SLABS/EAT/SRS → sniffa verktyg för identitet.")
    else:
        log_line(fh, "  inga slow-svar alls — kontrollera tändning PÅ + länk.")
    log_line(fh, f"\nlogg: {path}")
    fh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
