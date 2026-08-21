"""Passive K-line sniffing — frame splitting and annotation (offline analysis).

K-line is a single wire, half-duplex: both the tester's requests and the ECU's
replies appear on the same wire. A passive RX listener therefore captures the whole
conversation. Messages are separated by **silence gaps** between bytes. The pure
functions here (no I/O) are used by ``tools/sniff.py`` and are unit-testable.
"""
from __future__ import annotations

from .kline.frame import ChecksumError, FrameError, decode

# Service ID → name (KWP2000). Positive response = SID | 0x40.
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
    """Split a timestamped byte stream into messages on silence gaps.

    ``byte_samples``: iterable of ``(t, b)`` (t = monotonic time in seconds, b = byte).
    A new message starts when ``t - prev_t > gap``. Returns a list of
    ``{"start", "end", "gap_before", "data"}`` (gap_before = silence before
    the message, ``None`` for the first one).
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
    """Best-effort annotation of a sniffed message (raw frame bytes).

    Tries to decode the frame; otherwise guesses from the raw bytes. Names
    service/SID, positive response, negative response (7F+NRC) and slow-init sync (0x55).
    """
    if not message:
        return ""
    if message[0] == 0x55:
        return "slow-init sync (0x55)"
    try:
        payload = decode(message).data
    except (FrameError, ChecksumError):
        payload = message  # unknown/broken format — guess from the raw bytes
    if not payload:
        return ""
    sid = payload[0]
    if sid == 0x7F:
        svc = _SERVICES.get(payload[1], f"{payload[1]:#04x}") if len(payload) >= 2 else "?"
        nrc = f"{payload[2]:#04x}" if len(payload) >= 3 else "?"
        return f"NEG on {svc} (NRC {nrc})"
    if sid == 0xC1:
        return "StartCommunication positive (C1)"
    if (sid & 0x40) and (sid & ~0x40) in _SERVICES:
        return f"RESP {_SERVICES[sid & ~0x40]}"
    if sid in _SERVICES:
        return f"REQ {_SERVICES[sid]}"
    return ""
