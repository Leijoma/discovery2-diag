"""Passive K-line sniffer — listen to traffic between a (borrowed) tool and the ECU.

    PYTHONPATH=src python3 tools/sniff.py /dev/cu.usbserial-XXXX [gap_ms] [outfile] [seconds]

Connected via an OBD splitter (piggyback): the borrowed tool in one branch, this
listener in the other. Logs each message (split on silence gaps) with a timestamp +
annotation, and writes Ekaitza-style hex lines to the output file.

*** RX ONLY — the tool NEVER TRANSMITS. *** Transmitting would collide with the
borrowed tool and wreck the session. For GUARANTEED passivity: use ESP32 + L9637D
in pure RX (the KKL cable is a transceiver that listens when it isn't sending, but
doesn't drive the bus actively at rest). Run stationary (SLABS loses comms >8 km/h).
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
    print(f"PASSIVE sniff @ 10400 baud, gap {gap*1000:.0f} ms → {outfile}")
    print("RX ONLY — never transmits. Ctrl-C exits.\n")

    t0 = time.monotonic()
    cur = bytearray()
    msg_start = None
    last_byte = None
    prev_end = None
    n = 0
    log = open(outfile, "a", encoding="utf-8")
    try:
        while duration is None or (time.monotonic() - t0) < duration:
            b = ser.read(1)  # NEVER TRANSMIT — read only
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
    print(f"\n{n} messages logged → {outfile}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
