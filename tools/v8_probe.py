#!/usr/bin/env python3
"""Read-only probe of the Discovery 2 V8 engine ECU (Bosch Motronic M5.2.1). This is test T-26.

Nobody has published how the M5.2.1 talks, so this tries the standard ways in turn. For each
one it records whether anything answers.

  1. ISO 9141-2 / ISO 14230 **5-baud init at 0x33**, the generic OBD-II address. The key
     bytes tell which protocol the ECU speaks. If it answers, ask for generic OBD: `01 00`
     (supported PIDs), `01 01` (MIL + DTC count) and `03` (stored DTCs).
  2. ISO 14230 **fast init, functional 0x33** (`C1 33 F1 81`), followed by the same generic
     OBD requests.
  3. ISO 14230 **fast init, physical**, to the candidate ECU addresses 0x10/0x11/0x12/0x01
     with tester F1, plus 0x10 with tester F7 (our Td5/SLABS tester address). Each address
     that answers C1 gets `10 81` (default session, which is the state the ECU is already
     in), `18 00 FF 00` (read DTCs by status) and `21 01` (one local identifier). Every
     link that opens is closed again with `82` StopCommunication.
  4. **BMW DS2** (9600 baud 8E1, no init) to 0x12, the DME address on BMW's M5.2. This step
     is a long shot, tried because BMW owned Rover when the M5.2.1 was developed. It sends
     only `00` (identification).

Nothing here writes, clears or actuates. There is no `14`/`31`/`2E`/`30`/`3B` and no
SecurityAccess. The ECU identification that would carry the VIN (`1A 90`, mode 09) is left out
on purpose, so the log can be shared as is.

Ignition ON (position II), engine off, car stationary. The probe takes about 1.5 minutes.

    PYTHONPATH=src python3 tools/v8_probe.py auto
    PYTHONPATH=src python3 tools/v8_probe.py /dev/cu.usbserial-XXXX [--only slow|fast|phys|ds2]

It writes a log to `logs/v8_probe_<time>.txt` in the repo. Send that file back.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from d2diag.kline.frame import checksum, encode  # noqa: E402

OBD_FUNCTIONAL = 0x33
TESTER_OBD = 0xF1          # the ISO 15031 external test equipment address
TESTER_LR = 0xF7           # what Testbook/our Td5 and SLABS work use
# (target, source). The address list comes from other Bosch ECUs (0x10/0x11/0x01 on ME7, 0x12 =
# BMW DME); none of it is sourced for the M5.2.1 (docs/rover-v8/README.md).
PHYSICAL_CANDIDATES = [(0x10, TESTER_OBD), (0x11, TESTER_OBD), (0x12, TESTER_OBD),
                       (0x01, TESTER_OBD), (0x10, TESTER_LR)]
GENERIC_OBD = [(bytes([0x01, 0x00]), "01 00 supported PIDs"),
               (bytes([0x01, 0x01]), "01 01 MIL + DTC count"),
               (bytes([0x03]), "03 stored DTCs")]
PHYSICAL_READS = [(bytes([0x10, 0x81]), "10 81 default session"),
                  (bytes([0x18, 0x00, 0xFF, 0x00]), "18 00 FF 00 DTCs by status"),
                  (bytes([0x21, 0x01]), "21 01 local identifier 01")]
# A sanity guard for this file: none of these service IDs may ever be sent from here.
_FORBIDDEN_SIDS = {0x14, 0x27, 0x2E, 0x2F, 0x30, 0x31, 0x3B, 0x3D, 0x34, 0x36, 0x09}
SILENCE_S = 6.0            # > P3max (5 s): any link we opened has timed out before the next try


# ---- pure helpers (tested in tests/test_v8_probe.py) --------------------------------- #
def iso9141_frame(data: bytes) -> bytes:
    """ISO 9141-2 OBD request: `68 6A F1 <data> <cs>` (header fixed by ISO 15031-5)."""
    body = bytes([0x68, 0x6A, TESTER_OBD]) + bytes(data)
    return body + bytes([checksum(body)])


def ds2_frame(address: int, data: bytes) -> bytes:
    """BMW DS2: `<addr> <total length> <data> <xor of all previous bytes>`."""
    body = bytes([address, len(data) + 3]) + bytes(data)
    x = 0
    for b in body:
        x ^= b
    return body + bytes([x])


def interpret_keybytes(kw1: int, kw2: int) -> str:
    """Which protocol the 5-baud key bytes announce (ISO 9141-2 §6, ISO 14230-2 §5.2.4)."""
    if kw1 == kw2 and kw1 in (0x08, 0x94):
        return f"ISO 9141-2 (generic OBD, key bytes {kw1:02X} {kw2:02X})"
    if kw2 == 0x8F:
        return f"ISO 14230 / KWP2000 (key bytes {kw1:02X} 8F)"
    return f"unknown protocol (key bytes {kw1:02X} {kw2:02X})"


def strip_echo(burst: bytes, sent: bytes) -> bytes:
    """A half-duplex K-line echoes what we send. Drop it if the burst starts with it."""
    i = burst.find(sent)
    return burst[i + len(sent):] if i >= 0 else burst


def classify(reply: bytes, request: bytes) -> str:
    """'positive' if the response SID (request SID + 0x40) appears, 'negative' on 7F <sid>,
    'silent' if nothing came, otherwise 'noise'. Tolerant: it searches the burst, as
    KWP2000(tolerant=True) does for cheap cables."""
    if not reply:
        return "silent"
    sid = request[0]
    if bytes([0x7F, sid]) in reply:
        return "negative"
    if (sid + 0x40) & 0xFF in reply:
        return "positive"
    return "noise"


def _guard(data: bytes) -> None:
    if data and data[0] in _FORBIDDEN_SIDS:
        raise RuntimeError(f"v8_probe refuses to send service {data[0]:02X} (read-only tool)")


# ---- the probe ----------------------------------------------------------------------- #
class Probe:
    def __init__(self, port: str, log_path: str) -> None:
        from d2diag.transport import SerialTransport
        self.port = port
        self.t = SerialTransport(port, timeout=0.5)
        self.log = open(log_path, "w", encoding="utf-8")
        self.results: "list[tuple[str, str]]" = []

    def say(self, msg: str = "") -> None:
        print(msg)
        self.log.write(msg + "\n")
        self.log.flush()

    def note(self, step: str, outcome: str) -> None:
        self.results.append((step, outcome))

    def burst(self, frame: bytes, overall: float = 1.5, gap: float = 0.12) -> bytes:
        """Send a frame byte by byte (P4 = 5 ms) and read the whole answer burst raw."""
        self.t.reset_input_buffer()
        for b in frame:
            self.t.send(bytes([b]))
            time.sleep(0.005)
        buf = bytearray()
        start = time.monotonic()
        while time.monotonic() - start < overall:
            chunk = self.t.receive(64, timeout=gap)
            if chunk:
                buf += chunk
            elif buf:
                break
        return strip_echo(bytes(buf), frame)

    def ask(self, label: str, data: bytes, frame: bytes) -> str:
        _guard(data)
        reply = self.burst(frame)
        verdict = classify(reply, data)
        self.say(f"    {label:30} → {verdict:8} {reply.hex(' ') or '-'}")
        return verdict

    def quiet(self) -> None:
        self.say(f"  (silence {SILENCE_S:.0f} s)")
        time.sleep(SILENCE_S)

    # 1 -------------------------------------------------------------------------------- #
    def slow_init_33(self) -> None:
        self.say("\n[1] 5-baud init at 0x33 (generic OBD)")
        raw = self.t.slow_init(OBD_FUNCTIONAL)
        kw = self.t.parse_slow_init(raw)
        self.say(f"    raw {raw.hex(' ') or '-'}")
        if kw is None:
            self.say("    no 0x55 sync: nothing answered the 5-baud address")
            self.note("5-baud 0x33", "silent")
            return
        proto = interpret_keybytes(*kw)
        self.say(f"    answered: {proto}")
        self.note("5-baud 0x33", proto)
        time.sleep(0.06)  # P3min before the first request
        iso = kw[0] == kw[1] and kw[0] in (0x08, 0x94)
        for data, label in GENERIC_OBD:
            frame = iso9141_frame(data) if iso else encode(
                data, OBD_FUNCTIONAL, TESTER_OBD, addressed=True, functional=True)
            v = self.ask(label, data, frame)
            self.note(f"5-baud {label}", v)
            time.sleep(0.06)

    # 2 -------------------------------------------------------------------------------- #
    def _fast_init(self, target: int, source: int, functional: bool) -> "bytes | None":
        from d2diag.kline import KLine
        from d2diag.kline.kline import KLineError
        kl = KLine(self.t, target=target, source=source, init_idle=0.3)
        try:
            c1 = kl.fast_init_tolerant(b"\x81", functional=functional, source=source)
        except KLineError as exc:
            self.say(f"    no C1: {exc}")
            return None
        finally:
            self.say(f"    pulse {kl.last_pulse}")
        self.say(f"    C1 answer: {c1.hex(' ')}")
        return c1

    def fast_functional_33(self) -> None:
        self.say("\n[2] fast init, functional C1 33 F1 81 (generic OBD over KWP2000)")
        c1 = self._fast_init(OBD_FUNCTIONAL, TESTER_OBD, functional=True)
        self.note("fast 0x33 functional", "C1 " + c1.hex(" ") if c1 else "silent")
        if not c1:
            return
        time.sleep(0.06)
        for data, label in GENERIC_OBD:
            v = self.ask(label, data, encode(data, OBD_FUNCTIONAL, TESTER_OBD,
                                             addressed=True, functional=True))
            self.note(f"fast-33 {label}", v)
            time.sleep(0.06)

    # 3 -------------------------------------------------------------------------------- #
    def fast_physical(self) -> None:
        for i, (target, source) in enumerate(PHYSICAL_CANDIDATES):
            if i:
                self.quiet()
            self.say(f"\n[3] fast init, physical 81 {target:02X} {source:02X} 81")
            c1 = self._fast_init(target, source, functional=False)
            step = f"fast {target:02X}/{source:02X}"
            self.note(step, "C1 " + c1.hex(" ") if c1 else "silent")
            if not c1:
                continue
            time.sleep(0.06)
            for data, label in PHYSICAL_READS:
                v = self.ask(label, data, encode(data, target, source, addressed=True))
                self.note(f"{step} {label}", v)
                time.sleep(0.06)
            # Close the link we opened (CLAUDE.md: `82` ends the fast-init link on every module).
            self.ask("82 StopCommunication", b"\x82", encode(b"\x82", target, source, addressed=True))

    # 4 -------------------------------------------------------------------------------- #
    def ds2(self) -> None:
        import serial  # pyserial — DS2 needs 9600 8E1, which SerialTransport doesn't do
        self.say("\n[4] BMW DS2 at 9600 8E1 to 0x12 (identification 00)")
        self.t.close()
        frame = ds2_frame(0x12, b"\x00")
        with serial.Serial(self.port, 9600, parity=serial.PARITY_EVEN, timeout=0.3) as s:
            s.reset_input_buffer()
            s.write(frame)
            s.flush()
            time.sleep(0.6)
            raw = s.read(256)
        reply = strip_echo(raw, frame)
        self.say(f"    sent {frame.hex(' ')} → {reply.hex(' ') or '-'}")
        ok = len(reply) >= 3 and reply[0] == 0x12 and reply[2] == 0xA0  # A0 = DS2 "OK"
        self.note("DS2 0x12 ident", "positive" if ok else ("noise" if reply else "silent"))
        self.t.open()

    def run(self, only: "str | None") -> None:
        self.t.open()
        self.say(f"v8_probe {_dt.datetime.now().isoformat(timespec='seconds')} port {self.port}")
        steps = [("slow", self.slow_init_33), ("fast", self.fast_functional_33),
                 ("phys", self.fast_physical), ("ds2", self.ds2)]
        try:
            first = True
            for key, fn in steps:
                if only and key != only:
                    continue
                if not first:
                    self.quiet()
                first = False
                try:
                    fn()
                except Exception as exc:  # one failing step must not hide the others
                    self.say(f"    step failed: {type(exc).__name__}: {exc}")
                    self.note(key, f"error {type(exc).__name__}")
        finally:
            self.t.close()
        self.say("\nSummary")
        for step, outcome in self.results:
            self.say(f"  {step:40} {outcome}")
        self.log.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("port", help="serial device, or 'auto' to detect the cable")
    ap.add_argument("--only", choices=["slow", "fast", "phys", "ds2"], help="run one step only")
    args = ap.parse_args()
    from d2diag.ports import resolve_serial_port
    port = resolve_serial_port(args.port)
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    os.makedirs(os.path.join(root, "logs"), exist_ok=True)  # logs/ is gitignored
    log = os.path.join(root, "logs", f"v8_probe_{_dt.datetime.now():%Y%m%d_%H%M%S}.txt")
    print(f"Using cable at {port}. Ignition ON (II), engine off, car stationary.")
    Probe(port, log).run(args.only)
    print(f"\nLog saved: {os.path.abspath(log)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
