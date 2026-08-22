# SPDX-License-Identifier: Apache-2.0
"""mosbius/spice.py -- SPEC.md Sec 3.7 config include generation.

The actual ngspice/xschem-level verification (does this drive real
silicon-accurate rise time) lives outside the test suite -- see the M2
milestone notes. These tests check the generated SPICE text is
well-formed and correct against the bit map, which is what's checkable
without the EDA toolchain.
"""

from __future__ import annotations

from mosbius.bitmap import ALL_BITS
from mosbius.model import SwitchConfig
from mosbius.spice import (
    BUS_WIRE_CAPACITANCE_F,
    SINGLE_BIT_PINS,
    render_bus_wire_caps,
    render_config_spice,
)

from .conftest import bit_for, setting_bit


def test_render_has_192_ties():
    text = render_config_spice(SwitchConfig(bits=frozenset()))
    tie_lines = [l for l in text.splitlines() if l.startswith("Rcfg")]
    assert len(tie_lines) == 192


def test_empty_config_ties_everything_to_vgnd():
    text = render_config_spice(SwitchConfig(bits=frozenset()))
    tie_lines = [l for l in text.splitlines() if l.startswith("Rcfg")]
    assert all(l.endswith("VGND 0") for l in tie_lines)


def test_all_bits_set_ties_everything_to_vdpwr():
    text = render_config_spice(SwitchConfig(bits=frozenset(range(192))))
    tie_lines = [l for l in text.splitlines() if l.startswith("Rcfg")]
    assert all(l.endswith("VDPWR 0") for l in tie_lines)


def test_net_names_match_bitmap_pin_and_index(inverter_config):
    text = render_config_spice(inverter_config)
    lines = {l.split()[0]: l for l in text.splitlines() if l.startswith("Rcfg")}

    d_bit = bit_for("cfga_nfeta_d", 3)
    line = lines[f"Rcfg{d_bit}"]
    assert "cfga_nfeta_d[3]" in line
    assert line.endswith("VDPWR 0")

    source_bit = setting_bit("ctrl_nfeta_source")
    line = lines[f"Rcfg{source_bit}"]
    # Single-bit pins netlist bare, with no [index] suffix.
    assert " ctrl_nfeta_source " in line
    assert "[" not in line.split()[1]


def test_single_bit_pins_have_no_bracket_suffix():
    text = render_config_spice(SwitchConfig(bits=frozenset()))
    for bit in range(192):
        info = ALL_BITS[bit]
        if info.pin not in SINGLE_BIT_PINS:
            continue
        line = next(l for l in text.splitlines() if l.startswith(f"Rcfg{bit} "))
        pin_net = line.split()[1]
        assert pin_net == info.pin, f"bit {bit}: {pin_net!r} != bare {info.pin!r}"


def test_multibit_pins_get_bracket_suffix(inverter_config):
    text = render_config_spice(inverter_config)
    g_bit = bit_for("cfga_nfeta_g", 1)
    line = next(l for l in text.splitlines() if l.startswith(f"Rcfg{g_bit} "))
    assert line.split()[1] == "cfga_nfeta_g[1]"


def test_bus_wire_capacitance_covers_all_12_rows():
    assert len(BUS_WIRE_CAPACITANCE_F) == 12
    for side in ("A", "B"):
        for row in range(1, 7):
            assert f"bus_{side}[{row}]" in BUS_WIRE_CAPACITANCE_F


def test_bus_wire_capacitance_values_are_real_not_placeholder():
    # These are real magic PEX extraction values (see the module docstring
    # for how they were derived) -- not a flat guess. The earlier,
    # never-verified hand-estimate this replaced was ~30-50fF; the real
    # values are all at least an order of magnitude bigger than that,
    # which is the whole point of extracting them instead of guessing.
    for farads in BUS_WIRE_CAPACITANCE_F.values():
        assert farads > 500e-15, "value looks too close to the old, wrong hand-estimate"
        assert farads < 2000e-15, "value looks implausibly large, double check the extraction"


def test_render_bus_wire_caps_has_12_capacitors():
    text = render_bus_wire_caps()
    cap_lines = [l for l in text.splitlines() if l.startswith("Cwire")]
    assert len(cap_lines) == 12


def test_render_bus_wire_caps_ties_to_vgnd():
    text = render_bus_wire_caps()
    cap_lines = [l for l in text.splitlines() if l.startswith("Cwire")]
    assert all(l.split()[2] == "VGND" for l in cap_lines)


def test_render_bus_wire_caps_covers_every_bus_node_name():
    text = render_bus_wire_caps()
    for net in BUS_WIRE_CAPACITANCE_F:
        assert f" {net} VGND " in text
