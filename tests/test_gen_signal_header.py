"""The generated ESP header must stay in sync with the signal store.

If signals/td5.json changes and someone forgets to regenerate the ESP decode table, the
two platforms drift — the exact bug class (MAF u8@5 vs u16@4) this codegen exists to kill.
This test fails until `python3 tools/gen_signal_header.py` is re-run.
"""
import pathlib

import tools.gen_signal_header as g


def test_committed_header_matches_signal_store():
    path = pathlib.Path(g._HEADER_PATH)
    assert path.exists(), "esp32/kline_node/signals_td5.h missing — run tools/gen_signal_header.py"
    assert path.read_text(encoding="utf-8") == g.build_header(), (
        "signals_td5.h is stale vs signals/td5.json — run: python3 tools/gen_signal_header.py"
    )


def test_header_covers_the_curated_esp_fields():
    header = g.build_header()
    for esp_key, _store in g._FIELDS:
        assert f'"{esp_key}"' in header
