# SPDX-License-Identifier: Apache-2.0
"""Structural cross-validation for mosbius/bitmap.py (SPEC.md Sec 6.1, M0 exit criterion).

These checks are written independently of tools/extract_bitmap.py's own
cross_validate() -- they re-derive their expectations from SPEC.md's VERIFIED
sections (transcribed, not re-derived) so a bug in the extraction script's
own validation logic doesn't get a free pass here.
"""

from __future__ import annotations

import re

import pytest

from mosbius.bitmap import ALL_BITS, DEVICE_SETTING_BITS, MATRIX_BITS

# SPEC.md Sec 2.3 -- VERIFIED layout column order (position = X / 1840).
COLUMN_ORDER = [
    "asw_col_short_0", "asw_col_a_0", "asw_col_b_0", "asw_col_ab_0",
    "asw_col_a_1", "asw_col_a_2", "asw_col_b_1", "asw_col_b_2", "asw_col_b_3",
    "asw_col_a_3", "asw_col_a_4", "asw_col_b_4", "asw_col_ab_1", "asw_col_a_5",
    "asw_col_b_5", "asw_col_ab_2", "asw_col_a_6", "asw_col_b_6", "asw_col_a_7",
    "asw_col_b_7", "asw_col_a_8", "asw_col_b_8", "asw_col_b_9", "asw_col_b_10",
    "asw_col_a_9", "asw_col_a_10",
]
assert len(COLUMN_ORDER) == 26

# SPEC.md Sec 2.4 -- VERIFIED pin width budget.
EXPECTED_TOTAL_BITS = 192
EXPECTED_CFGA_BITS = 75
EXPECTED_CFGB_BITS = 75
EXPECTED_BUS_SHORT_BITS = 6
EXPECTED_BUS_PWR_BITS = 6
EXPECTED_CTRL_BITS = 30

# SPEC.md Sec 2.7 -- VERIFIED cfg_bus_pwr rail assignment, cross-checked
# independently against the netlist and the configurator.
EXPECTED_BUS_PWR_TABLE = {
    # cfg_bus_pwr index -> (side, row, rail)
    6: ("B", 6, "VAPWR"),
    5: ("A", 4, "VAPWR"),
    4: ("B", 1, "VAPWR"),
    3: ("A", 6, "VGND"),
    2: ("B", 5, "VGND"),
    1: ("A", 2, "VGND"),
}

# SPEC.md Sec 2.10 -- VERIFIED external analog pin map.
EXPECTED_EXTERNAL_PINS = {
    "ua[1]": ("A", 1), "ua[2]": ("A", 3), "ua[3]": ("A", 5),
    "ua[4]": ("B", 2), "ua[5]": ("B", 4),
}

# SPEC.md Sec 2.8 -- the 30 cfg signals, their side and pin-array width.
THREE_BIT_SIGNALS = {
    "cfga_otan_inp", "cfgb_otan_inm", "cfga_dpn_inp", "cfgb_dpn_inm",
    "cfga_dpp_inp", "cfgb_dpp_inm",
}
SIX_BIT_A_SIGNALS = {
    "cfga_otan_outp", "cfga_mirn_a", "cfga_mirp_a", "cfga_dpn_outp",
    "cfga_dpp_outp", "cfga_nfeta_d", "cfga_nfeta_g", "cfga_nfeta_s",
    "cfga_pfeta_d", "cfga_pfeta_g", "cfga_pfeta_s",
}
SIX_BIT_B_SIGNALS = {
    "cfgb_otan_outm", "cfgb_mirn_b", "cfgb_mirp_b", "cfgb_dpn_outm",
    "cfgb_dpp_outm", "cfgb_nfetb_d", "cfgb_nfetb_g", "cfgb_nfetb_s",
    "cfgb_pfetb_d", "cfgb_pfetb_g", "cfgb_pfetb_s",
}
ALL_30_SIGNALS = THREE_BIT_SIGNALS | SIX_BIT_A_SIGNALS | SIX_BIT_B_SIGNALS | {
    "cfg_bus_short", "cfg_bus_pwr",
}
assert len(ALL_30_SIGNALS) == 30


def test_all_192_bits_claimed_exactly_once():
    assert set(ALL_BITS) == set(range(192))
    assert len(ALL_BITS) == 192
    assert len(MATRIX_BITS) + len(DEVICE_SETTING_BITS) == 192


def test_matrix_bits_are_162_and_device_settings_30():
    # 156 matrix-column bits + 6 cfg_bus_short + ... wait: cfg_bus_short IS
    # one of the 156 (it's column 0). So: 156 column bits (of which 6 are
    # cfg_bus_short) + 6 cfg_bus_pwr (outside the column matrix) = 162.
    assert len(MATRIX_BITS) == 162
    assert len(DEVICE_SETTING_BITS) == 30


def test_every_cfg_signal_claimed_by_exactly_one_column_or_group():
    bits_by_pin: dict[str, list[int]] = {}
    for mb in MATRIX_BITS.values():
        bits_by_pin.setdefault(mb.pin, []).append(mb.bit)

    assert set(bits_by_pin) == ALL_30_SIGNALS

    for sig in THREE_BIT_SIGNALS:
        assert len(bits_by_pin[sig]) == 3, sig
    for sig in SIX_BIT_A_SIGNALS | SIX_BIT_B_SIGNALS:
        assert len(bits_by_pin[sig]) == 6, sig
    assert len(bits_by_pin["cfg_bus_short"]) == 6
    assert len(bits_by_pin["cfg_bus_pwr"]) == 6

    # Every signal's bits sit on a single column base (except bus_pwr, which
    # is not on the column matrix at all -- checked separately below).
    for sig in (THREE_BIT_SIGNALS | SIX_BIT_A_SIGNALS | SIX_BIT_B_SIGNALS | {"cfg_bus_short"}):
        bases = {b - (b % 6) for b in bits_by_pin[sig]}
        assert len(bases) == 1, f"{sig} spans multiple column bases: {bits_by_pin[sig]}"


def test_a_side_signals_only_on_a_side_columns_b_only_on_b():
    bits_by_pin: dict[str, list[int]] = {}
    for mb in MATRIX_BITS.values():
        bits_by_pin.setdefault(mb.pin, []).append(mb.bit)

    for sig in SIX_BIT_A_SIGNALS:
        base = min(bits_by_pin[sig]) - (min(bits_by_pin[sig]) % 6)
        col = COLUMN_ORDER[base // 6]
        assert "_a_" in col, f"{sig} (A-side signal) sits on {col}"
    for sig in SIX_BIT_B_SIGNALS:
        base = min(bits_by_pin[sig]) - (min(bits_by_pin[sig]) % 6)
        col = COLUMN_ORDER[base // 6]
        assert "_b_" in col, f"{sig} (B-side signal) sits on {col}"

    # MatrixBit.bus must also agree with the pin's own side prefix.
    for mb in MATRIX_BITS.values():
        if mb.pin.startswith("cfga_"):
            assert mb.bus == "A", mb
        elif mb.pin.startswith("cfgb_"):
            assert mb.bus == "B", mb


def test_three_bit_signals_only_on_ab_columns():
    bits_by_pin: dict[str, list[int]] = {}
    for mb in MATRIX_BITS.values():
        bits_by_pin.setdefault(mb.pin, []).append(mb.bit)

    for sig in THREE_BIT_SIGNALS:
        base = min(bits_by_pin[sig]) - (min(bits_by_pin[sig]) % 6)
        col = COLUMN_ORDER[base // 6]
        assert "_ab_" in col, f"{sig} (3-bit signal) sits on non-ab column {col}"


def test_192_bit_budget_closes_by_group():
    def count(pred):
        return sum(1 for mb in MATRIX_BITS.values() if pred(mb))

    cfga_count = count(lambda mb: mb.pin.startswith("cfga_"))
    cfgb_count = count(lambda mb: mb.pin.startswith("cfgb_"))
    short_count = count(lambda mb: mb.pin == "cfg_bus_short")
    pwr_count = count(lambda mb: mb.pin == "cfg_bus_pwr")

    assert cfga_count == EXPECTED_CFGA_BITS
    assert cfgb_count == EXPECTED_CFGB_BITS
    assert short_count == EXPECTED_BUS_SHORT_BITS
    assert pwr_count == EXPECTED_BUS_PWR_BITS
    assert len(DEVICE_SETTING_BITS) == EXPECTED_CTRL_BITS
    assert (cfga_count + cfgb_count + short_count + pwr_count
            + len(DEVICE_SETTING_BITS)) == EXPECTED_TOTAL_BITS


def test_cfg_bus_short_is_column_zero_bits_zero_to_five():
    bits = sorted(mb.bit for mb in MATRIX_BITS.values() if mb.pin == "cfg_bus_short")
    assert bits == [0, 1, 2, 3, 4, 5]


def test_cfg_bus_pwr_matches_verified_rail_table():
    pwr_bits = {mb.index: mb for mb in MATRIX_BITS.values() if mb.pin == "cfg_bus_pwr"}
    assert set(pwr_bits) == set(range(1, 7))
    for idx, (side, row, rail) in EXPECTED_BUS_PWR_TABLE.items():
        mb = pwr_bits[idx]
        assert mb.bus == side, f"cfg_bus_pwr[{idx}]: bus {mb.bus} != {side}"
        assert mb.row == row, f"cfg_bus_pwr[{idx}]: row {mb.row} != {row}"
        assert mb.rail == rail, f"cfg_bus_pwr[{idx}]: rail {mb.rail} != {rail}"
        assert mb.crosspoint is None


def test_row_offset_pattern_is_uniform_across_full_columns():
    # SPEC.md Sec 2.7: every full column has the identical row pattern
    # row 1 2 3 4 5 6 -> bit offset 0 2 4 1 3 5.
    expected_offset_for_row = {1: 0, 2: 2, 3: 4, 4: 1, 5: 3, 6: 5}
    full_signals = SIX_BIT_A_SIGNALS | SIX_BIT_B_SIGNALS
    for mb in MATRIX_BITS.values():
        if mb.pin not in full_signals:
            continue
        base = mb.bit - (mb.bit % 6)
        offset = mb.bit - base
        assert offset == expected_offset_for_row[mb.row], (
            f"{mb.pin}[{mb.index}] bit {mb.bit}: offset {offset} != "
            f"expected {expected_offset_for_row[mb.row]} for row {mb.row}"
        )


def test_ab_columns_split_even_offsets_to_a_odd_to_b():
    for mb in MATRIX_BITS.values():
        if mb.pin not in THREE_BIT_SIGNALS:
            continue
        base = mb.bit - (mb.bit % 6)
        offset = mb.bit - base
        if mb.pin.startswith("cfga_"):
            assert offset % 2 == 0, f"{mb.pin} bit {mb.bit}: expected even offset, got {offset}"
        else:
            assert offset % 2 == 1, f"{mb.pin} bit {mb.bit}: expected odd offset, got {offset}"
        # And 3-bit signals only ever reach rows 1-3 (SPEC.md Sec 2.12).
        assert mb.row in (1, 2, 3)


def test_crosspoint_naming_matches_pin_signal_name():
    # cfga_<signal>_<terminal> / cfgb_<signal>_<terminal> must drive
    # xpt_<signal>_<terminal> (SPEC.md Sec 2.8), for every non-short/pwr bit.
    for mb in MATRIX_BITS.values():
        if mb.pin in ("cfg_bus_short", "cfg_bus_pwr"):
            continue
        suffix = mb.pin[len("cfga_"):] if mb.pin.startswith("cfga_") else mb.pin[len("cfgb_"):]
        assert mb.crosspoint == f"xpt_{suffix}", mb


def test_every_column_base_claimed_exactly_once():
    claimed_bases = set()
    for mb in MATRIX_BITS.values():
        if mb.pin == "cfg_bus_pwr":
            continue  # not part of the 26-column matrix
        claimed_bases.add(mb.bit - (mb.bit % 6))
    expected_bases = {pos * 6 for pos in range(26)}
    assert claimed_bases == expected_bases


def test_device_setting_bits_cover_widths_ratios_tails_sources_mode():
    pins = {sb.pin for sb in DEVICE_SETTING_BITS.values()}
    expected_pins = {
        "ctrl_pfeta_width", "ctrl_pfetb_width", "ctrl_nfeta_width", "ctrl_nfetb_width",
        "ctrl_mirp_a", "ctrl_mirp_b", "ctrl_mirn_a", "ctrl_mirn_b",
        "ctrl_dpp_tail", "ctrl_dpn_tail", "ctrl_otan_tail",
        "ctrl_pfeta_source", "ctrl_pfetb_source", "ctrl_nfeta_source", "ctrl_nfetb_source",
        "ctrl_dpp_source", "ctrl_dpn_source",
        "ctrl_otan_mode",
    }
    assert pins == expected_pins, pins ^ expected_pins


def test_device_setting_bits_confined_to_their_ctrl_top_block_range():
    # SPEC.md Sec 2.2 (VERIFIED chain composition) + Sec 2.11 caveat: block
    # *names* don't indicate function, but the *bit ranges* are exact.
    block_ranges = {
        (156, 161): {"ctrl_pfeta_width", "ctrl_pfeta_source", "ctrl_pfetb_source", "ctrl_pfetb_width"},
        (162, 167): {"ctrl_dpp_tail", "ctrl_mirp_b", "ctrl_mirp_a"},
        (168, 171): {"ctrl_dpp_source"},  # + cfg_bus_pwr, which is a MatrixBit not a DeviceSettingBit
        (172, 175): {"ctrl_dpn_source"},  # + cfg_bus_pwr
        (176, 183): {"ctrl_mirn_b", "ctrl_mirn_a", "ctrl_dpn_tail", "ctrl_otan_tail"},
        (184, 189): {"ctrl_nfetb_width", "ctrl_nfetb_source", "ctrl_nfeta_source", "ctrl_nfeta_width"},
        (190, 191): {"ctrl_otan_mode"},
    }
    for (lo, hi), expected_pins in block_ranges.items():
        pins_in_range = {
            sb.pin for bit, sb in DEVICE_SETTING_BITS.items() if lo <= bit <= hi
        }
        assert pins_in_range == expected_pins, (
            f"bits {lo}-{hi}: {pins_in_range} != {expected_pins}"
        )


def test_two_bit_fields_have_both_indices_present():
    two_bit_pins = {
        "ctrl_pfeta_width", "ctrl_pfetb_width", "ctrl_nfeta_width", "ctrl_nfetb_width",
        "ctrl_mirp_a", "ctrl_mirp_b", "ctrl_mirn_a", "ctrl_mirn_b",
        "ctrl_dpp_tail", "ctrl_dpn_tail", "ctrl_otan_tail", "ctrl_otan_mode",
    }
    indices_by_pin: dict[str, set[int]] = {}
    for sb in DEVICE_SETTING_BITS.values():
        indices_by_pin.setdefault(sb.pin, set()).add(sb.index)
    for pin in two_bit_pins:
        assert indices_by_pin[pin] == {0, 1}, f"{pin}: {indices_by_pin[pin]}"


def test_no_bit_appears_in_both_matrix_and_device_setting_dicts():
    assert set(MATRIX_BITS).isdisjoint(set(DEVICE_SETTING_BITS))
