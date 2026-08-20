# SPDX-License-Identifier: Apache-2.0
"""SPEC.md Sec 6.4 structural invariants + M1 exit criterion: bitstream
pack/unpack round-trips all 192 one-hot bitstreams byte-exact."""

from __future__ import annotations

import pytest

from mosbius import bitstream


def test_pack_empty_is_48_zero_chars():
    hx = bitstream.pack([])
    assert hx == "0" * 48
    assert len(hx) == 48


def test_pack_unpack_round_trip_all_192_one_hot_bits():
    for bit in range(192):
        hx = bitstream.pack([bit])
        assert len(hx) == 48
        back = bitstream.unpack(hx)
        assert back == frozenset({bit}), f"bit {bit} did not round-trip byte-exact"


def test_pack_unpack_round_trip_arbitrary_sets():
    cases = [
        set(),
        {0},
        {191},
        {0, 191},
        set(range(0, 192, 7)),
        set(range(192)),  # all bits set
    ]
    for bits in cases:
        hx = bitstream.pack(bits)
        assert bitstream.unpack(hx) == frozenset(bits)


def test_all_bits_set_is_all_f():
    hx = bitstream.pack(range(192))
    assert hx == "f" * 48


def test_bit_n_sets_expected_nibble():
    # Bit 191 is the top bit -> leftmost hex nibble is 8 (SPEC.md Sec 2.5).
    hx = bitstream.pack([191])
    assert hx[0] == "8"
    assert hx[1:] == "0" * 47
    # Bit 0 is the bottom bit -> rightmost nibble is 1.
    hx = bitstream.pack([0])
    assert hx[-1] == "1"
    assert hx[:-1] == "0" * 47


def test_pack_rejects_out_of_range_bit():
    with pytest.raises(bitstream.BitstreamError, match="out of range"):
        bitstream.pack([192])
    with pytest.raises(bitstream.BitstreamError, match="out of range"):
        bitstream.pack([-1])


def test_unpack_rejects_wrong_length():
    with pytest.raises(bitstream.BitstreamError, match="48"):
        bitstream.unpack("00")
    with pytest.raises(bitstream.BitstreamError, match="48"):
        bitstream.unpack("0" * 49)


def test_unpack_rejects_non_hex_characters():
    with pytest.raises(bitstream.BitstreamError, match="non-hex"):
        bitstream.unpack("g" * 48)


def test_unpack_accepts_0x_prefix():
    assert bitstream.unpack("0x" + "0" * 46 + "01") == frozenset({0})
