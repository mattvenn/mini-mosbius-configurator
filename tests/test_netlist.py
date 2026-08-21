# SPDX-License-Identifier: Apache-2.0
"""mosbius/netlist.py -- parsing a design's xschem/SPICE netlist into a
MosbiusDesign (SPEC.md Sec 3 architecture diagram).

Cross-checked end-to-end (outside this suite, needs the EDA container):
decode() an inverter, generate_schematic() it, netlist it through xschem,
and parse_netlist() the result -- it reproduces the exact same
nmos_a.g=ua1/d=ua2/s=VGND, pmos_a mirrored to VAPWR topology. These tests
cover parse_netlist() in isolation against hand-written netlist text.
"""

from __future__ import annotations

import pytest

from mosbius.netlist import DeviceRequest, NetlistError, PORT_NAMES, parse_netlist


INVERTER_NETLIST = """\
** sch_path: /work/inverter.sch
**.subckt inverter ua2 ua1 VGND VAPWR
*.iopin ua2
*.iopin ua1
*.iopin VGND
*.iopin VAPWR
nfeta_0 ua1 ua2 VGND net1 mosbius_nmos w=1
pfeta_1 ua1 ua2 VAPWR net2 mosbius_pmos w=1
**.ends
"""


def test_parses_both_devices():
    design = parse_netlist(INVERTER_NETLIST)
    assert len(design.devices) == 2
    names = {d.name for d in design.devices}
    assert names == {"nfeta_0", "pfeta_1"}


def test_terminal_mapping_matches_pin_order():
    design = parse_netlist(INVERTER_NETLIST)
    nmos_a = next(d for d in design.devices if d.name == "nfeta_0")
    assert nmos_a.kind == "nmos"
    assert nmos_a.terminals == {"g": "ua1", "d": "ua2", "s": "VGND", "b": "net1"}
    assert nmos_a.properties == {"w": 1}


def test_port_nets_detected():
    design = parse_netlist(INVERTER_NETLIST)
    assert design.port_nets() == {"ua1", "ua2", "VGND", "VAPWR"}


def test_nets_includes_internal_nets_too():
    design = parse_netlist(INVERTER_NETLIST)
    assert "net1" in design.nets()
    assert "net2" in design.nets()


def test_ignores_comment_and_directive_lines():
    # Lines starting with * or . (comments, .subckt/.ends/.iopin) must not
    # be mistaken for device instances.
    design = parse_netlist(INVERTER_NETLIST)
    assert len(design.devices) == 2


def test_mirror_and_ota_pin_orders():
    text = """\
mtail ibn outn bn mosbius_nsink ratio=2
mref ibp outp bp mosbius_psource ratio=1
xota inp inm outp outm ib bn bp mosbius_ota tail=4
"""
    design = parse_netlist(text)
    by_name = {d.name: d for d in design.devices}
    assert by_name["mtail"].terminals == {"ibias": "ibn", "out": "outn", "b": "bn"}
    assert by_name["mtail"].kind == "nsink"
    assert by_name["mref"].terminals == {"ibias": "ibp", "out": "outp", "b": "bp"}
    assert by_name["mref"].kind == "psource"
    ota = by_name["xota"]
    assert ota.kind == "ota"
    assert ota.terminals == {
        "inp": "inp", "inm": "inm", "outp": "outp", "outm": "outm",
        "ibias": "ib", "bn": "bn", "bp": "bp",
    }
    assert ota.properties == {"tail": 4}


def test_wrong_connection_count_raises():
    # mosbius_nmos takes 4 connections (g,d,s,b); this line only gives 3.
    with pytest.raises(NetlistError, match="4 connections"):
        parse_netlist("M1 a b c mosbius_nmos w=1\n")


def test_no_devices_raises():
    with pytest.raises(NetlistError, match="no mosbius_"):
        parse_netlist("** empty netlist, no mosbius devices\n.end\n")


def test_port_names_match_minimosbius_template_ports():
    assert PORT_NAMES == {"ibias", "ua1", "ua2", "ua3", "ua4", "ua5", "VAPWR", "VDPWR", "VGND"}
