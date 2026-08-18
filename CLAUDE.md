# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Open diagnostics platform for the Land Rover Discovery 2 Td5 over **K-line**
(pre-CAN), using a cheap KKL 409.1 USB cable. Reverse-engineered from sniffed bus
traffic; see `README.md` for scope and `references/protocol_state_handoff.md` for
what is currently **belagt** (proven) vs **kandidat** vs open per module.

## Commands

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"          # only runtime dep is pyserial

pytest -q                        # whole suite (~190 tests, no hardware needed)
pytest tests/test_slabs.py -q    # one file
pytest tests/test_web.py -k slabs_empty_read_grace -q   # one test

# Dashboard — mock (no car) / live (ignition on, stationary)
PYTHONPATH=src python3 tools/dashboard.py --mock
PYTHONPATH=src python3 tools/dashboard.py --serial /dev/cu.usbserial-XXXX [--slabs] [--fault-watch] [--csv]

# Read-only sanity check against a module
PYTHONPATH=src python3 tools/verify_ecu.py td5|slabs /dev/cu.usbserial-XXXX
```

There is no linter/formatter config — match surrounding style. `pyproject.toml`
sets `pythonpath = ["src", "."]`, so `pytest` works without `PYTHONPATH`; the
`tools/*.py` scripts do need it (or an editable install).

## Architecture

Strict bottom-up stack; **no layer knows anything about the one below it beyond
its interface**, and each is unit-tested in isolation:

```
Transport      transport/base.py — raw bytes in/out (SerialTransport, LoggingTransport)
K-Line         kline/frame.py (encode/decode) + kline/kline.py (fast/slow init, echo, retries)
KWP2000        kwp2000/ — service IDs, negative responses (0x7F+NRC), responsePending (0x78)
EcuSession     session.py — shared lifecycle/keepalive/read_block + tolerant establish retry
Module layer   td5/ slabs/ airbag/ (+ bcu/ ace/ autobox/ menu stubs)
Web            web/ — stdlib HTTP + SSE server, single-file dashboard.html (vanilla JS)
```

Key seams to understand before changing things:

- **Two frame formats.** Addressed (`0x8n`, target+source) only for
  StartCommunication/fast init; the whole session afterwards is unaddressed
  length-prefixed frames (`<len> <SID> … <cs>`). `kline.read_frame` sniffs the
  format byte, so both work transparently. Airbag is the exception — addressed
  framing throughout at 0x5B.
- **`EcuSession` is where module layers share behaviour.** Subclasses set `name`
  and call `_establish(after=…)`: Td5 passes `after=self.connect`
  (StartDiagnosticSession + SecurityAccess seed→key), SLABS passes `after=None`
  (no session, no unlock — services work right after fast init). SLABS also
  overrides `_keepalive_sub = None` because it needs a **bare `3E`**; `3E 01`
  kills its session.
- **`EcuSession.read_block(lids) -> {lid_hex: bytes}`** is deliberately the exact
  shape `sniff/automap.py` consumes — that is what lets a live session feed the
  differential mapper.
- **Signal store (`src/d2diag/signals/*.json`) is the single source of truth for
  LID field mappings.** Decoders, the dashboard and automap all read it, and
  confirmed mappings are written back with `upsert_field` — never hand-paste
  `Signal(...)` rows into Python. Every field carries `konfidens`: `belagt`
  (verified against the car) or `kandidat` (derived/unverified). Keep that
  distinction honest; it propagates to the UI.
- **`web/sources.py` is the boundary between the protocol stack and the UI.**
  Each `DataSource.poll()` returns `{status, signals, faults}`; mock and live
  sources are interchangeable and switchable at runtime from the header. Adding a
  module to the dashboard means adding a source pair (mock + live), not touching
  the server.
- **Two command paths in `web/server.py`.** `enqueue_command` runs anything in
  `_INLINE_COMMANDS` (CSV start/stop, fault-watch — server state only) straight on
  the HTTP thread, and queues everything that touches K-line for the poll thread so
  bus access stays serialized. Put a new command on the queue only if it talks to
  the ECU: queued commands wait out the current poll, which during a reconnect can
  be ~20 s and blows the 8 s HTTP timeout.
- **`faultscan.py`** reads every module sequentially — K-line is a shared bus, so
  it is strictly establish → read → close, one module at a time.
- **`web/docs.py`** serves the canonical markdown files fresh on every request
  (references/ plus a fault dictionary in a sibling `Discovery 2/` repo). It is a
  window on the source, never a copy — don't cache or duplicate those docs.
- **`server/endpoint.py`** is a separate, self-hosted community-contribution
  service (stdlib + sqlite3), paired with the opt-in client in `community/`.
  Both are whitelist-based and PII-free by construction — keep it that way.

## Hard-won protocol rules

Violating these produces bugs that only show up against the real car:

- **SLABS must be polled lightly.** ~1 Hz keepalive plus a few reads — the
  dashboard's `SlabsDataSource.poll` reads only heights (`21 54`) per cycle and
  faults at most every 10th poll. Block-reading many LIDs each 0.5 s cycle killed
  the session after ~15 s. Details in `references/slabs_protocol.md`.
- **A `7F 81 10` (generalReject) on StartCommunication means a session is already
  open** on the shared bus — usually a leftover Td5 session. Use
  `EcuSession.release()` (StopDiagnosticSession + close), not bare `close()`, when
  switching modules; don't try to fix it with longer idle. On error paths (dead
  session, lost cable) call `close()` directly — there is no session to end and a
  `20` into a silent bus only costs a timeout.
- **Keep `tolerant=True`** on KWP2000 for cheap KKL cables: it searches the read
  burst for a positive/negative SID instead of demanding a checksum-clean frame,
  which compensates for FTDI latency jitter during fast init.
- **macOS: always `/dev/cu.*`, never `/dev/tty.*`** (tty blocks on DCD).
  `resolve_serial_port("auto")` handles detection.
- **Airbag/SRS is read-only by construction** — no clear, no outputs, no security
  writes. Actuator tests elsewhere stay behind an explicit confirmation and are
  documented as stationary-with-ignition-on.

## Conventions

- **Language:** code comments, docstrings, references/, TODO.md and commit
  messages are **Swedish**; README.md, server/ and community/ (outward-facing) are
  English. Follow whatever the file already uses.
- **Zero dependencies above pyserial.** The web layer is stdlib HTTP + SSE and the
  dashboard is a single vanilla-JS HTML file — no frameworks, no build step.
- **Tests run without hardware** against `tests/fakes.py::FakeKLineEcu`, a
  half-duplex ECU simulator at the transport level (it echoes frames like the real
  bus). Responses may be static bytes, a sequence, or a `callable(count)` when a
  test needs differing values between reads.
- Comments explain *why* — especially which sniff/log a protocol fact came from.
  When you learn something from the car or a capture, record it in the relevant
  `references/*.md` alongside the code change.
