"""Passive K-line sniffer WITH markers — for sniffing a borrowed tool (reference tool).

    PYTHONPATH=src python3 tools/sniff_session.py PORT [gap_ms] [outfile]

Like ``sniff.py`` (RX-only, frames on silence gaps, Ekaitza-style hex log) but with
one crucial feature: **you can type markers** that get stamped into the log in real
time. Type e.g. ``SLABS read faults`` + Enter just before you run the function in the
reference tool's menu → the log gets a timestamped ``>>> `` line between the frames.
Then the bytes can be paired with the right action afterwards (the read/clear cycle
becomes readable).

*** RX ONLY — NEVER transmits. *** The sniffer only listens; transmitting would
disturb/damage the reference tool session. Run stationary, ignition on (SLABS loses comms >8 km/h).

Commands while running:  <any text> + Enter = marker · ``q`` + Enter = quit.
"""
import sys
import threading
import time

import serial

from d2diag.sniff import describe

_lock = threading.Lock()
_stop = threading.Event()


def _emit(fh, t0: float, text: str) -> None:
    """Write a line to console + file, thread-safely."""
    line = f"[{time.monotonic() - t0:9.3f}s] {text}"
    with _lock:
        print(line, flush=True)
        fh.write(line + "\n")
        fh.flush()


def _sniffer(ser: "serial.Serial", fh, t0: float, gap: float) -> None:
    """RX-only loop: collect bytes into a frame on silence gaps, log hex + annotation."""
    cur = bytearray()
    last = None
    while not _stop.is_set():
        b = ser.read(1)  # NEVER TRANSMIT — read only
        now = time.monotonic()
        if b:
            cur += b
            last = now
        elif cur and last is not None and (now - last) > gap:
            ann = describe(bytes(cur))
            _emit(fh, t0, bytes(cur).hex(" ") + (f"   ({ann})" if ann else ""))
            cur = bytearray()
            last = None
    if cur:
        _emit(fh, t0, bytes(cur).hex(" ") + "   (incomplete at exit)")


def main() -> int:
    import os
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    gap = (float(sys.argv[2]) / 1000.0) if len(sys.argv) > 2 else 0.007
    if len(sys.argv) > 3:
        outfile = sys.argv[3]
    else:
        os.makedirs("logs", exist_ok=True)
        outfile = os.path.join("logs", f"reference_tool_sniff-{time.strftime('%Y%m%d-%H%M%S')}.log")

    ser = serial.serial_for_url(
        port, baudrate=10400, bytesize=8, parity="N", stopbits=1, timeout=gap
    )
    fh = open(outfile, "a", encoding="utf-8")
    t0 = time.monotonic()

    banner = (
        f"PASSIVE sniff+marker @ 10400 baud → {outfile}\n"
        "RX ONLY — never transmits. Type text+Enter = marker, 'q'+Enter = quit."
    )
    print(banner)
    fh.write(f"=== SESSION {time.strftime('%Y-%m-%d %H:%M:%S')} — port {port} ===\n")
    fh.flush()

    th = threading.Thread(target=_sniffer, args=(ser, fh, t0, gap), daemon=True)
    th.start()

    try:
        while True:
            try:
                line = input()
            except EOFError:
                break
            if line.strip().lower() in ("q", "quit", "exit"):
                break
            _emit(fh, t0, f">>> {line.strip() or '(marker)'}")
    except KeyboardInterrupt:
        pass
    finally:
        _stop.set()
        th.join(timeout=1.0)
        with _lock:
            fh.write(f"=== END {time.strftime('%H:%M:%S')} ===\n")
            fh.close()
        ser.close()
    print(f"\ndone → {outfile}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
