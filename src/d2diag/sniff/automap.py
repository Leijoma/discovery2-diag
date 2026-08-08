"""Auto-mappa ett reference tool-fält från KLARTEXT-avläsningar + sniffade råbytes.

Förutsättning: användaren ser bara klartext i reference tool (kan inte ange offset/typ).
Verktyget får därför bara ``(klartext-värde, råbytes-för-kandidat-LID:er)`` per
avläsning och **söker själv** rätt fält:

- **numeriskt** — testa varje ``(lid, offset, typ∈{u8,u16,u16le,s16,s16le})``,
  linjäranpassa råvärde→klartext, välj bästa R² (snäpp skalan till rena bråk).
  En enda avläsning ger en gissning (ren skala, bias 0); två+ vid olika lägen
  låser skala+offset.
- **tillstånd** — när avläsningarna är text (OPEN/CLOSED, AIR/springs …): hitta
  den byte.bit (eller byte) som skiljer lägena entydigt.
"""
from __future__ import annotations

from .calib import _fmt_num, suggest_signal

CLEAN_SCALES = [
    1.0, 0.5, 0.25, 0.1, 0.05, 0.04, 0.02, 0.01, 0.005, 0.001, 0.0001,
    1 / 16, 1 / 32, 1 / 64, 1 / 128, 1 / 256,
]


def _u8(b, o):
    return b[o] if o < len(b) else None


def _u16(b, o):
    return (b[o] << 8) | b[o + 1] if o + 1 < len(b) else None


def _u16le(b, o):
    return (b[o + 1] << 8) | b[o] if o + 1 < len(b) else None


def _s16(b, o):
    v = _u16(b, o)
    return v - 0x10000 if v is not None and v >= 0x8000 else v


def _s16le(b, o):
    v = _u16le(b, o)
    return v - 0x10000 if v is not None and v >= 0x8000 else v


KINDS = {"u8": _u8, "u16": _u16, "u16le": _u16le, "s16": _s16, "s16le": _s16le}
_KIND_RANK = {"u16": 0, "u8": 1, "s16": 2, "u16le": 3, "s16le": 4}  # BE föredras


def _nearest_clean(scale: float) -> "float | None":
    best, bd = None, 0.03
    for s in CLEAN_SCALES:
        d = abs(s - scale) / (abs(s) or 1)
        if d < bd:
            best, bd = s, d
    return best


def _r2(xs, ys, scale, bias):
    my = sum(ys) / len(ys)
    ss_res = sum((y - (scale * x + bias)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - my) ** 2 for y in ys)
    return 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else 1.0


def _fit(xs, ys):
    """→ (scale, bias, r2, how, clean) eller None.

    Med få avläsningar ger varje fält R²≈1 (två punkter ligger alltid på en
    linje). Därför är **ren skala** (snäppt till ett känt bråk) den starka
    signalen om att fältet är rätt — inte R²."""
    n = len(xs)
    if len(set(xs)) >= 2:
        mx, my = sum(xs) / n, sum(ys) / n
        sxx = sum((x - mx) ** 2 for x in xs)
        sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        scale = sxy / sxx
        bias = my - scale * mx
        r2_raw = _r2(xs, ys, scale, bias)
        snap = _nearest_clean(scale)
        if snap is not None:
            b2 = sum(y - snap * x for x, y in zip(xs, ys)) / n
            if _r2(xs, ys, snap, b2) >= r2_raw - 0.02:  # acceptera liten R²-förlust för ren skala
                return snap, b2, _r2(xs, ys, snap, b2), "fit", True
        return scale, bias, r2_raw, "fit", False
    # bara ett distinkt råvärde → gissa ren skala (bias 0)
    x, y = xs[0], ys[0]
    if x == 0:
        return None
    for s in CLEAN_SCALES:
        if abs(x * s - y) <= max(0.02, abs(y) * 0.02):
            return s, 0.0, 1.0, "guess", True
    return None


def _lid_int(lid: str) -> int:
    return int(lid, 16)


def search_numeric(samples, candidate_lids, name="signal", unit=""):
    """samples: [{'value': float, 'raws': {lid_hex: bytes}}]. → bästa fält eller None."""
    best = None
    for lid in candidate_lids:
        raws = [s["raws"].get(lid) for s in samples]
        if any(r is None for r in raws):
            continue
        ys = [s["value"] for s in samples]
        maxlen = min(len(r) for r in raws)
        tol = max(0.03, 0.01 * max(abs(y) for y in ys))
        for off in range(maxlen):
            for kind, fn in KINDS.items():
                xs = [fn(r, off) for r in raws]
                if any(x is None for x in xs):
                    continue
                got = _fit(xs, ys)
                if got is None:
                    continue
                scale, bias, r2, how, clean = got
                small_bias = abs(bias) <= tol
                # renhet väger tyngst, sedan R², fit>gissning, liten bias, BE-typ, lågt offset
                key = (clean, round(r2, 6), how == "fit", small_bias, -_KIND_RANK[kind], -off)
                if best is None or key > best["key"]:
                    best = {
                        "key": key, "lid": lid, "offset": off, "kind": kind,
                        "scale": scale, "bias": 0.0 if small_bias else bias,
                        "r2": r2, "how": how, "clean": clean,
                    }
    if best is None:
        return None
    best["signal"] = suggest_signal(
        name, _lid_int(best["lid"]), best["offset"], best["kind"],
        best["scale"], best["bias"], unit,
    )
    best.pop("key")
    return best


def search_state(samples, candidate_lids):
    """samples: [{'state': str, 'raws': {lid_hex: bytes}}]. → bästa byte/bit eller None."""
    states = [s["state"] for s in samples]
    if len(set(states)) < 2:
        return None

    def consistent(vals):
        by_state = {}
        for st, v in zip(states, vals):
            if by_state.setdefault(st, v) != v:
                return False  # samma läge, olika råvärde → inte det här fältet
        return len(set(by_state.values())) == len(by_state)  # lägena särskiljs

    best = None
    for lid in candidate_lids:
        raws = [s["raws"].get(lid) for s in samples]
        if any(r is None for r in raws):
            continue
        maxlen = min(len(r) for r in raws)
        for off in range(maxlen):
            for bit in range(8):
                vals = [(r[off] >> bit) & 1 for r in raws]
                if consistent(vals):
                    mapping = {st: (r[off] >> bit) & 1 for st, r in zip(states, raws)}
                    cand = {"lid": lid, "offset": off, "bit": bit, "mapping": mapping,
                            "rank": (0, off, bit)}
                    if best is None or cand["rank"] < best["rank"]:
                        best = cand
            if best is not None and best["lid"] == lid and best["offset"] == off:
                continue  # redan en bit-träff för denna byte
            vals = [r[off] for r in raws]
            if consistent(vals):
                mapping = {st: r[off] for st, r in zip(states, raws)}
                cand = {"lid": lid, "offset": off, "bit": None, "mapping": mapping,
                        "rank": (1, off, 0)}
                if best is None or cand["rank"] < best["rank"]:
                    best = cand
    if best is None:
        return None
    where = f"21 {best['lid']} byte{best['offset']}"
    where += f" bit{best['bit']}" if best["bit"] is not None else " (hel byte)"
    best["rule"] = where + ": " + ", ".join(f"{k}={v}" for k, v in best["mapping"].items())
    best.pop("rank")
    return best


def block_diff(parsed, candidate_lids):
    """Vilka bytes ändrades mellan avläsningarna? Kärn-primitiven för fält som
    läses i ett block: ändra EN sak, se vilken byte som rör sig = där bor fältet.

    → [{'lid', 'byte', 'values': [per avläsning]}]. Tom = inget rörde sig.
    """
    out = []
    if len(parsed) < 2:
        return out
    for lid in candidate_lids:
        raws = [p["raws"].get(lid) for p in parsed]
        if any(r is None for r in raws):
            continue
        for off in range(min(len(r) for r in raws)):
            vals = [r[off] for r in raws]
            if len(set(vals)) > 1:
                out.append({"lid": lid, "byte": off, "values": vals})
    return out


def solve(samples, candidate_lids, name="signal", unit=""):
    """Auto-detektera numeriskt vs tillstånd och returnera bästa mappning.

    ``samples``: [{'text': '<klartext>', 'raws': {lid_hex: 'hex' | bytes}}]. Bär
    alltid med ``diff`` (ändrade bytes mellan avläsningarna) så platsen syns.
    """
    parsed = []
    numeric = True
    for s in samples:
        raws = {k: (v if isinstance(v, (bytes, bytearray)) else bytes.fromhex(v.replace(" ", "")))
                for k, v in (s.get("raws") or {}).items()}
        text = (s.get("text") or "").strip()
        parsed.append({"text": text, "raws": raws})
        try:
            float(text.replace(",", "."))
        except ValueError:
            numeric = False
    if len(parsed) < 1:
        return {"ok": False, "error": "inga avläsningar"}
    diff = block_diff(parsed, candidate_lids)
    if numeric:
        num = [{"value": float(p["text"].replace(",", ".")), "raws": p["raws"]} for p in parsed]
        res = search_numeric(num, candidate_lids, name, unit)
        if res is None:
            return {"ok": False, "error": "hittade inget råfält som matchar värdena", "diff": diff}
        return {"ok": True, "mode": "numeric", "diff": diff, **res}
    st = [{"state": p["text"], "raws": p["raws"]} for p in parsed]
    res = search_state(st, candidate_lids)
    if res is None:
        return {"ok": False, "error": "behöver ≥2 olika lägen som särskiljs i råbytesen", "diff": diff}
    return {"ok": True, "mode": "state", "diff": diff, **res}
