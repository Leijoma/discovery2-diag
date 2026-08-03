"""Passiv K-line-sniffer — lyssna på trafik mellan ett (lånat) verktyg och ECU:n.

    PYTHONPATH=src python3 tools/sniff.py /dev/cu.usbserial-XXXX [gap_ms] [utfil] [sekunder]

Kopplas in via en OBD-splitter (piggyback): lånat verktyg i ena grenen, denna
lyssnare i den andra. Loggar varje meddelande (uppdelat på tystnadsgap) med
tidsstämpel + annotering, och skriver Ekaitza-stil hex-rader till utfil.

*** RX ONLY — verktyget SÄNDER ALDRIG. *** Att sända skulle krocka med det lånade
verktyget och förstöra sessionen. För GARANTERAD passivitet: använd ESP32 + L9637D
i ren RX (KKL-kabeln är en transceiver som lyssnar när den inte sänder, men driver
inte bussen aktivt i vila). Kör stillastående (SLABS tappar comms >8 km/h).
"""
import sys
import time

import serial

from d2diag.sniff import describe


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    gap = (float(sys.argv[2]) / 1000.0) if len(sys.argv) > 2 else 0.007
    outfile = sys.argv[3] if len(sys.argv) > 3 else "sniff.log"
    duration = float(sys.argv[4]) if len(sys.argv) > 4 else None

    ser = serial.serial_for_url(
        port, baudrate=10400, bytesize=8, parity="N", stopbits=1, timeout=gap
    )
    print(f"PASSIV sniff @ 10400 baud, gap {gap*1000:.0f} ms → {outfile}")
    print("RX ONLY — sänder aldrig. Ctrl-C avslutar.\n")

    t0 = time.monotonic()
    cur = bytearray()
    msg_start = None
    last_byte = None
    prev_end = None
    n = 0
    log = open(outfile, "a", encoding="utf-8")
    try:
        while duration is None or (time.monotonic() - t0) < duration:
            b = ser.read(1)  # SÄND ALDRIG — bara läs
            now = time.monotonic()
            if b:
                if msg_start is None:
                    msg_start = now
                cur += b
                last_byte = now
            elif cur and last_byte is not None and (now - last_byte) > gap:
                gb = None if prev_end is None else (msg_start - prev_end)
                ann = describe(bytes(cur))
                gbs = f" gap=+{gb*1000:5.0f}ms" if gb is not None else " " * 12
                extra = f"   ({ann})" if ann else ""
                print(f"[{msg_start-t0:8.3f}s{gbs}] {bytes(cur).hex(' ')}{extra}")
                log.write(bytes(cur).hex() + "\n")
                log.flush()
                prev_end = last_byte
                cur = bytearray()
                msg_start = None
                n += 1
    except KeyboardInterrupt:
        pass
    finally:
        if cur:
            log.write(bytes(cur).hex() + "\n")
        log.close()
        ser.close()
    print(f"\n{n} meddelanden loggade → {outfile}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
