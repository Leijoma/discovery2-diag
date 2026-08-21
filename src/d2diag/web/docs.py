"""Document library for the dashboard's Documents tab.

The registry points at the **canonical** markdown files (the fault-code dictionary
in the register repo + the reference docs in the diag repo) and reads them *fresh
on every request*. The dashboard is thereby a window on the source — never a copy.
Missing files (e.g. the register repo sits at a different path on the Pi) are
silently skipped.
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
    """Ordered collection of markdown documents exposed to the web."""

    def __init__(self) -> None:
        self._docs: "list[_Doc]" = []
        self._by_id: "dict[str, _Doc]" = {}

    def add_file(
        self, path: "str | Path", title: "str | None" = None, group: str = "Reference"
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
        self, path: "str | Path", group: str = "Reference", pattern: str = "*.md"
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
        """List of available documents (missing files are omitted)."""
        return [
            {"id": d.id, "title": d.title, "group": d.group}
            for d in self._docs
            if d.available
        ]

    def html(self, doc_id: str) -> "str | None":
        """Render the document to HTML, or ``None`` if unknown/missing."""
        doc = self._by_id.get(doc_id)
        if doc is None or not doc.available:
            return None
        try:
            text = doc.path.read_text(encoding="utf-8")
        except OSError:
            return None
        return markdown.render(text)
