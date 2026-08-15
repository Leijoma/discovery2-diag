"""Passiv K-line-sniffer MED markörer — för sniffning av ett lånat verktyg (reference tool).

    PYTHONPATH=src python3 tools/sniff_session.py PORT [gap_ms] [utfil]

Som ``sniff.py`` (RX-only, ramar på tystnadsgap, Ekaitza-stil hexlogg) men med en
avgörande funktion: **du kan skriva markörer** som stämplas in i loggen i realtid.
Skriv t.ex. ``SLABS läs felkoder`` + Enter precis innan du kör funktionen i
reference tool-menyn → loggen får en tidsstämplad ``>>> ``-rad mellan ramarna. Då kan
bytes paras ihop med rätt åtgärd efteråt (läs/rensa-cykeln blir läsbar).

*** RX ONLY — sänder ALDRIG. *** Sniffern lyssnar bara; att sända skulle störa/
skada reference tool-sessionen. Kör stillastående, tändning på (SLABS tappar comms >8 km/h).

Kommandon medan den kör:  <valfri text> + Enter = markör · ``q`` + Enter = avsluta.
"""
import sys
import threading
import time

import serial

from d2diag.sniff import describe

_lock = threading.Lock()
_stop = threading.Event()


def _emit(fh, t0: float, text: str) -> None:
    """Skriv en rad till konsol + fil, trådsäkert."""
    line = f"[{time.monotonic() - t0:9.3f}s] {text}"
    with _lock:
        print(line, flush=True)
        fh.write(line + "\n")
        fh.flush()


def _sniffer(ser: "serial.Serial", fh, t0: float, gap: float) -> None:
    """RX-only-loop: samla bytes till ram på tystnadsgap, logga hex + annotering."""
    cur = bytearray()
    last = None
    while not _stop.is_set():
        b = ser.read(1)  # SÄND ALDRIG — bara läs
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
        _emit(fh, t0, bytes(cur).hex(" ") + "   (ofullständig vid avslut)")


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
        f"PASSIV sniff+markör @ 10400 baud → {outfile}\n"
        "RX ONLY — sänder aldrig. Skriv text+Enter = markör, 'q'+Enter = avsluta."
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
            _emit(fh, t0, f">>> {line.strip() or '(markör)'}")
    except KeyboardInterrupt:
        pass
    finally:
        _stop.set()
        th.join(timeout=1.0)
        with _lock:
            fh.write(f"=== SLUT {time.strftime('%H:%M:%S')} ===\n")
            fh.close()
        ser.close()
    print(f"\nklart → {outfile}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
