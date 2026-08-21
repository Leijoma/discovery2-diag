"""Test helper: a half-duplex ECU simulator at the Transport level.

Echoes every frame sent (like a real K-line) and queues a preprogrammed response
when a known request is sent. Lets the whole K-Line layer be tested without hardware.

A response (the value in ``responses``) may be either **static bytes** (the same
response every time — backward compatible) or **scripted**: a ``list``/``tuple`` of
bytes (one response per call, the last one repeats) or a ``callable(count) -> bytes``.
That lets a differential read yield DIFFERENT values between read #1 and read #2.
"""
from __future__ import annotations

from d2diag.transport.base import Transport


def _as_response(v):
    """Normalize a response value into a callable(count) -> bytes."""
    if callable(v):
        return v
    if isinstance(v, (list, tuple)):
        seq = [bytes(x) for x in v]
        return lambda n, _seq=seq: _seq[min(n, len(_seq) - 1)]
    b = bytes(v)
    return lambda n, _b=b: _b


class FakeKLineEcu(Transport):
    def __init__(self, responses: "dict | None" = None, corrupt: bool = False) -> None:
        self._rx = bytearray()
        self._responses = {bytes(k): _as_response(v) for k, v in (responses or {}).items()}
        self._counts: "dict[bytes, int]" = {}
        self._corrupt = corrupt
        self.breaks: "list[float]" = []
        self.sent: "list[bytes]" = []

    def open(self) -> None:
        self._is_open = True

    def close(self) -> None:
        self._is_open = False

    def send(self, data: bytes) -> int:
        data = bytes(data)
        self.sent.append(data)
        self._rx.extend(data)  # echo (half-duplex)
        fn = self._responses.get(data)
        if fn is not None:
            n = self._counts.get(data, 0)
            self._counts[data] = n + 1
            resp = bytes(fn(n))
            if self._corrupt:
                resp = resp[:-1] + bytes([resp[-1] ^ 0xFF])  # broken checksum
            self._rx.extend(resp)
        return len(data)

    def receive(self, size: int = 1, timeout: "float | None" = None) -> bytes:
        out = bytes(self._rx[:size])
        del self._rx[: len(out)]
        return out

    # low-level serial hooks that the K-Line layer uses
    def send_break(self, duration: float = 0.025) -> None:
        self.breaks.append(duration)

    def reset_input_buffer(self) -> None:
        self._rx.clear()

    # 5-baud slow-init hooks (airbag 0x5B): return keyword bytes 55 KW1 KW2
    def slow_init(self, address: int) -> bytes:
        self.slow_init_addr = address
        return b"\x55\xe9\x8f"  # sync + KW1 + KW2 (like the airbag in the sniff)

    def parse_slow_init(self, raw: bytes):
        i = raw.find(0x55)
        return (raw[i + 1], raw[i + 2]) if i >= 0 and len(raw) >= i + 3 else None
