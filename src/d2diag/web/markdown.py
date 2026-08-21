"""Minimal, dependency-free Markdown→HTML renderer.

Built to render *our* diagnostic documents (the canonical fault-code dictionary +
the reference docs) in the dashboard's Documents tab — **not** a full CommonMark
implementation. Supports exactly what we use:

- headings ``#``…``######``
- GFM tables (``| … |`` with separator row ``|---|---|``) — they carry the whole reference
- bold ``**x**``, italic ``*x*``/``_x_``, inline code `` `x` ``
- links ``[text](url)`` (incl. anchor links ``#slug``)
- blockquotes ``>`` (multiple lines), bullet/numbered lists, ``---`` (hr)
- code fences ```` ``` ````

The dashboard is offline (Pi in the car) → no CDN, no external markdown lib.
Rendering happens server-side; the client injects the finished HTML.
"""
from __future__ import annotations

import html
import re

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$")
_HR = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
_ULI = re.compile(r"^(\s*)[-*]\s+(.*)$")
_OLI = re.compile(r"^(\s*)\d+[.)]\s+(.*)$")
_FENCE = re.compile(r"^\s*```")

_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITAL = re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])")
_ITAL_U = re.compile(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])")


def _inline(text: str) -> str:
    """Render inline markup in an already HTML-escaped line of text."""
    # Protect inline code first so its contents aren't formatted further.
    spans: list[str] = []

    def _stash(m: "re.Match") -> str:
        spans.append(m.group(1))
        return f"\x00{len(spans) - 1}\x00"

    text = re.sub(r"`([^`]+)`", _stash, text)
    text = html.escape(text, quote=False)
    # The URL is already escaped by the line above (& → &amp;); don't escape again,
    # only quotes so the attribute isn't broken.
    text = _LINK.sub(
        lambda m: f'<a href="{m.group(2).replace(chr(34), "&quot;")}" '
        f'rel="noopener">{m.group(1)}</a>',
        text,
    )
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITAL.sub(r"<em>\1</em>", text)
    text = _ITAL_U.sub(r"<em>\1</em>", text)

    def _pop(m: "re.Match") -> str:
        return f"<code>{html.escape(spans[int(m.group(1))], quote=False)}</code>"

    return re.sub(r"\x00(\d+)\x00", _pop, text)


def _split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    # split on | but respect escaped \|
    cells = re.split(r"(?<!\\)\|", line)
    return [c.replace("\\|", "|").strip() for c in cells]


class _Renderer:
    def __init__(self, lines: list[str]) -> None:
        self.lines = lines
        self.i = 0
        self.out: list[str] = []

    def render(self) -> str:
        while self.i < len(self.lines):
            line = self.lines[self.i]
            if not line.strip():
                self.i += 1
                continue
            if _FENCE.match(line):
                self._fence()
            elif self._is_table():
                self._table()
            elif _HEADING.match(line):
                self._heading()
            elif _HR.match(line):
                self.out.append("<hr>")
                self.i += 1
            elif line.lstrip().startswith(">"):
                self._blockquote()
            elif _ULI.match(line) or _OLI.match(line):
                self._list()
            else:
                self._paragraph()
        return "\n".join(self.out)

    # ---- block types ---------------------------------------------------- #
    def _fence(self) -> None:
        self.i += 1
        buf: list[str] = []
        while self.i < len(self.lines) and not _FENCE.match(self.lines[self.i]):
            buf.append(self.lines[self.i])
            self.i += 1
        self.i += 1  # closing ```
        self.out.append(
            "<pre><code>" + html.escape("\n".join(buf), quote=False) + "</code></pre>"
        )

    def _is_table(self) -> bool:
        return (
            "|" in self.lines[self.i]
            and self.i + 1 < len(self.lines)
            and bool(_TABLE_SEP.match(self.lines[self.i + 1]))
        )

    def _table(self) -> None:
        header = _split_row(self.lines[self.i])
        self.i += 2  # header + separator
        rows: list[list[str]] = []
        while self.i < len(self.lines) and "|" in self.lines[self.i] and self.lines[self.i].strip():
            rows.append(_split_row(self.lines[self.i]))
            self.i += 1
        head = "".join(f"<th>{_inline(c)}</th>" for c in header)
        body = "".join(
            "<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in rows
        )
        self.out.append(
            f'<div class="tablewrap"><table><thead><tr>{head}</tr></thead>'
            f"<tbody>{body}</tbody></table></div>"
        )

    def _heading(self) -> None:
        m = _HEADING.match(self.lines[self.i])
        level = len(m.group(1))
        self.out.append(f"<h{level}>{_inline(m.group(2).strip())}</h{level}>")
        self.i += 1

    def _blockquote(self) -> None:
        buf: list[str] = []
        while self.i < len(self.lines) and self.lines[self.i].lstrip().startswith(">"):
            buf.append(re.sub(r"^\s*>\s?", "", self.lines[self.i]))
            self.i += 1
        inner = "<br>".join(_inline(b) if b.strip() else "" for b in buf)
        self.out.append(f"<blockquote>{inner}</blockquote>")

    def _list(self) -> None:
        ordered = bool(_OLI.match(self.lines[self.i]))
        pat = _OLI if ordered else _ULI
        items: list[str] = []
        while self.i < len(self.lines):
            m = pat.match(self.lines[self.i])
            if not m:
                # allow a different list type to end this one
                if (_OLI if not ordered else _ULI).match(self.lines[self.i]):
                    break
                if not self.lines[self.i].strip():
                    break
                if _HEADING.match(self.lines[self.i]) or self._is_table():
                    break
                # continuation line of the previous item
                if items:
                    items[-1] += " " + _inline(self.lines[self.i].strip())
                    self.i += 1
                    continue
                break
            items.append(_inline(m.group(2).strip()))
            self.i += 1
        tag = "ol" if ordered else "ul"
        self.out.append(f"<{tag}>" + "".join(f"<li>{it}</li>" for it in items) + f"</{tag}>")

    def _paragraph(self) -> None:
        buf: list[str] = []
        while self.i < len(self.lines):
            line = self.lines[self.i]
            if (
                not line.strip()
                or _HEADING.match(line)
                or _FENCE.match(line)
                or _HR.match(line)
                or line.lstrip().startswith(">")
                or _ULI.match(line)
                or _OLI.match(line)
                or self._is_table()
            ):
                break
            buf.append(line.strip())
            self.i += 1
        self.out.append("<p>" + " ".join(_inline(b) for b in buf) + "</p>")


def render(text: str) -> str:
    """Render Markdown → HTML fragment (no ``<html>``/``<body>`` wrapper)."""
    return _Renderer(text.replace("\r\n", "\n").replace("\r", "\n").split("\n")).render()
