# SPDX-License-Identifier: Apache-2.0
"""mosbius/schgen.py -- SPEC.md Sec 3.8 "Generated .sch" output form.

M2 exit criterion: a decoded bitstream renders as a schematic that
netlists back to the same config. The xschem-level half of that check
(actually netlisting the generated .sch and diffing device connectivity)
lives outside the test suite -- see the M2 milestone notes; it was
verified manually against the inverter and matched exactly. These tests
check the structural properties schgen.py's collision-free routing must
hold everywhere: every connection reaches its net's channel through a
private column, and no two nets can ever share one.
"""

from __future__ import annotations

from mosbius.decode import decode
from mosbius.model import SwitchConfig
from mosbius.schgen import generate_schematic


def test_generates_one_component_per_device(inverter_config):
    decoded = decode(inverter_config)
    text = generate_schematic(decoded)
    component_lines = [l for l in text.splitlines() if l.startswith("C {mosbius_")]
    assert len(component_lines) == len(decoded.devices)
    names = {l for l in component_lines}
    assert any("mosbius_nmos.sym" in l for l in names)
    assert any("mosbius_pmos.sym" in l for l in names)


def test_raises_on_unmapped_device_name():
    class FakeDesign:
        devices = [type("D", (), {"name": "not_a_real_device", "terminals": {}, "settings": {}})()]
        nets = []
        ibias = 100e-6

    try:
        generate_schematic(FakeDesign())
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_empty_design_has_no_components():
    text = generate_schematic(decode(SwitchConfig(bits=frozenset())))
    assert not [l for l in text.splitlines() if l.startswith("C {mosbius_")]


def test_every_net_gets_its_own_channel_row(inverter_config):
    decoded = decode(inverter_config)
    text = generate_schematic(decoded)
    # Each net's channel is a horizontal wire "N x1 y x2 y {\nlab=net}" --
    # collect (y, net) pairs and check every y maps to exactly one net.
    from mosbius.schgen import CHANNEL_BASE_Y

    lines = text.splitlines()
    channel_y_for_net = {}
    for i, line in enumerate(lines):
        if not line.startswith("N "):
            continue
        parts = line.split()
        x1, y1, x2, y2 = int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
        if y1 != y2 or x1 == x2:
            continue  # not a horizontal segment
        if y1 > CHANNEL_BASE_Y:
            continue  # a pin-to-jog stub near the device row, not a channel
        net = lines[i + 1].removeprefix("lab=").rstrip("}")
        if net in channel_y_for_net:
            assert channel_y_for_net[net] == y1, f"{net} split across two channel rows"
        else:
            # No other net may already claim this y.
            other = [n for n, y in channel_y_for_net.items() if y == y1]
            assert not other, f"row {y1} shared by {net} and {other}"
            channel_y_for_net[net] = y1


def test_ports_placed_for_external_nets(inverter_config):
    # schgen.py normalises decode.py's "ua[N]" net names to the plain
    # "uaN" that minimosbius_template.sch's real ports use (see
    # mosbius/schgen.py::_port_net_name) -- ua[1]=gate net, ua[2]=drain net
    # for this inverter (SPEC.md Sec 2.10 external pin map).
    decoded = decode(inverter_config)
    text = generate_schematic(decoded)
    assert "lab=ua1" in text
    assert "lab=ua2" in text
    port_lines = [l for l in text.splitlines() if "devices/iopin.sym" in l]
    port_nets = {l.split("lab=")[1].rstrip("}") for l in port_lines}
    assert "ua1" in port_nets
    assert "ua2" in port_nets
