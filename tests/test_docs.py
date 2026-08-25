"""Tests for the markdown renderer and the document library (the Documents tab)."""
from __future__ import annotations

import pathlib

from d2diag.web import markdown as md
from d2diag.web.docs import DocLibrary


def test_headings_and_inline():
    out = md.render("# H1\n\n## H2\n\nText **fet** *kursiv* `kod`.\n")
    assert "<h1>H1</h1>" in out
    assert "<h2>H2</h2>" in out
    assert "<strong>fet</strong>" in out
    assert "<em>kursiv</em>" in out
    assert "<code>kod</code>" in out


def test_gfm_table_with_inline_cells():
    src = (
        "| Kod | Not |\n"
        "|---|---|\n"
        "| 020-05 | `21 11` byte 3 |\n"
        "| 0B10 | **strongly reported** |\n"
    )
    out = md.render(src)
    assert "<table>" in out and out.count("<tr>") == 3  # 1 head + 2 body
    assert "<th>Kod</th>" in out
    assert "<td><code>21 11</code> byte 3</td>" in out
    assert "<td><strong>strongly reported</strong></td>" in out
    assert 'class="tablewrap"' in out  # horizontal scroll container


def test_html_is_escaped_outside_and_inside_code():
    out = md.render("Text <tag> & `a<b>` slut.\n")
    assert "&lt;tag&gt;" in out
    assert "&amp;" in out
    assert "<code>a&lt;b&gt;</code>" in out


def test_blockquote_list_hr_fence_link():
    out = md.render(
        "> line one\n> line two\n\n- a\n- b\n\n1. x\n2. y\n\n---\n\n"
        "```text\nraw 81 29\n```\n\n[lnk](http://a?b=1&c=2)\n"
    )
    assert "<blockquote>line one<br>line two</blockquote>" in out
    assert "<ul><li>a</li><li>b</li></ul>" in out
    assert "<ol><li>x</li><li>y</li></ol>" in out
    assert "<hr>" in out
    assert "<pre><code>raw 81 29</code></pre>" in out
    assert out.count("<a ") == 1 and 'href="http://a?b=1&amp;c=2"' in out


def test_doclibrary_reads_fresh_and_skips_missing(tmp_path: pathlib.Path):
    f = tmp_path / "slabs_protocol.md"
    f.write_text("# SLABS\n\nv1.\n", encoding="utf-8")
    lib = (
        DocLibrary()
        .add_file(tmp_path / "missing.md", title="Gone")  # does not exist → omitted
        .add_dir(tmp_path, group="Reference")
    )
    idx = lib.index()
    ids = {x["title"] for x in idx}
    assert "SLABS" in ids and "Gone" not in ids
    assert lib.html("gone") is None  # missing file → None (not a crash)

    doc_id = next(x["id"] for x in idx if x["title"] == "SLABS")
    assert "<h1>SLABS</h1>" in lib.html(doc_id)

    # fresh read: change the file → new rendering without touching the library
    f.write_text("# SLABS\n\nv2 updated.\n", encoding="utf-8")
    assert "v2 updated." in lib.html(doc_id)


def test_doclibrary_title_from_h1_and_unique_ids(tmp_path: pathlib.Path):
    (tmp_path / "a.md").write_text("# Same\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("# Same\n", encoding="utf-8")
    lib = DocLibrary().add_dir(tmp_path)
    ids = [x["id"] for x in lib.index()]
    assert len(ids) == len(set(ids))  # collisions get suffixed


def test_doclibrary_add_dir_exclude_keeps_pinned_file_once(tmp_path: pathlib.Path):
    """The test plan is pinned to its own group first, then the rest of references/ is
    swept in — the pinned file must not appear twice."""
    (tmp_path / "test_plan.md").write_text("# Test backlog\n", encoding="utf-8")
    (tmp_path / "slabs_protocol.md").write_text("# SLABS\n", encoding="utf-8")
    lib = (
        DocLibrary()
        .add_file(tmp_path / "test_plan.md", group="Test plan")
        .add_dir(tmp_path, group="Reference", exclude={"test_plan.md"})
    )
    idx = lib.index()
    assert [x["title"] for x in idx] == ["Test backlog", "SLABS"]  # pinned first
    assert idx[0]["group"] == "Test plan"
