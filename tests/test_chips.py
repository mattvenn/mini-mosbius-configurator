# SPDX-License-Identifier: Apache-2.0
"""mosbius/chips/ -- the per-part descriptor the router, checker and SPICE
writer are all driven from.

Most of what a Chip exposes is derived from its generated bit table rather
than transcribed, which is the point: a regenerated table cannot drift away
from the rows the router believes exist. These tests pin the derivations
against the facts SPEC.md and CLAUDE.md state independently, so a wrong
derivation fails here rather than as a mysterious routing result.
"""

from __future__ import annotations

import pytest

from mosbius import bitstream, messages
from mosbius.chips import TNT, UnknownChipError, chip_for_macro
from mosbius.model import SwitchConfig


def test_tnt_chain_is_192_bits_in_48_hex_characters():
    assert TNT.num_bits == 192
    assert TNT.hex_chars == 48
    assert len(TNT.all_bits) == 192
    assert len(TNT.matrix_bits) == 162
    assert len(TNT.setting_bits) == 30


def test_tnt_has_28_crosspoints():
    """CLAUDE.md trap 5: 28 crosspoints, not the 37 the web configurator
    suggests."""
    assert len(TNT.crosspoints) == 28


def test_tnt_external_pins_straddle_both_bus_sides():
    """CLAUDE.md trap 1, the single easiest fact here to get backwards:
    three pins on side A, two on side B, and info.yaml's "Bus 1A".."Bus 5A"
    labels are pin names rather than segment identities."""
    assert TNT.external_pins == {
        "ua[1]": ("A", 1),
        "ua[2]": ("A", 3),
        "ua[3]": ("A", 5),
        "ua[4]": ("B", 2),
        "ua[5]": ("B", 4),
    }
    assert TNT.ibias_pin == "ua[0]"


def test_tnt_row_6_is_the_only_row_free_on_both_sides():
    """Which rows a net spanning both bus sides can use follows from the pin
    map rather than being an independent fact. On tnt's part it comes out as
    row 6 alone, which is why two-sided nets compete for one row."""
    assert TNT.joinable_rows == [6]


def test_tnt_rail_taps_are_three_per_rail_on_fixed_rows():
    taps = TNT.rail_tap_by_side_row
    assert len(taps) == 6
    by_rail: dict[str, list] = {}
    for (side, row), (_bit, rail) in taps.items():
        by_rail.setdefault(rail, []).append((side, row))
    assert sorted(by_rail["VAPWR"]) == [("A", 4), ("B", 1), ("B", 6)]
    assert sorted(by_rail["VGND"]) == [("A", 2), ("A", 6), ("B", 5)]


def test_diffpair_and_ota_inputs_reach_only_rows_1_to_3():
    """CLAUDE.md trap 6. Everything else reaches all six rows."""
    limited = {"cfga_dpn_inp", "cfgb_dpn_inm", "cfga_dpp_inp", "cfgb_dpp_inm",
               "cfga_otan_inp", "cfgb_otan_inm"}
    for pin, rows in TNT.rows_by_pin.items():
        expected = frozenset({1, 2, 3}) if pin in limited else frozenset(range(1, 7))
        assert rows == expected, pin


def test_tnt_pins_are_bond_wires_not_switches():
    """A bond wire has no bit, so its row is spent whether the design wanted
    the pin or not. That is what makes those rows unusable for internal
    nets."""
    assert TNT.pins.switched is False
    assert TNT.pinned_rows == {("A", 1), ("A", 3), ("A", 5), ("B", 2), ("B", 4)}
    assert TNT.free_rows == TNT.all_rows - TNT.pinned_rows


def test_the_ota_is_the_one_device_on_both_bus_sides():
    """Side is a property of a terminal, not of a device: asking for the
    OTA's side is what used to raise KeyError('ota')."""
    assert TNT.terminal_side[("ota", "inp")] == "A"
    assert TNT.terminal_side[("ota", "outp")] == "A"
    assert TNT.terminal_side[("ota", "inm")] == "B"
    assert TNT.terminal_side[("ota", "outm")] == "B"


def test_crosspoints_translate_back_to_the_names_a_user_drew():
    """CLAUDE.md: internal hardware identifiers get translated before a user
    ever reads one."""
    assert TNT.terminal_by_crosspoint["xpt_dpn_inp"] == "ndiffpair+.g"
    assert TNT.terminal_by_crosspoint["xpt_mirn_a"] == "nsink_a.out"


def test_chip_for_macro_finds_the_default_part():
    assert chip_for_macro("tt_um_tnt_mosbius") is TNT


def test_an_unmapped_macro_stops_rather_than_guessing():
    """The other mini-MOSbius is real and is on four shuttles, so this is a
    macro a user can plausibly type. Guessing would produce an unrelated
    circuit, not a slightly wrong one."""
    with pytest.raises(UnknownChipError) as excinfo:
        chip_for_macro("tt_um_mosbius")
    message = str(excinfo.value)
    assert "tt_um_mosbius" in message
    assert "tt_um_tnt_mosbius" in message
    assert "--project" in message


# --- chain length is a property of the part, not a constant ----------------

def test_a_chain_that_is_not_a_multiple_of_four_bits_rounds_up():
    """Andrew Kang's part has 196 bits, which is 49 hex characters. Packing
    it as 192 // 4 would silently drop the top nibble."""
    assert bitstream.hex_chars(192) == 48
    assert bitstream.hex_chars(196) == 49
    assert bitstream.hex_chars(193) == 49


def test_pack_and_unpack_round_trip_at_a_non_default_length():
    bits = frozenset({0, 195})
    packed = bitstream.pack(bits, 196)
    assert len(packed) == 49
    assert bitstream.unpack(packed, 196) == bits


def test_a_bitstream_of_the_wrong_length_is_refused():
    """Almost always a truncated paste, or a bitstream built for the other
    part -- both worth stopping for."""
    with pytest.raises(bitstream.BitstreamError):
        bitstream.unpack("0" * 49, 192)


def test_a_switch_config_validates_against_its_own_chip():
    with pytest.raises(ValueError) as excinfo:
        SwitchConfig(bits=frozenset({192}), chip=TNT)
    assert str(excinfo.value) == messages.MODEL_BIT_OUT_OF_RANGE.format(
        bad=[192], max_bit=191, num_bits=192,
    )
