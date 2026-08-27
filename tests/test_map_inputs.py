"""Pure differential-mapping logic for tools/map_inputs.py — the noise mask + bit diff.

No hardware: these lock the behaviour that makes the mapper usable on a live bus (mask the
self-changing counter bits, keep the stable ones, and report only genuine flips).
"""
import tools.map_inputs as m


def test_bits_of_explodes_lsb_first():
    b = m.bits_of({"56": b"\x05"})   # 0b00000101
    assert b[("56", 0, 0)] == 1 and b[("56", 0, 2)] == 1
    assert b[("56", 0, 1)] == 0 and b[("56", 0, 3)] == 0


def test_volatile_bits_masks_only_the_self_changing_bit():
    # byte0 bit0 flips across the baseline (a counter); bit1 is steady.
    samples = [{"56": b"\x02"}, {"56": b"\x03"}, {"56": b"\x02"}]
    vol = m.volatile_bits(samples)
    assert ("56", 0, 0) in vol
    assert ("56", 0, 1) not in vol


def test_stable_bits_takes_the_mode_and_drops_masked():
    samples = [{"56": b"\x02"}, {"56": b"\x03"}, {"56": b"\x02"}]
    mask = m.volatile_bits(samples)
    stable = m.stable_bits(samples, mask)
    assert stable[("56", 0, 1)] == 1          # steady high
    assert ("56", 0, 0) not in stable          # masked (volatile)


def test_changed_bits_reports_only_real_flips():
    ref = m.stable_bits([{"56": b"\x00"}], set())
    cur = m.stable_bits([{"56": b"\x01"}], set())
    changes = m.changed_bits(ref, cur)
    assert ("56", 0, 0, 0, 1) in changes
    assert all(off == 0 and bit != 0 or (lid, off, bit) == ("56", 0, 0)
               for (lid, off, bit, _, _) in changes)  # only bit0 changed


def test_masked_bit_never_reported_as_changed():
    samples = [{"56": b"\x01"}, {"56": b"\x00"}]     # bit0 is noisy
    mask = m.volatile_bits(samples)
    ref = m.stable_bits(samples, mask)
    cur = m.stable_bits([{"56": b"\x01"}], mask)
    assert not any(bit == 0 for (_, _, bit, _, _) in m.changed_bits(ref, cur))
