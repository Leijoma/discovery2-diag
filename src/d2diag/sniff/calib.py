"""Solve scale/offset from (raw value, reference tool displayed value) samples.

Model: ``displayed = raw · scale + bias`` (least-squares). Also gives a suggestion for a
ready-made :class:`d2diag.td5.identifiers.Signal` row to paste in.
"""
from __future__ import annotations


def solve_linear(samples: "list[tuple[float, float]]") -> "dict | None":
    """Fit ``y = scale·x + bias`` to the samples ``[(raw, displayed), …]``.

    Returns ``{scale, bias, r2, n}`` or ``None`` if fewer than two samples with
    different raw values (then the slope can't be determined)."""
    xs = [float(s[0]) for s in samples]
    ys = [float(s[1]) for s in samples]
    n = len(xs)
    if n < 2 or len(set(xs)) < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    scale = sxy / sxx
    bias = my - scale * mx
    ss_res = sum((y - (scale * x + bias)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - my) ** 2 for y in ys) or 1e-12
    r2 = 1.0 - ss_res / ss_tot
    return {"scale": scale, "bias": bias, "r2": r2, "n": n}


def _fmt_num(v: float) -> str:
    """Pretty string: catch common fractions (1/1000 etc.), otherwise a short decimal."""
    if v == 0:
        return "0"
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    inv = 1.0 / v
    if abs(inv - round(inv)) < 1e-6 and abs(round(inv)) <= 100000:
        return f"1 / {int(round(inv))}"
    return f"{v:.6g}"


def suggest_signal(
    name: str, lid: int, offset: int, kind: str, scale: float, bias: float, unit: str = ""
) -> str:
    """Format a ``Signal(...)`` row for ``td5/identifiers.py``."""
    parts = [f'"{name}"', f"0x{lid:02X}", str(offset)]
    if kind != "u16":
        parts.append(f'"{kind}"')
    if abs(scale - 1.0) > 1e-9:
        parts.append(f"scale={_fmt_num(scale)}")
    if abs(bias) > 1e-9:
        parts.append(f"bias={_fmt_num(bias)}")
    if unit:
        parts.append(f'unit="{unit}"')
    return "Signal(" + ", ".join(parts) + ")"
