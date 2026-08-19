"""Tester för den delade EcuSession-basen (livscykel, read_block, _establish).

Testar mot ``FakeKLineEcu`` genom en minimal konkret subklass, så bas-mekaniken
verifieras oberoende av Td5/Slabs. Modulernas egna establish-beteenden täcks
fortsatt av test_tolerant/test_slabs.
"""
import pytest

from d2diag.kline import KLine, encode
from d2diag.kwp2000 import KWP2000, KWP2000Error
from d2diag.session import EcuSession
from tests.fakes import FakeKLineEcu

NOSLEEP = lambda *_: None  # noqa: E731


def _sess(data: bytes) -> bytes:
    return encode(data, addressed=False)


def _init_req() -> bytes:
    return encode(b"\x81", addressed=True)


class _Dummy(EcuSession):
    """Modul utan efter-fas (som Slabs): fast init → klar."""

    name = "DUMMY"

    def establish(self, **kw):
        return self._establish(after=None, idle=0, attempts=2, retry_sleep=0, sleep=NOSLEEP, **kw)


def _dummy(responses):
    # kort ram-timeout: testerna ska inte betala 1 s per uteblivet svar
    ecu = FakeKLineEcu(responses)
    return ecu, _Dummy(KWP2000(KLine(ecu, timeout=0.05)))


def test_context_manager_opens_and_closes():
    ecu, s = _dummy({})
    assert not getattr(ecu, "_is_open", False)
    with s:
        assert ecu._is_open is True
    assert ecu._is_open is False


def test_read_local_strips_echoed_lid():
    responses = {_sess(b"\x21\x54"): _sess(b"\x61\x54\x91\x9c\x0f\x0f")}
    ecu, s = _dummy(responses)
    with s:
        assert s.read_local(0x54) == bytes.fromhex("919c0f0f")


def test_read_block_returns_lid_hex_keyed_bytes():
    responses = {
        _sess(b"\x21\x54"): _sess(b"\x61\x54\x91\x9c\x0f\x0f"),
        _sess(b"\x21\x43"): _sess(b"\x61\x43\x7c\x00\x7c\x00"),
    }
    ecu, s = _dummy(responses)
    with s:
        block = s.read_block([0x54, 0x43])
    assert set(block) == {"54", "43"}                 # gemena 2-hex-nycklar (automap-format)
    assert block["54"] == bytes.fromhex("919c0f0f")
    assert block["43"] == bytes.fromhex("7c007c00")


def test_read_block_skips_failing_lid():
    # 0x54 svarar; 0x99 ger negativt svar (7F 21 12) → hoppas tyst över.
    responses = {
        _sess(b"\x21\x54"): _sess(b"\x61\x54\x91\x9c"),
        _sess(b"\x21\x99"): _sess(b"\x7f\x21\x12"),
    }
    ecu, s = _dummy(responses)
    with s:
        block = s.read_block([0x54, 0x99])
    assert set(block) == {"54"}                       # den felande LID:en finns inte med


def test_establish_after_none_returns_c1():
    ecu, s = _dummy({_init_req(): _sess(b"\xc1\x57\x8f")})
    with s:
        c1 = s.establish()
    assert c1[:3] == b"\xc1\x57\x8f"


def test_establish_raises_after_attempts_when_no_c1():
    # Ingen init-respons → tolerant fast init hittar ingen C1 → höjer efter attempts.
    ecu, s = _dummy({})
    with s:
        with pytest.raises(KWP2000Error):
            s.establish()


# ---- ren avslutning på delad buss (release/end_session) ------------------ #

class _WithSession(_Dummy):
    """Modul MED diagnostiksession (som Td5) — ska stängas rent."""

    name = "WITHSESSION"
    _has_session = True


def test_release_sends_stop_diagnostic_session_then_closes():
    # Td5-fallet: release() ska skicka StopDiagnosticSession (20 → 60) INNAN porten
    # stängs, annars ligger sessionen kvar och nästa moduls init får 7F 81 10.
    ecu = FakeKLineEcu({_sess(b"\x20"): _sess(b"\x60"), _sess(b"\x82"): _sess(b"\xc2")})
    s = _WithSession(KWP2000(KLine(ecu)))
    with s:
        s.release()
    # Td5 har BÅDA: en diagnostiksession (20) ovanpå kommunikationslänken (82).
    assert ecu.sent == [_sess(b"\x20"), _sess(b"\x82")]
    assert ecu._is_open is False


def test_release_without_session_still_stops_communication():
    # SLABS-fallet: ingen diagnostiksession att avsluta — men fast init upprättade
    # en LÄNK, och den måste rivas med 82. Annars svarar modulen 7F 81 10 på nästa
    # StartCommunication tills dess egen timeout löper ut (belagt i bilen 2026-08-18).
    ecu, s = _dummy({_sess(b"\x82"): _sess(b"\xc2")})
    with s:
        s.release()
    assert ecu.sent == [_sess(b"\x82")]     # 82, men inget 20 (ingen session)
    assert ecu._is_open is False


def test_release_closes_even_when_stop_fails():
    # Tyst/död buss: 20 får inget svar. Stängningen får inte hänga på det.
    ecu = FakeKLineEcu({})  # inget svar på 20
    s = _WithSession(KWP2000(KLine(ecu, timeout=0.01)))
    with s:
        s.release()
    assert ecu._is_open is False


def test_establish_clears_stale_link_before_init():
    # En länk som lämnats öppen (kraschad process, tidigare körning) får modulen att
    # svara 7F 81 10 på StartCommunication. Vi river den med 82 FÖRE varje försök.
    ecu, s = _dummy({_init_req(): _sess(b"\xc1\x57\x8f"), _sess(b"\x82"): _sess(b"\xc2")})
    with s:
        assert s.establish().startswith(b"\xc1\x57\x8f")  # burst från C1 (+ checksumma)
    assert ecu.sent[0] == _sess(b"\x82")    # rensning först …
    assert ecu.sent[1] == _init_req()       # … sedan init


def test_establish_progress_reports_the_burst_on_each_failed_try():
    # Bursten (t.ex. "03 7f 81 10 13") ska synas i anslutningsloggen för VARJE
    # misslyckat försök — annars går det inte att se om rejecten fanns från start.
    ecu, s = _dummy({})                     # inget svar på vare sig 82 eller init
    msgs: "list[str]" = []
    with s:
        with pytest.raises(KWP2000Error):
            s.establish(progress=msgs.append)
    tries = [m for m in msgs if m.startswith("no response yet")]
    assert len(tries) == 2                  # attempts=2 i _Dummy
    assert all("bursten" in m for m in tries)


def test_stale_link_is_cleared_once_not_between_tries():
    # Pausen mellan försöken måste vara TYST. Skickar vi 82 före varje försök
    # nollställs modulens väntan och den släpper aldrig sin länk (mätt i sniffen:
    # varje lyckad SLABS-init kom efter 25–28 s utan trafik mot modulen).
    ecu, s = _dummy({})                      # inget svar → alla försök misslyckas
    with pytest.raises(KWP2000Error):
        with s:
            s.establish()
    stops = [f for f in ecu.sent if f == _sess(b"\x82")]
    assert len(stops) == 1                   # exakt en rensning, före tystnaden
    assert ecu.sent[0] == _sess(b"\x82")     # och den kom först av allt


def test_end_session_leaves_the_port_open_but_release_closes_it():
    # Delad port: tools/slabs_probe.py läser TD5 först och testar SEDAN SLABS på
    # samma transport. Avslutas TD5 med release() stängs porten, och varje följande
    # initförsök "misslyckas" utan att en byte gått ut — ett testfel som ser ut som
    # en tyst modul (bilen 2026-08-19, 6,5 min bortkastade). end_session() får
    # därför avsluta sessionen UTAN att stänga.
    ecu = FakeKLineEcu({_sess(b"\x20"): _sess(b"\x60"), _sess(b"\x82"): _sess(b"\xc2")})
    s = _WithSession(KWP2000(KLine(ecu)))
    s.open()
    s.end_session()
    assert ecu.sent == [_sess(b"\x20"), _sess(b"\x82")]
    assert ecu.is_open is True          # porten lever vidare för nästa modul
    s.release()
    assert ecu.is_open is False
