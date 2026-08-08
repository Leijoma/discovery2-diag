"""Tester för modulkartorna (Karta-fliken) och täckningsberäkningen."""
from __future__ import annotations

from d2diag.menus import MENUS
from d2diag.web.server import DiagServer
from d2diag.web.sources import MockDataSource, MockSlabsDataSource


def test_all_modules_have_populated_maps():
    for name in ("slabs", "bcu", "ace", "autobox", "airbag"):
        menu = MENUS[name]
        assert menu, f"{name} har tom karta"
        for group in menu:
            assert group["items"], f"{name}/{group['cat']} saknar items"
            for item in group["items"]:
                assert set(item) >= {"name", "status", "ref"}
                assert item["status"] in {"ok", "maybe", "todo"}


def test_coverage_counts_match_maps():
    srv = DiagServer(
        {"motor": MockDataSource(), "slabs": MockSlabsDataSource()},
        port=0, menus=MENUS, active="slabs",
    )
    try:
        cov = srv.coverage()
        assert set(cov) == set(MENUS)
        for name, menu in MENUS.items():
            tot = sum(len(g["items"]) for g in menu)
            ok = sum(1 for g in menu for i in g["items"] if i["status"] == "ok")
            mb = sum(1 for g in menu for i in g["items"] if i["status"] == "maybe")
            assert cov[name] == {"ok": ok, "maybe": mb, "total": tot}
            assert cov[name]["ok"] + cov[name]["maybe"] <= tot
    finally:
        srv.server_close()


def test_airbag_has_no_output_actuators():
    """SRS är pyroteknik — kartan får inte lista aktiverbara outputs som todo/ok-test."""
    names = [i["name"].lower() for g in MENUS["airbag"] for i in g["items"]]
    # enda output-raden ska vara den belagda 'ingen output-sida'
    assert any("ingen output" in n for n in names)
    assert not any("force on" in n or "aktivera" in n for n in names)
