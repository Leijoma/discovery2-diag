"""Läs ESP32 K-line-sniffens (kline_sniff.ino) USB-serial + markörer → loggfil.

    python3 tools/esp32_read.py [PORT] [utfil]

ESP32:an ramar och tidsstämplar själv och skickar hex-rader @115200. Detta loggar
dem + låter dig skriva **markörer** i realtid (text+Enter → `>>> `-rad) så bytes kan
paras ihop med reference tool-åtgärden (läs/rensa-cykeln). ``q``+Enter avslutar.

Default-port /dev/cu.usbserial-0001 (ESP32). OBS: när porten öppnas kan ESP32:an
auto-resettas (den skriver då sin banner igen) — helt normalt.
"""
import os
import sys
import threading
import time

import serial

_lock = threading.Lock()
_stop = threading.Event()


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/cu.usbserial-0001"
    if len(sys.argv) > 2:
        outfile = sys.argv[2]
    else:
        os.makedirs("logs", exist_ok=True)
        outfile = os.path.join("logs", f"esp32_sniff-{time.strftime('%Y%m%d-%H%M%S')}.log")

    ser = serial.serial_for_url(port, baudrate=115200, timeout=0.2)
    fh = open(outfile, "a", encoding="utf-8")
    print(f"ESP32-sniff @ {port} → {outfile}")
    print("Skriv text+Enter = markör (t.ex. 'SLABS läs felkoder'). q+Enter = avsluta.")
    fh.write(f"=== SESSION {time.strftime('%Y-%m-%d %H:%M:%S')} — {port} ===\n")
    fh.flush()

    def reader():
        while not _stop.is_set():
            try:
                line = ser.readline()
            except serial.SerialException:
                break
            if line:
                s = line.decode("ascii", "replace").rstrip()
                with _lock:
                    print(s, flush=True)
                    fh.write(s + "\n")
                    fh.flush()

    th = threading.Thread(target=reader, daemon=True)
    th.start()
    try:
        while True:
            try:
                m = input()
            except EOFError:
                break
            if m.strip().lower() in ("q", "quit", "exit"):
                break
            stamp = f">>> {m.strip() or '(markör)'}"
            with _lock:
                print(stamp, flush=True)
                fh.write(stamp + "\n")
                fh.flush()
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
