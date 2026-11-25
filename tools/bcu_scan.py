"""BCU read-only auth-boundary scan — how much does the Valeo BCU give up unauthenticated?

The reference tool does SecurityAccess (`27 01`/`27 02`) immediately after connecting and
before every read, so the 2026-08-09 sniff cannot tell us which reads actually *require*
it. This tool answers that directly: connect read-only, sweep a set of `21 xx`
identifiers WITHOUT SecurityAccess, and classify each response. The Valeo seed→key is
unknown (see `references/valeo_bcu_capabilities.md`), so we never send a key — the
question here is only what is legible without one.

    PYTHONPATH=src python3 tools/bcu_scan.py --serial auto
    PYTHONPATH=src python3 tools/bcu_scan.py --serial auto --full          # also sweep 21 00..FF
    PYTHONPATH=src python3 tools/bcu_scan.py --serial auto --stimulus "open the driver door"

⚠️ **READ ONLY.** Sends only `21 xx` (ReadDataByLocalIdentifier), `1A xx`
(ReadEcuIdentification) and `27 01` (request seed — no side effect). It never writes
(`3B`), never actuates (`2F`/`30`/`31`), and never sends a key (`27 02`). A locked BCU
must not be poked with guessed keys (attempt counter / brick risk).

Method notes (why it is built this way):

* **Two interleaved passes.** BCU init and reads are flaky (~1 in 4 attempts times out).
  A single "no response" is therefore not proof of gating. Each LID is read twice in a
  shuffled order; a LID that answers once and times out once is comms-flaky, not
  auth-gated, and is reported as INCONSISTENT rather than lumped with the real refusals.
* **Seed decoy detection.** `21 CC` (EKA) without SecurityAccess returns the *current
  rolling seed*, not the code (proven 2026-08-20). We fetch a seed up front and flag any
  positive response that simply echoes it, so a decoy is never mistaken for real data.
* **Differential (`--stimulus`).** A constant positive response can still be a
  placeholder. The only proof that a LID carries *real* live data is that its bytes move
  when a physical input changes. With `--stimulus` the tool reads a baseline, asks you to
  change one input, reads again, and reports which LIDs' bytes actually moved.
"""
import argparse
import os
import random
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from d2diag.bcu import BCU_ADDRESS, Bcu  # noqa: E402
from d2diag.kline import KLine  # noqa: E402
from d2diag.kline.kline import KLineError  # noqa: E402
from d2diag.kwp2000 import KWP2000  # noqa: E402
from d2diag.kwp2000.kwp2000 import KWP2000Error, NegativeResponse  # noqa: E402
from d2diag.ports import resolve_serial_port  # noqa: E402
from d2diag.transport import SerialTransport  # noqa: E402
from d2diag.transport.logging_transport import LoggingTransport  # noqa: E402

# LIDs the reference tool actually read from the BCU (sniff 2026-08-09), grouped by role.
# See references/valeo_bcu_capabilities.md.
INPUT_LIDS = [0x2C, 0x2D] + list(range(0xD8, 0xEA))        # switch/lighting/door bitfields
SETTING_LIDS = [0xC6, 0xC7, 0xCA, 0xCB, 0xCE, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xEB]
EKA_LID = 0xCC
IDENTITY_OPTS = [0x80, 0x8A, 0x8B, 0x8D, 0x9B]

# ---- response classification --------------------------------------------- #
DATA = "DATA"            # positive, plausibly real
SEED = "SEED-DECOY"      # positive but equals the current SecurityAccess seed
DENIED = "DENIED"        # 7F .. 33 securityAccessDenied
NRC = "NRC"              # other negative response (e.g. 31 requestOutOfRange = no such LID)
NORESP = "NO-RESPONSE"   # timeout / unreadable burst


def _read_once(kwp: KWP2000, lid: int, seed: "bytes | None") -> "tuple[str, object]":
    """One read-only `21 lid`. Returns (bucket, detail) and never writes."""
    try:
        data = kwp.read_local_identifier(lid)
    except NegativeResponse as e:
        return (DENIED if e.nrc == 0x33 else NRC, e.nrc)
    except (KWP2000Error, KLineError):
        return (NORESP, None)
    if seed is not None and bytes(seed) and bytes(seed) in bytes(data):
        return (SEED, data)
    return (DATA, data)


def _scan_pass(kwp: KWP2000, lids: "list[int]", seed: "bytes | None",
               gap: float) -> "dict[int, tuple[str, object]]":
    out: "dict[int, tuple[str, object]]" = {}
    order = list(lids)
    random.shuffle(order)            # de-correlate LID identity from position/time in the session
    for lid in order:
        out[lid] = _read_once(kwp, lid, seed)
        time.sleep(gap)
    return out


def _merge(p1: "dict", p2: "dict") -> "dict[int, dict]":
    """Combine two passes: agree → stable; disagree → INCONSISTENT (comms-flaky)."""
    merged = {}
    for lid in sorted(set(p1) | set(p2)):
        b1, d1 = p1.get(lid, (NORESP, None))
        b2, d2 = p2.get(lid, (NORESP, None))
        if b1 == b2:
            merged[lid] = {"bucket": b1, "stable": True, "data": d1 if d1 is not None else d2}
        elif NORESP in (b1, b2) and DATA in (b1, b2):
            # one good read, one dropout → real data behind a flaky link, keep the good one
            good = d1 if b1 == DATA else d2
            merged[lid] = {"bucket": DATA, "stable": False, "data": good, "note": "1 dropout"}
        else:
            merged[lid] = {"bucket": "INCONSISTENT", "stable": False,
                           "data": None, "note": f"{b1}/{b2}"}
    return merged


def _hx(d) -> str:
    return d.hex(" ") if isinstance(d, (bytes, bytearray)) else str(d)


def _report(title: str, lids: "list[int]", merged: "dict", log) -> None:
    log(f"\n[{title}]")
    for lid in lids:
        m = merged.get(lid)
        if not m:
            continue
        b = m["bucket"]
        tag = "" if m["stable"] else f"  (⚠ {m.get('note','unstable')})"
        if b in (DATA, SEED):
            log(f"  21 {lid:02X}  {b:12} {_hx(m['data'])}{tag}")
        elif b == NRC:
            log(f"  21 {lid:02X}  {b:12} NRC 0x{m['data']:02X}{tag}")
        else:
            log(f"  21 {lid:02X}  {b}{tag}")


def _summary(merged: "dict", log) -> None:
    counts: "dict[str, int]" = {}
    for m in merged.values():
        counts[m["bucket"]] = counts.get(m["bucket"], 0) + 1
    log("\n[summary] " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    readable = [lid for lid, m in merged.items() if m["bucket"] == DATA]
    log(f"  readable without auth: {len(readable)} LIDs "
        + (", ".join(f"{x:02X}" for x in sorted(readable)) if readable else "(none)"))


def _differential(before: "dict", after: "dict", log) -> None:
    log("\n[differential] LIDs whose bytes MOVED on the stimulus (= real live data):")
    moved = False
    for lid in sorted(before):
        b, a = before[lid], after.get(lid)
        if not a or b["bucket"] != DATA or a["bucket"] != DATA:
            continue
        if b["data"] != a["data"]:
            moved = True
            log(f"  21 {lid:02X}  {_hx(b['data'])}  →  {_hx(a['data'])}")
    if not moved:
        log("  (nothing moved — either the stimulus hit no BCU input, or these LIDs are static)")


def main() -> int:
    ap = argparse.ArgumentParser(description="BCU read-only auth-boundary scan (no writes)")
    ap.add_argument("--serial", default="auto", help="serial port, or 'auto'")
    ap.add_argument("--full", action="store_true",
                    help="also sweep 21 00..FF to find LIDs the reference tool never touched")
    ap.add_argument("--stimulus", metavar="TEXT",
                    help="differential mode: read baseline, prompt to change ONE input, read again")
    ap.add_argument("--gap", type=float, default=0.08, help="delay between reads (s)")
    ap.add_argument("--no-prompt", action="store_true",
                    help="skip the ignition-cycle prompt (BCU already in diagnostic mode)")
    args = ap.parse_args()

    port = resolve_serial_port(args.serial)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    os.makedirs("logs", exist_ok=True)
    raw_path = os.path.join("logs", f"bcu_scan-{stamp}.raw.log")

    def log(msg: str = "") -> None:
        print(msg)

    inner = LoggingTransport(SerialTransport(port, timeout=1.0), logfile=raw_path)
    kline = KLine(inner, target=BCU_ADDRESS)
    kwp = KWP2000(kline, tolerant=True)
    bcu = Bcu(kwp)

    log(f"BCU read-only scan — {stamp}  port={port}")
    log(f"raw TX/RX → {raw_path}")
    log("READ ONLY: only 21/1A/27-01 are sent — no writes, no key, no actuators.")

    if not args.no_prompt:
        input("\nIgnition OFF, press a key on the fob, then turn ignition ON. Enter when ready… ")

    bcu.open()
    try:
        log("\nEstablishing (5-baud slow init to 0x40)…")
        kw = bcu.establish(progress=lambda m: log(f"  {m}"))
        log(f"  ✓ connected, keybytes {kw[0]:02X} {kw[1]:02X}")

        # Identity (for context) + a fresh seed so we can spot the 21 CC decoy.
        ident = bcu.identify(tuple(IDENTITY_OPTS))
        log("\n[identity] 1A xx:")
        for opt, data in ident.items():
            log(f"  1A {opt}: {_hx(data)}")
        seed = None
        try:
            seed = kwp.request_seed(0x01)
            log(f"\n[seed] 27 01 → {_hx(seed)}  (used to flag 21 CC decoys)")
        except (KWP2000Error, KLineError):
            log("\n[seed] 27 01 gave no clean seed this session (continuing without decoy check)")

        lids = INPUT_LIDS + SETTING_LIDS + [EKA_LID]
        if args.full:
            lids = sorted(set(lids) | set(range(0x00, 0x100)))

        log("\nPass 1/2…")
        p1 = _scan_pass(kwp, lids, seed, args.gap)
        log("Pass 2/2 (shuffled)…")
        p2 = _scan_pass(kwp, lids, seed, args.gap)
        merged = _merge(p1, p2)

        _report("inputs (switch/lighting/door)", INPUT_LIDS, merged, log)
        _report("settings", SETTING_LIDS, merged, log)
        _report("eka", [EKA_LID], merged, log)
        if args.full:
            extra = [l for l in sorted(merged) if l not in lids or l not in
                     (INPUT_LIDS + SETTING_LIDS + [EKA_LID])]
            _report("other (full sweep)", extra, merged, log)
        _summary(merged, log)

        if args.stimulus:
            input(f"\nDIFFERENTIAL: now {args.stimulus}, then press Enter… ")
            a1 = _scan_pass(kwp, INPUT_LIDS, seed, args.gap)
            a2 = _scan_pass(kwp, INPUT_LIDS, seed, args.gap)
            after = _merge(a1, a2)
            _differential(merged, after, log)

    finally:
        bcu.release()
        log(f"\nDone. Raw log: {raw_path}")
        log("Paste the summary + differential here to update references/valeo_bcu_capabilities.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
