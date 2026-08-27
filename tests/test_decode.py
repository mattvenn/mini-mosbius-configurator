# SPDX-License-Identifier: Apache-2.0
"""mosbius/decode.py -- SPEC.md Sec 3.8.

M1 exit criterion: decoding a known-good bitstream yields the expected
circuit. `inverter_config` (tests/conftest.py) is hand-built directly from
the verified bit map -- decoding it back out and getting the same
transistor-level structure is the strongest self-consistency check
available on the map before real hardware (M4) exists.
"""

from __future__ import annotations

from mosbius.decode import decode, format_summary
from mosbius.model import SwitchConfig

from .conftest import bit_for


def test_decode_empty_config_has_no_devices():
    decoded = decode(SwitchConfig(bits=frozenset()))
    assert decoded.devices == []


def test_decode_inverter_yields_expected_devices(inverter_config):
    decoded = decode(inverter_config)
    by_name = {d.name: d for d in decoded.devices}

    assert set(by_name) == {"nmos_a", "pmos_a"}

    nmos_a = by_name["nmos_a"]
    assert nmos_a.terminals["g"] == by_name["pmos_a"].terminals["g"]
    assert nmos_a.terminals["d"] == by_name["pmos_a"].terminals["d"]
    assert nmos_a.terminals["g"] != nmos_a.terminals["d"]
    assert nmos_a.settings["source_tied_to_VGND"] is True
    assert by_name["pmos_a"].settings["source_tied_to_VAPWR"] is True


def test_decode_inverter_input_and_output_nets_reach_expected_pins(inverter_config):
    decoded = decode(inverter_config)
    by_name = {d.name: d for d in decoded.devices}
    gate_net = by_name["nmos_a"].terminals["g"]
    drain_net = by_name["nmos_a"].terminals["d"]

    net_by_name = {n.name: n for n in decoded.nets}
    assert "ua[1]" in net_by_name[gate_net].nodes
    assert "bus_A[1]" in net_by_name[gate_net].nodes
    assert "ua[2]" in net_by_name[drain_net].nodes
    assert "bus_A[3]" in net_by_name[drain_net].nodes


def test_decode_drops_devices_with_all_terminals_isolated():
    # A config that only closes an unrelated switch shouldn't report every
    # other device in the chip as "in use".
    config = SwitchConfig(bits=frozenset({bit_for("cfga_mirn_a", 1)}))
    decoded = decode(config)
    names = {d.name for d in decoded.devices}
    assert names == {"nsink_a"}


def test_format_summary_mentions_devices_and_nets(inverter_config):
    text = format_summary(decode(inverter_config))
    assert "nmos_a" in text
    assert "pmos_a" in text
    assert "ua[1]" in text
    assert "ua[2]" in text
    assert "ibias" in text


def test_format_summary_empty_design_says_so():
    text = format_summary(decode(SwitchConfig(bits=frozenset())))
    assert "none" in text.lower()


def test_net_line_names_the_segment_each_pin_is_really_bonded_to():
    """A net joined across both bus sides by cfg_bus_short holds two
    segments. The pin must be shown against its own -- ua[4] is bus_B[2],
    and printing the net's alphabetically-first segment named bus_A[2]
    instead, which reads as the wrong bond (CLAUDE.md trap 1).
    """
    from mosbius.decode import decode, format_summary
    from mosbius.model import SwitchConfig

    config = SwitchConfig.from_bitstream("3f008803f00400140100021018840600005004010000001d")
    text = format_summary(decode(config))
    assert "ua[4] (bus_B[2])" in text
    assert "ua[4] (bus_A[2])" not in text
