"""Extended SLABS hunt — the whole pin-7 matrix in ONE run with a shared log.

    PYTHONPATH=src python3 tools/slabs_hunt.py PORT [profile] [log-dir]

profile: quick  = candidate addresses only, in all modes + sniff  (~3 min)
         full   = 0x01–0xFF (fast/func) + candidate slow + sniff (~15 min)  [default]

Run stationary, ignition on. This is the last exhaustive attempt with OUR KKL
(pin 7) BEFORE we sniff a borrowed tool. Phases:

  1. LINK CHECK fast init against the engine 0x13 → expects C1 57 8F. Proves that
               cable/OBD/ground/timing are OK, so that silence from SLABS is A
               RESPONSE (not a broken link). Then a long idle so the engine session dies.
  2. SNIFF      passive RX-only ~20 s at key-on — BCU=gateway may poll modules
               on the shared bus → capture the SLABS address/init WITHOUT guessing.
               (K-line is often silent without a tester; low odds but free.)
  3. MATRIX     active scan in the modes fast-f1 / func-f1 / func-f7 / slow. Looks
               for C1 (positive) or 7F (responded-but-rejected), resp. 0x55 (slow-sync).
               The engine 0x13 is always skipped (an open session masks the bus).

CREATIVE VARIABLE: run once with the engine OFF (ignition on) and once with the
engine IDLING — SLABS/EAS/SLS are then active and the module may be "awake" in a
different way. Total silence in BOTH → strong support for the pin-8 hypothesis; a
response with the engine on → the module requires active operation. Everything is
logged per run so they can be compared.
"""
import sys
import time

import serial

from d2diag.kline import TESTER_ADDRESS, KLine, encode
from d2diag.sniff import describe
from d2diag.transport import SerialTransport

# Candidate addresses to always try (even in quick). Known from research + common
# KWP-ABS/body addresses. 0x29/0x34 = pyTD5Tester/Android finds; the rest = guesses.
CANDIDATES = [0x29, 0x34, 0x28, 0x38, 0x18, 0x08, 0x33, 0x14, 0x40, 0x44, 0x50]

MODES = ("fast-f1", "func-f1", "func-f7", "slow")


def build_frame(mode: str, addr: int) -> bytes:
    tester = 0xF1 if mode.endswith("f1") else 0xF7
    fmt = 0xC1 if mode.startswith("func") else 0x81   # functional vs physical
    b = bytes([fmt, addr, tester, 0x81])
    return b + bytes([sum(b) & 0xFF])


def log_line(fh, msg: str) -> None:
    print(msg)
    fh.write(msg + "\n")
    fh.flush()


def phase_linkcheck(port: str, fh) -> None:
    log_line(fh, "\n=== PHASE 1: LINK CHECK (engine 0x13, expecting C1 57 8F) ===")
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
            log_line(fh, f"  ✓ LINK OK — engine responds C1  ({resp.hex(' ')})")
        else:
            log_line(fh, f"  ✗ NO C1 — check cable/OBD/ignition FIRST!  ({raw.hex(' ') or 'silent'})")
    finally:
        t.close()
    log_line(fh, "  idle 15 s (let the engine session die)...")
    time.sleep(15)


def phase_sniff(port: str, fh, seconds: float = 20.0) -> None:
    log_line(fh, f"\n=== PHASE 2: PASSIVE SNIFF {seconds:.0f} s (RX-only, BCU may poll) ===")
    ser = serial.serial_for_url(
        port, baudrate=10400, bytesize=8, parity="N", stopbits=1, timeout=0.007
    )
    t0 = time.monotonic()
    cur = bytearray()
    last = None
    n = 0
    try:
        while (time.monotonic() - t0) < seconds:
            b = ser.read(1)          # NEVER TRANSMIT
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
    log_line(fh, f"  {n} messages captured" + (" — SILENT (expected without a tester)" if n == 0 else ""))


def phase_matrix(port: str, fh, addrs, do_slow: bool) -> list:
    log_line(fh, f"\n=== PHASE 3: ACTIVE MATRIX ({len(addrs)} addresses, modes {', '.join(MODES)}) ===")
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
                    log_line(fh, f"  0x{addr:02X}: C1! POSITIVE  {resp.hex(' ')}")
                    hits.append((mode, addr, "C1"))
                elif 0x7F in resp:
                    log_line(fh, f"  0x{addr:02X}: 7F (response!)  {resp.hex(' ')}")
                    hits.append((mode, addr, "7F"))
    finally:
        t.close()
    return hits


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    profile = sys.argv[2] if len(sys.argv) > 2 else "full"
    logdir = sys.argv[3] if len(sys.argv) > 3 else "logs"
    if profile not in ("quick", "full"):
        print(f"unknown profile: {profile} (quick|full)")
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
        slow_addrs = CANDIDATES   # slow is slow (2.6 s/addr) → candidates only

    log_line(fh, f"SLABS HUNT ({profile}) — {stamp} — port {port}")
    log_line(fh, "Stationary, ignition on. Ctrl-C aborts (the log is saved).")

    all_hits = []
    try:
        phase_linkcheck(port, fh)
        phase_sniff(port, fh)
        # fast/func over the full list, slow only candidates
        all_hits += phase_matrix(port, fh, addrs, do_slow=False)
        if do_slow:
            log_line(fh, f"\n  -- slow (candidates only, 2.6 s/addr) --")
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
        log_line(fh, "\n[aborted by user]")

    log_line(fh, "\n=== SUMMARY ===")
    if all_hits:
        for mode, addr, tag in all_hits:
            log_line(fh, f"  HIT    {mode:8s} 0x{addr:02X} = {tag}")
        log_line(fh, "  ⇒ a new module responds on pin 7! Note mode+address, build a layer.")
    else:
        log_line(fh, "  no hits — SLABS silent in all modes on pin 7.")
        log_line(fh, "  ⇒ next: (a) physical pin check (pin 8?), (b) sniff a borrowed tool.")
    log_line(fh, f"\nlog: {path}")
    fh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
