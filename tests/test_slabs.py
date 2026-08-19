"""SLABS-lagret verifierat mot VERKLIG sniffad reference tool-trafik (2026-08-07).

Varje förfrågan/svar nedan är exakta bytes ur ``references/captures/
slabs_session_20260807.log``. Testerna bevisar att vårt lager:
  - **skriver** byte-identiska kommandon (clear + ställdon), och
  - **läser/avkodar** SLABS-svaren rätt (felblock, VIN, versioner).
"""
import pytest

from d2diag.kline import KLine, encode
from d2diag.kwp2000 import KWP2000
from d2diag.slabs import Slabs, decode_fault_block
from tests.fakes import FakeKLineEcu


def _frame(data: bytes) -> bytes:
    return encode(data, addressed=False)  # oadresserad session-ram <len><data><cs>


def _slabs(responses):
    ecu = FakeKLineEcu(responses)
    return ecu, Slabs(KWP2000(KLine(ecu)))


# ---- avkodningen matchar fångade frames exakt --------------------------- #
def test_capture_frames_are_wellformed():
    # Bekräftar att vår oadresserade kodning ger EXAKT de sniffade byten.
    assert _frame(b"\x21\x11").hex(" ") == "02 21 11 34"
    assert _frame(b"\x14\xff\xff").hex(" ") == "03 14 ff ff 15"
    assert _frame(b"\x31\x31\x0a").hex(" ") == "03 31 31 0a 6f"
    assert _frame(b"\x31\x2f\x28").hex(" ") == "03 31 2f 28 8b"
    assert _frame(b"\x31\x30\x28").hex(" ") == "03 31 30 28 8c"
    assert _frame(b"\x31\x25\x08\xfa").hex(" ") == "04 31 25 08 fa 5c"


# ---- LÄSA: felblock avkodas mot baslinjen ------------------------------- #
def test_decode_logged_fault_block_matches_baseline():
    # 21 11 före clear: byte3.bit4 + byte10.bit4 = fel 020 (RF-givare) + 027 (shuttle)
    block = bytes.fromhex("00 00 00 10 00 00 00 00 00 00 10 00 00 00 00 00".replace(" ", ""))
    faults = decode_fault_block(block)
    assert any(f.startswith("020:") for f in faults)
    assert any(f.startswith("027:") for f in faults)
    assert len(faults) == 2


def test_read_faults_logged_and_current():
    logged = bytes.fromhex("00000010000000000000100000000000")
    responses = {
        _frame(b"\x21\x11"): _frame(b"\x61\x11" + logged),
        _frame(b"\x21\x47"): _frame(b"\x61\x47" + bytes(16)),  # aktuella = inga
    }
    ecu, slabs = _slabs(responses)
    with slabs:
        faults = slabs.read_faults()
    assert len(faults["loggade"]) == 2
    assert faults["aktuella"] == []


def test_cleared_block_gives_no_faults():
    responses = {
        _frame(b"\x21\x11"): _frame(b"\x61\x11" + bytes(16)),
        _frame(b"\x21\x47"): _frame(b"\x61\x47" + bytes(16)),
    }
    ecu, slabs = _slabs(responses)
    with slabs:
        assert slabs.read_faults() == {"loggade": [], "aktuella": []}


# ---- LÄSA: ECU-identitet ------------------------------------------------ #
def test_read_vin():
    vin = b"SALLXXXXXXXXXXXXX"
    responses = {_frame(b"\x1a\x8d"): _frame(b"\x5a\x8d" + vin)}
    ecu, slabs = _slabs(responses)
    with slabs:
        assert slabs.read_vin() == "SALLXXXXXXXXXXXXX"


def test_read_software_versions():
    data = b"KRTE49B0\x0030303030\x00HDTE16A0"
    responses = {_frame(b"\x1a\x8b"): _frame(b"\x5a\x8b" + data)}
    ecu, slabs = _slabs(responses)
    with slabs:
        vers = slabs.read_software_versions()
    assert "KRTE49B0" in vers and "HDTE16A0" in vers


# ---- SKRIVA: kommandon blir byte-identiska med reference toolens --------------- #
def test_clear_faults_sends_exact_capture():
    responses = {_frame(b"\x14\xff\xff"): _frame(b"\x54")}
    ecu, slabs = _slabs(responses)
    with slabs:
        slabs.clear_faults()
    assert ecu.sent[-1] == bytes.fromhex("0314ffff15")  # '03 14 ff ff 15'


def test_keepalive_sends_bare_3e_matching_capture():
    # Sniffad keepalive (slabs_session_20260807.log) = '01 3e 3f' → '01 7e 7f',
    # dvs BAR 3E utan sub-byte. Ett tidigare '3E 01' fick inget svar och rev
    # sessionen direkt efter uppkoppling.
    responses = {_frame(b"\x3e"): _frame(b"\x7e")}
    ecu, slabs = _slabs(responses)
    with slabs:
        slabs.tester_present()
    assert ecu.sent[-1] == bytes.fromhex("013e3f")  # '01 3e 3f' — bar 3E


@pytest.mark.parametrize("call, frame_hex", [
    (lambda s: s.buzzer(),               "03 31 31 0a 6f"),
    (lambda s: s.compressor(),           "03 31 30 28 8c"),
    (lambda s: s.exhaust_valve(),        "03 31 2f 28 8b"),
    (lambda s: s.pump_relay(True),       "04 31 25 08 fa 5c"),
    (lambda s: s.raise_corner("left"),   "03 31 33 28 8f"),
    (lambda s: s.lower_corner("right"),  "03 31 36 28 92"),
])
def test_actuator_command_matches_capture(call, frame_hex):
    want = bytes.fromhex(frame_hex.replace(" ", ""))
    rid = want[2]
    responses = {want: _frame(bytes([0x71, rid, 0x20]))}
    ecu, slabs = _slabs(responses)
    with slabs:
        call(slabs)
    assert ecu.sent[-1] == want


def _f(d):
    from d2diag.kline import encode
    return encode(d, addressed=False)


def _slabs_over(responses):
    from d2diag.kline import KLine, encode
    from d2diag.kwp2000 import KWP2000
    from d2diag.slabs import SLABS_ADDRESS, Slabs
    from tests.fakes import FakeKLineEcu
    responses = dict(responses)
    responses[encode(b"\x81", SLABS_ADDRESS, 0xF7, addressed=True)] = _f(b"\xc1\x57\x8f")
    ecu = FakeKLineEcu(responses)
    return ecu, Slabs(KWP2000(KLine(ecu, target=SLABS_ADDRESS), tolerant=True))


def test_establish_confirms_session_with_1a_8a():
    # Reference tool skickar ALLTID 1A 8A som första begäran efter C1 (sniffen).
    # Vi speglar det och använder svaret som kvittens på att sessionen lever.
    ident = bytes.fromhex("00374460440310ff319010864000")
    ecu, slabs = _slabs_over({_f(b"\x1a\x8a"): _f(b"\x5a\x8a" + ident)})
    msgs = []
    with slabs:
        slabs.establish(sleep=lambda *_: None, progress=msgs.append)
    assert _f(b"\x1a\x8a") in ecu.sent                  # kvittensen gick ut
    assert any("session confirmed" in m for m in msgs)


def test_establish_reports_a_dead_session_but_does_not_raise():
    # Tolerant init letar bara efter C1 i bursten → kan ge falskt positivt
    # "session established" följt av noll läsningar (bilen 2026-08-18). Uteblir
    # svaret på 1A 8A ska loggen säga det — men etableringen får inte rivas.
    ecu, slabs = _slabs_over({})                        # inget svar på 1A 8A
    msgs = []
    with slabs:
        c1 = slabs.establish(sleep=lambda *_: None, progress=msgs.append)
    assert c1.startswith(b"\xc1\x57\x8f")               # etableringen står kvar
    assert any("no answer to 1A 8A" in m for m in msgs)


def test_functional_init_frame_matches_the_address_hunt():
    # Vår adressjakt 2026-08-05 fick svar från 0x29 ENBART i funktionellt läge med
    # testar-adress 0xF1: C1 29 F1 81 5c. muki01-referensen initierar likadant
    # (C1 33 F1 81 66). Ramen måste bli byte-identisk med den som fungerade.
    from d2diag.kline import encode
    from d2diag.slabs import SLABS_ADDRESS
    f = encode(b"\x81", SLABS_ADDRESS, 0xF1, addressed=True, functional=True)
    assert f.hex(" ") == "c1 29 f1 81 5c"


def test_establish_tries_functional_addressing_first():
    # FUNKTIONELLT först: i bilen 2026-08-19 stod de funktionella ramarna för
    # 6 träffar av 24 medan fysisk gav 1 av 21. Fysisk provas sist — den har trots
    # allt gett kontakt en gång, och det är den reference tool använder.
    from d2diag.kline import KLine, encode
    from d2diag.kwp2000 import KWP2000, KWP2000Error
    from d2diag.slabs import SLABS_ADDRESS, Slabs
    from tests.fakes import FakeKLineEcu

    functional = encode(b"\x81", SLABS_ADDRESS, 0xF1, addressed=True, functional=True)
    ecu = FakeKLineEcu({functional: encode(b"\xc1\x57\x8f", addressed=False)})
    slabs = Slabs(KWP2000(KLine(ecu, target=SLABS_ADDRESS, timeout=0.05), tolerant=True))
    msgs = []
    with slabs:
        slabs.establish(attempts=1, sleep=lambda *_: None, progress=msgs.append)

    physical = encode(b"\x81", SLABS_ADDRESS, 0xF7, addressed=True)
    assert functional in ecu.sent          # funktionell provas …
    assert physical not in ecu.sent        # … och räcker, fysisk behövs inte
    assert any("[funktionell, F1]" in m for m in msgs)   # syns i loggen


def test_establish_falls_back_to_physical_on_later_tries():
    # Alla tre lägena ska provas innan vi ger upp — fysisk sist.
    from d2diag.kline import KLine, encode
    from d2diag.kwp2000 import KWP2000
    from d2diag.slabs import SLABS_ADDRESS, Slabs
    from tests.fakes import FakeKLineEcu

    physical = encode(b"\x81", SLABS_ADDRESS, 0xF7, addressed=True)
    ecu = FakeKLineEcu({physical: encode(b"\xc1\x57\x8f", addressed=False)})
    slabs = Slabs(KWP2000(KLine(ecu, target=SLABS_ADDRESS, timeout=0.05), tolerant=True))
    with slabs:
        slabs.establish(attempts=3, sleep=lambda *_: None)
    sent = [f.hex(" ") for f in ecu.sent if len(f) == 5]
    assert sent == ["c1 29 f1 81 5c", "c1 29 f7 81 62", "81 29 f7 81 22"]
