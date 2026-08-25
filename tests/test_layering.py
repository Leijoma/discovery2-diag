"""Layering guard — the core must never import the consumer/presentation layer.

Core = car communication + data interpretation (see SCOPE.md). It must not import from
`web` (or a future `apps`) — data flows one way: comms -> interpretation -> snapshot ->
consumers. This AST scan fails if any core module imports a forbidden package, so the
drift can't creep back in silently.
"""
import ast
import pathlib

import pytest

_SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "d2diag"

# Everything that is CORE (comms + interpretation). Excludes web/ (consumer) and
# community/ (opt-in upload client — consumer side).
_CORE = [
    "transport", "kline", "kwp2000", "session.py", "ports.py", "signals", "menus.py",
    "faultscan.py", "sniff", "td5", "slabs", "airbag", "bcu", "ace", "autobox",
]
_FORBIDDEN = {"web", "apps"}


def _core_files() -> "list[pathlib.Path]":
    out: "list[pathlib.Path]" = []
    for name in _CORE:
        p = _SRC / name
        if p.is_dir():
            out += sorted(p.rglob("*.py"))
        elif p.exists():
            out.append(p)
    return out


def _imported_modules(path: pathlib.Path):
    """Yield every module path referenced by an import in this file."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            yield node.module or ""
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name


@pytest.mark.parametrize("path", _core_files(), ids=lambda p: p.relative_to(_SRC).as_posix())
def test_core_does_not_import_consumer_layer(path: pathlib.Path):
    for mod in _imported_modules(path):
        parts = set(mod.split("."))
        offending = parts & _FORBIDDEN
        assert not offending, f"{path.relative_to(_SRC)} imports consumer layer: {mod!r}"


def test_core_file_list_is_present():
    # Guard against the scan silently matching nothing (e.g. a path rename).
    files = _core_files()
    assert len(files) > 15
