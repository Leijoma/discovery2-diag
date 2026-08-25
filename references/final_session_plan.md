# Short reference tool session — capture exactly this (prioritized)

> **Appendix.** The living backlog of what to test next is `references/test_plan.md`;
> this file holds the step-by-step detail it points at.

We already have the **raw bytes** for most of it (from `session.log`) — what we're missing
is the reference tool's **plain-text values** to correlate against. So the most valuable
items are the **"read off the screen"** ones and don't even need a working sniff.

## 0. Quick check of the sniffer (30 s)
Capture → **New collection** → do you see ×N **climbing**? Yes = sniff works (capture raw
at the same time). No = ignore the sniff, just run **A** below (enough for most of it).

## A. HIGHEST VALUE — read off all the values on the screen (no sniff needed)
Write down **all** values in the **order displayed** (static values ≈ the same as in our
old capture → we correlate against the raw bytes offline):

1. **SLABS → ABS Inputs** — wheel speed FR/FL/RR/RL · ABS sensor V FR/FL/RR/RL ·
   inlet/outlet valves · pump monitor/relay · battery · ECU supply · ground ref ·
   HDC brake · engine speed/torque/throttle. → against `21 43/44/49/50/57`.
2. **SLABS → SLS Inputs** — L/R sensor value (height) · L/R sensor supply · L/R value (V) ·
   exhaust valve (V) · compressor relay (V). → against `21 53/54/55`.
3. **TD5 → Settings → Feature/config** — ENABLED/DISABLED for all 21 flags in
   order + ECU Status. → solves the `21 3D` block.

## B. IF the sniffer is stable — differential (change ONE thing at a time, annotate)
4. **SLABS settings:** toggle **Transport mode** (safe, reversible) → write
   "toggled transport mode". → solves which of `45/46/49/59` = transport + the encoding.
5. **TD5 read switch:** press **brake** → **clutch** → **cruise ON**, one at a time,
   annotate where. → maps the bit fields `21 1E`/`21 36`.

## C. If there's time — autobox
6. **Auto Gearbox → Read Faults** with the **engine running** + selector in **P**. If it
   succeeds → we get interpretable `72 … 60 …` responses (framing already solved:
   `72 <len> <data> <XOR-cs>`).

## Afterwards
Paste the notes (or hand over the log file) → I correlate against the raw bytes and map
the fields offline. **A is enough to solve the SLABS analog and the TD5 feature block.**
