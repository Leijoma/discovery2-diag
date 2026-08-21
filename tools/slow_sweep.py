"""Exhaustive 5-baud slow-init sweep over the WHOLE address space + auto-verification.

    PYTHONPATH=src python3 tools/slow_sweep.py PORT [lo] [hi] [log-dir]

Background: the chassis modules respond to slow init (0x18/0x33/0x40 found), but the
previous sweep only tested a candidate list. This sweeps the WHOLE 0x01–0xFF and looks
for COMPLETE handshakes (0x55 sync + KW1 KW2 + correct ``~address`` acknowledgement =
real module, not an artifact). Each hit is then re-verified 3x with a >=8 s gap
(the session lock requires it) so the result is reproducible.

Phases:
  1. LINK CHECK fast init against the engine 0x13 → C1 (proves cable/OBD/timing).
  2. SNIFF      20 s passive RX (BCU=gateway may poll).
  3. SWEEP      slow init 0x01–0xFF; classify COMPLETE / SYNC-only / silent.
  4. VERIFY     each COMPLETE/SYNC hit 3x with an 8 s gap; KW/protocol interpretation.

Stationary, IGNITION ON (ignition-fed modules like SLABS only show up then).
Run engine OFF. ~11 min for the sweep + ~1 min per hit. Ctrl-C saves the log.
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
    return "unknown"


def classify(addr: int, raw: bytes):
    """→ (tag, kw1, kw2). tag ∈ COMPLETE / SYNC / SILENT."""
    if not raw or raw[0] != 0x55 or len(raw) < 3:
        return "SILENT", None, None
    kw1, kw2 = raw[1], raw[2]
    complete = ((~addr) & 0xFF) in raw[3:]
    return ("COMPLETE" if complete else "SYNC"), kw1, kw2


def log_line(fh, msg: str) -> None:
    print(msg)
    fh.write(msg + "\n")
    fh.flush()


def linkcheck(port: str, fh) -> None:
    log_line(fh, "\n=== PHASE 1: LINK CHECK (engine 0x13 → C1) ===")
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
        log_line(fh, f"  {'✓ LINK OK' if 0xC1 in resp else '✗ NO C1 (check the cable!)'}  {resp.hex(' ') or 'silent'}")
    finally:
        t.close()
    log_line(fh, "  idle 15 s (engine session dies)...")
    time.sleep(15)


def sniff(port: str, fh, seconds: float = 20.0) -> None:
    import serial
    from d2diag.sniff import describe
    log_line(fh, f"\n=== PHASE 2: PASSIVE SNIFF {seconds:.0f} s ===")
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
    log_line(fh, f"  {n} messages" + ("  — SILENT (expected)" if n == 0 else ""))


def sweep(port: str, fh, lo: int, hi: int):
    n = hi - lo + 1
    log_line(fh, f"\n=== PHASE 3: SLOW SWEEP 0x{lo:02X}–0x{hi:02X} (~{n*2.6/60:.0f} min) ===")
    t = SerialTransport(port, timeout=1.0)
    t.open()
    hits = []
    try:
        for addr in range(lo, hi + 1):
            raw = t.slow_init(addr)
            tag, kw1, kw2 = classify(addr, raw)
            if tag != "SILENT":
                proto = protocol_of(kw1, kw2)
                log_line(fh, f"  0x{addr:02X}: {tag:8s} KW={kw1:#04x} {kw2:#04x} [{proto}]  {raw.hex(' ')}")
                hits.append((addr, tag, kw1, kw2))
            time.sleep(0.8)
    finally:
        t.close()
    return hits


def verify(port: str, fh, hits):
    if not hits:
        log_line(fh, "\n=== PHASE 4: no hits to verify ===")
        return {}
    log_line(fh, f"\n=== PHASE 4: VERIFY {len(hits)} hits (3x / 8 s gap) ===")
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
                if tag == "COMPLETE":
                    oks += 1
                proto = protocol_of(kw1, kw2) if kw1 is not None else "-"
                log_line(fh, f"    #{i+1}: {tag:8s} {(raw.hex(' ') or 'silent'):18s} [{proto}]")
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
    log_line(fh, f"SLOW SWEEP {stamp} — port {port} — 0x{lo:02X}–0x{hi:02X}")
    log_line(fh, "IGNITION ON, engine OFF. Ctrl-C saves the log.")
    hits = []
    try:
        linkcheck(port, fh)
        sniff(port, fh)
        hits = sweep(port, fh, lo, hi)
        verdicts = verify(port, fh, hits)
    except KeyboardInterrupt:
        log_line(fh, "\n[aborted]")
        verdicts = {}
    log_line(fh, "\n=== SUMMARY ===")
    if hits:
        for addr, tag, kw1, kw2 in hits:
            oks = verdicts.get(addr)
            v = f"{oks}/3 complete" if oks is not None else "not verified"
            note = " ← KNOWN (engine OBD)" if addr == 0x33 else (" ← likely BCU (permanent)" if addr == 0x40 else "")
            proto = protocol_of(kw1, kw2)
            real = "REAL MODULE" if (oks or 0) >= 2 else ("uncertain" if (oks or 0) == 1 else tag)
            log_line(fh, f"  0x{addr:02X} [{proto:11s}] {real}  ({v}){note}")
        log_line(fh, "  ⇒ new addresses beyond 0x33(OBD)/0x40(BCU) = candidate SLABS/EAT/SRS → sniff a tool for identity.")
    else:
        log_line(fh, "  no slow responses at all — check ignition ON + link.")
    log_line(fh, f"\nlog: {path}")
    fh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
