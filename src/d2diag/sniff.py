"""Passiv K-line-sniffning — ram-uppdelning och annotering (offline-analys).

K-line är en enda tråd, halvduplex: både testarens frågor och ECU:ns svar syns
på samma tråd. En passiv RX-lyssnare fångar alltså hela samtalet. Meddelanden
skiljs åt på **tystnadsgap** mellan bytes. De rena funktionerna här (ingen I/O)
används av ``tools/sniff.py`` och är enhetstestbara.
"""
from __future__ import annotations

from .kline.frame import ChecksumError, FrameError, decode

# Tjänste-ID → namn (KWP2000). Positivt svar = SID | 0x40.
_SERVICES = {
    0x10: "StartDiagnosticSession",
    0x11: "EcuReset",
    0x14: "ClearDiagnosticInformation",
    0x18: "ReadDtcByStatus",
    0x1A: "ReadEcuId",
    0x20: "StopDiagnosticSession",
    0x21: "ReadDataByLocalId",
    0x22: "ReadDataByCommonId",
    0x27: "SecurityAccess",
    0x2E: "WriteDataByCommonId",
    0x2F: "InputOutputControl",
    0x31: "StartRoutineByLocalId",
    0x33: "RequestRoutineResults",
    0x3B: "WriteDataByLocalId",
    0x3E: "TesterPresent",
    0x81: "StartCommunication",
    0x82: "StopCommunication",
    0x83: "AccessTimingParameters",
}


def frame_by_gaps(byte_samples, gap: float) -> "list[dict]":
    """Dela en tidsstämplad byte-ström i meddelanden på tystnadsgap.

    ``byte_samples``: itererbar av ``(t, b)`` (t = monoton tid i sekunder, b = byte).
    Nytt meddelande börjar när ``t - förra_t > gap``. Returnerar en lista av
    ``{"start", "end", "gap_before", "data"}`` (gap_before = tystnad före
    meddelandet, ``None`` för det första).
    """
    msgs: "list[dict]" = []
    cur = bytearray()
    start = None
    last = None
    for t, b in byte_samples:
        if last is not None and cur and (t - last) > gap:
            msgs.append({"start": start, "end": last, "data": bytes(cur)})
            cur = bytearray()
            start = None
        if start is None:
            start = t
        cur.append(b & 0xFF)
        last = t
    if cur:
        msgs.append({"start": start, "end": last, "data": bytes(cur)})
    for i, m in enumerate(msgs):
        m["gap_before"] = None if i == 0 else round(m["start"] - msgs[i - 1]["end"], 4)
    return msgs


def describe(message: bytes) -> str:
    """Best-effort-annotering av ett sniffat meddelande (rå ram-bytes).

    Försöker avkoda ramen; annars gissa på råbytes. Namnger tjänst/SID, positivt
    svar, negativt svar (7F+NRC) och slow-init-sync (0x55).
    """
    if not message:
        return ""
    if message[0] == 0x55:
        return "slow-init sync (0x55)"
    try:
        payload = decode(message).data
    except (FrameError, ChecksumError):
        payload = message  # okänt/trasigt format — gissa på råbytes
    if not payload:
        return ""
    sid = payload[0]
    if sid == 0x7F:
        svc = _SERVICES.get(payload[1], f"{payload[1]:#04x}") if len(payload) >= 2 else "?"
        nrc = f"{payload[2]:#04x}" if len(payload) >= 3 else "?"
        return f"NEG på {svc} (NRC {nrc})"
    if sid == 0xC1:
        return "StartCommunication positivt (C1)"
    if (sid & 0x40) and (sid & ~0x40) in _SERVICES:
        return f"SVAR {_SERVICES[sid & ~0x40]}"
    if sid in _SERVICES:
        return f"REQ {_SERVICES[sid]}"
    return ""
