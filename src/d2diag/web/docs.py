"""Dokumentbibliotek för dashboardens Dokument-flik.

Registret pekar på de **kanoniska** markdown-filerna (felkodsordboken i register-
repot + referensdokumenten i diag-repot) och läser dem *färskt vid varje anrop*.
Dashboarden blir därmed ett fönster mot källan — aldrig en kopia. Saknade filer
(t.ex. register-repot ligger på annan sökväg på Pi:n) hoppas tyst över.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import markdown

_H1 = re.compile(r"^#\s+(.*)$", re.MULTILINE)


def _slug(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\wåäö]+", "-", text, flags=re.UNICODE).strip("-")
    return text or "doc"


class _Doc:
    def __init__(self, id: str, title: str, path: Path, group: str) -> None:
        self.id = id
        self.title = title
        self.path = path
        self.group = group

    @property
    def available(self) -> bool:
        return self.path.is_file()


class DocLibrary:
    """Ordnad samling markdown-dokument som exponeras för webben."""

    def __init__(self) -> None:
        self._docs: "list[_Doc]" = []
        self._by_id: "dict[str, _Doc]" = {}

    def add_file(
        self, path: "str | Path", title: "str | None" = None, group: str = "Referens"
    ) -> "DocLibrary":
        path = Path(path).expanduser()
        title = title or self._title_of(path)
        base = _slug(title)
        doc_id = base
        n = 2
        while doc_id in self._by_id:
            doc_id = f"{base}-{n}"
            n += 1
        doc = _Doc(doc_id, title, path, group)
        self._docs.append(doc)
        self._by_id[doc_id] = doc
        return self

    def add_dir(
        self, path: "str | Path", group: str = "Referens", pattern: str = "*.md"
    ) -> "DocLibrary":
        d = Path(path).expanduser()
        if d.is_dir():
            for f in sorted(d.glob(pattern)):
                self.add_file(f, group=group)
        return self

    @staticmethod
    def _title_of(path: Path) -> str:
        try:
            m = _H1.search(path.read_text(encoding="utf-8"))
            if m:
                return m.group(1).strip()
        except OSError:
            pass
        return path.stem.replace("_", " ").replace("-", " ")

    def index(self) -> "list[dict]":
        """Lista över tillgängliga dokument (saknade filer utelämnas)."""
        return [
            {"id": d.id, "title": d.title, "group": d.group}
            for d in self._docs
            if d.available
        ]

    def html(self, doc_id: str) -> "str | None":
        """Rendera dokumentet till HTML, eller ``None`` om okänt/saknat."""
        doc = self._by_id.get(doc_id)
        if doc is None or not doc.available:
            return None
        try:
            text = doc.path.read_text(encoding="utf-8")
        except OSError:
            return None
        return markdown.render(text)
