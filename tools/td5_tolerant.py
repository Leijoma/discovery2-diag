"""Tolerant Td5 one-shot: burst-läsning (muki01-stil) + full unlock-sekvens.

    PYTHONPATH=src python3 tools/td5_tolerant.py /dev/cu.usbserial-12345678

Kombinerar det bästa av två världar:
- muki01/live_raw: läs HELA svarsbursten, sök efter framgångsbyten, avvisa
  INTE på checksumma (brusskadad ram med rätt byte i räknas ändå).
- Ekaitza-sniffen: den bevisade sekvensen  10 A0 -> seed -> keygen -> key -> 21 xx.

Nyckeln: en brusskadad C1-burst (t.ex. 03 c1 38 0e ...) INNEHÅLLER 0xC1, så vi
ser "session öppen" direkt och slipper init-om-loopen som annars låser ECU:n.
Tändning på, motorn AV.
"""
import sys
import time

import serial

from d2diag.td5.identifiers import LIDS, signals_for_lid
from d2diag.td5.keygen import key_bytes_from_seed


def _checksum(b: bytes) -> int:
    return sum(b) & 0xFF


def _frame(data: bytes) -> bytes:
    """Oadresserad sessionsram: <data...> + checksumma (data börjar med längdbyten)."""
    return data + bytes([_checksum(data)])


def _burst(ser, frame: bytes, gap: float = 0.06, overall: float = 1.5) -> bytes:
    ser.reset_input_buffer()
    ser.write(frame)
    ser.flush()
    buf = bytearray()
    t0 = time.monotonic()
    last = None
    while time.monotonic() - t0 < overall:
        n = ser.in_waiting
        if n:
            buf += ser.read(n)
            last = time.monotonic()
        elif last is not None and time.monotonic() - last > gap:
            break
        else:
            time.sleep(0.002)
    return bytes(buf)


def _fast_init_low(ser, low: float = 0.025) -> None:
    orig = ser.baudrate
    ser.baudrate = round(9 / low)
    ser.write(b"\x00")
    ser.flush()
    ser.baudrate = orig
    ser.reset_input_buffer()


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    ser = serial.serial_for_url(
        port, baudrate=10400, bytesize=8, parity="N", stopbits=1, timeout=0.05
    )

    print("bus-idle 5 s (som referensens delay(5000))...")
    time.sleep(5)
    ser.reset_input_buffer()

    # ---- fast init: sök 0xC1 permissivt i bursten ----
    ok = False
    for i in range(10):
        ser.reset_input_buffer()
        _fast_init_low(ser)
        time.sleep(0.03)
        raw = _burst(ser, bytes([0x81, 0x13, 0xF7, 0x81, 0x0C]))
        if 0xC1 in raw:
            ci = raw.find(0xC1)
            print(f"init {i + 1}: C1 hittad  (kringliggande {raw[ci:ci+3].hex(' ')})  raw={raw.hex(' ')}")
            ok = True
            break
        if 0x7F in raw:
            print(f"init {i + 1}: 7F (session öppen) — tyst 8 s")
            time.sleep(8)
            continue
        print(f"init {i + 1}: {raw.hex(' ') or 'tomt'}")
    if not ok:
        print(">> Ingen C1. Kör en tändningscykel och kör om.")
        ser.close()
        return 1

    # ---- StartDiagnosticSession 10 A0 -> sök 0x50 ----
    raw = _burst(ser, _frame(bytes([0x02, 0x10, 0xA0])))
    print(f"10 A0 -> {'50 OK' if 0x50 in raw else 'INGET 50'}  raw={raw.hex(' ')}")

    # ---- SecurityAccess seed 27 01 -> sök 67 01 <seed> ----
    raw = _burst(ser, _frame(bytes([0x02, 0x27, 0x01])))
    si = raw.find(bytes([0x67, 0x01]))
    if si < 0 or len(raw) < si + 4:
        print(f"27 01 -> ingen seed (67 01)  raw={raw.hex(' ')}")
        ser.close()
        return 1
    seed = raw[si + 2:si + 4]
    print(f"27 01 -> seed {seed.hex(' ')}  raw={raw.hex(' ')}")

    # ---- keygen + skicka nyckel 27 02 -> sök 67 02 ----
    key = key_bytes_from_seed(seed[0], seed[1])
    raw = _burst(ser, _frame(bytes([0x04, 0x27, 0x02, key[0], key[1]])))
    unlocked = raw.find(bytes([0x67, 0x02])) >= 0
    print(f"27 02 -> {'UPPLÅST' if unlocked else 'ingen 67 02'}  (key {key.hex(' ')})  raw={raw.hex(' ')}")

    # ---- läs LID:er permissivt ----
    print("\n--- livedata (permissiv, upplåst) ---")
    for lid in LIDS:
        raw = _burst(ser, _frame(bytes([0x02, 0x21, lid])))
        idx = raw.find(bytes([0x61, lid]))
        data = raw[idx + 2:] if idx >= 0 else b""
        print(f"21 {lid:02X}  raw={raw.hex(' ')}" + ("" if idx >= 0 else "  (inget 61)"))
        for sig in signals_for_lid(lid):
            if sig.fits(data):
                print(f"    {sig.name:16} {sig.decode(data):9.2f} {sig.unit}")
        time.sleep(0.05)

    ser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
