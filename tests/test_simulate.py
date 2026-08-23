# SPDX-License-Identifier: Apache-2.0
"""mosbius/simulate.py -- TODO.md Sec 1 (closed 2026-08-23): a routed
design -> a real, silicon-accurate SPICE subcircuit.

Real EDA-toolchain verification (does the generated netlist actually
simulate to the right frequency) lives outside the test suite, same as
mosbius/spice.py's own tests -- see project memory `ring_oscillator_l2_sim`
for that. These tests check the generated SPICE text is structurally
correct and matches the routed config, which is checkable without the EDA
toolchain.
"""

from __future__ import annotations

import json

from mosbius.model import SwitchConfig
from mosbius.simulate import (
    name_from_routed_path,
    render_mosbius_wrapper,
    simulate_from_routed_json,
    used_external_pins,
)

# The exact measured ring-oscillator bitstream (project memory
# `ring_oscillator_l2_sim`) -- known, from real investigation this
# session, to use ua[1] directly and ua[2]/ua[4] via a cfg_bus_short
# merge (its own device terminals sit on the *opposite* bus side from
# the pin's own bonded row). A real regression target for the short-merge
# case, not a synthetic one.
MEASURED_RING_BITSTREAM = "380088007001000010000404250109000400000040000014"


def test_used_external_pins_inverter(inverter_config):
    # make_inverter_config() (tests/conftest.py): nmos_a/pmos_a gates and
    # drains on ua[1]/ua[2] -- no cfg_bus_short involved, the simple case.
    assert used_external_pins(inverter_config) == ["ua[1]", "ua[2]"]


def test_used_external_pins_resolves_bus_short_merge():
    # ua[2]/ua[4]'s real devices sit on the opposite bus side from the
    # pin's own bonded row, reachable only via a closed cfg_bus_short --
    # the exact case this session's investigation had to reason through
    # by hand. used_external_pins() must resolve it via graph
    # connectivity alone, no special-casing.
    config = SwitchConfig.from_bitstream(MEASURED_RING_BITSTREAM)
    assert used_external_pins(config) == ["ua[1]", "ua[2]", "ua[4]"]


def test_used_external_pins_empty_config():
    assert used_external_pins(SwitchConfig(bits=frozenset())) == []


def test_wrapper_subckt_name_and_port_list():
    config = SwitchConfig.from_bitstream(MEASURED_RING_BITSTREAM)
    text = render_mosbius_wrapper(config, "ring")
    assert "\n.subckt ring_mosbius ibias ua1 ua2 ua3 ua4 ua5 VAPWR VDPWR VGND\n" in "\n" + text


def test_wrapper_is_self_contained_no_include():
    config = SwitchConfig.from_bitstream(MEASURED_RING_BITSTREAM)
    text = render_mosbius_wrapper(config, "ring")
    assert ".include" not in text


def test_wrapper_contains_config_ties_and_bus_wire_caps():
    config = SwitchConfig.from_bitstream(MEASURED_RING_BITSTREAM)
    text = render_mosbius_wrapper(config, "ring")
    assert len([l for l in text.splitlines() if l.startswith("Rcfg")]) == 192
    assert len([l for l in text.splitlines() if l.startswith("Cwire")]) == 12


def test_wrapper_pad_instances_match_used_pins_only():
    config = SwitchConfig.from_bitstream(MEASURED_RING_BITSTREAM)
    text = render_mosbius_wrapper(config, "ring")
    pad_lines = [l for l in text.splitlines() if l.startswith("Xpad_")]
    assert len(pad_lines) == 3
    assert "Xpad_ua1 VGND ua1 bus_A[1] pad_model" in text
    assert "Xpad_ua2 VGND ua2 bus_A[3] pad_model" in text
    assert "Xpad_ua4 VGND ua4 bus_B[2] pad_model" in text
    # ua3/ua5 are unused by this bitstream -- no pad instance for either.
    assert "Xpad_ua3" not in text
    assert "Xpad_ua5" not in text


def test_wrapper_empty_config_gets_no_pad_instances():
    text = render_mosbius_wrapper(SwitchConfig(bits=frozenset()), "empty")
    assert "Xpad_" not in text
    assert "none -- this config uses no real package pin" in text


def test_wrapper_row_coupling_caps_land_inside_subckt_mosbius_not_outside():
    # The exact bug this session's investigation hit and fixed on
    # tools/run_ringo_row_coupling.sh: a coupling cap referencing a
    # subcircuit-internal node from OUTSIDE .subckt mosbius creates a
    # disconnected phantom node, not a real connection. Verify the caps
    # are actually between the subckt's own port header and its matching
    # .ends, not merely present somewhere in the file.
    config = SwitchConfig.from_bitstream(MEASURED_RING_BITSTREAM)
    text = render_mosbius_wrapper(config, "ring")
    lines = text.splitlines()

    inner_start = next(i for i, l in enumerate(lines) if l.startswith(".subckt mosbius "))
    inner_end = next(i for i in range(inner_start, len(lines)) if lines[i].startswith(".ends"))

    caps_inside = [l for l in lines[inner_start:inner_end] if l.startswith("Ccpl_")]
    caps_outside = [l for l in lines[:inner_start] + lines[inner_end:] if l.startswith("Ccpl_")]

    assert len(caps_inside) == 150
    assert len(caps_outside) == 0


def test_wrapper_subckt_ends_balanced():
    config = SwitchConfig.from_bitstream(MEASURED_RING_BITSTREAM)
    text = render_mosbius_wrapper(config, "ring")
    # 10 subckts from the embedded device library + this wrapper's own
    # ring_mosbius == 11, both properly newline-preceded (the wrapper's
    # own .subckt line isn't the literal first line of the file -- header
    # comments come first).
    assert text.count("\n.subckt ") == 11
    assert text.count("\n.ends") == 11


def test_name_from_routed_path_strips_mosbius_json_suffix():
    from pathlib import Path

    assert name_from_routed_path(Path("build/ring.mosbius.json")) == "ring"
    assert name_from_routed_path(Path("/tmp/other.json")) == "other"


def test_simulate_from_routed_json(tmp_path):
    routed_path = tmp_path / "ring.mosbius.json"
    routed_path.write_text(json.dumps({
        "schema": 1,
        "bitstream": MEASURED_RING_BITSTREAM,
        "ibias": 100e-6,
        "device_roles": {},
        "net_rows": {},
    }))

    name, text = simulate_from_routed_json(routed_path)

    assert name == "ring"
    assert ".subckt ring_mosbius" in text
    assert "Xpad_ua1" in text
