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

from mosbius import messages
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
mtail outn ibn bn mosbius_nsink ratio=2
mref outp ibp bp mosbius_psource ratio=1
xota inp inm outp outm ib bn bp mosbius_ota tail=4
"""
    design = parse_netlist(text)
    by_name = {d.name: d for d in design.devices}
    assert by_name["mtail"].terminals == {"out": "outn", "ibias": "ibn", "b": "bn"}
    assert by_name["mtail"].kind == "nsink"
    assert by_name["mref"].terminals == {"out": "outp", "ibias": "ibp", "b": "bp"}
    assert by_name["mref"].kind == "psource"
    ota = by_name["xota"]
    assert ota.kind == "ota"
    assert ota.terminals == {
        "inp": "inp", "inm": "inm", "outp": "outp", "outm": "outm",
        "ibias": "ib", "bn": "bn", "bp": "bp",
    }
    assert ota.properties == {"tail": 4}


def test_tail_pin_order():
    text = "T1 net1 ibias VGND mosbius_ntail tail=6\nT2 net2 ibias_p VAPWR mosbius_ptail tail=8\n"
    design = parse_netlist(text)
    by_name = {d.name: d for d in design.devices}
    assert by_name["T1"].terminals == {"d": "net1", "g": "ibias", "s": "VGND"}
    assert by_name["T1"].kind == "ntail"
    assert by_name["T2"].terminals == {"d": "net2", "g": "ibias_p", "s": "VAPWR"}
    assert by_name["T2"].kind == "ptail"
    assert by_name["T1"].properties == {"tail": 6}


def test_wrong_connection_count_raises():
    # mosbius_nmos takes 4 connections (g,d,s,b); this line only gives 3.
    with pytest.raises(NetlistError) as excinfo:
        parse_netlist("M1 a b c mosbius_nmos w=1\n")
    assert str(excinfo.value) == messages.NETLIST_PIN_COUNT_MISMATCH.format(
        name="M1", kind="nmos", n_pins=4, pin_names="g, d, s, b", n_nets=3,
    )


def test_routed_design_json_is_named_as_such():
    # `route`/`watch` read build/<name>.spice; routing's own output,
    # build/<name>.mosbius.json, is one word away in the name and lands
    # here by mistake. "no mosbius_* instances found" is true of it but
    # explains nothing.
    routed_json = '{\n  "bitstream": "00" ,\n  "device_roles": {}\n}\n'
    with pytest.raises(NetlistError) as excinfo:
        parse_netlist(routed_json)
    assert str(excinfo.value) == messages.NETLIST_ROUTED_JSON_GIVEN


def test_no_devices_raises():
    with pytest.raises(NetlistError) as excinfo:
        parse_netlist("** empty netlist, no mosbius devices\n.end\n")
    assert str(excinfo.value) == messages.NETLIST_NO_DEVICES_FOUND


def test_port_names_match_mini_mosbius_ports():
    assert PORT_NAMES == {"ibias", "ua1", "ua2", "ua3", "ua4", "ua5", "VAPWR", "VDPWR", "VGND"}


def test_x_prefixed_instance_names_parse():
    """The symbols emit `XM1 ...` rather than `M1 ...` since they gained
    `@spiceprefix`.

    The instance name is taken verbatim, prefix included -- it is only ever
    a key, never parsed for meaning.
    """
    design = parse_netlist(
        "XM1 ua1 ua2 VGND VGND mosbius_nmos w=1\n"
        "XM2 ua1 ua2 VAPWR VAPWR mosbius_pmos w=1\n"
    )
    assert [d.name for d in design.devices] == ["XM1", "XM2"]
    assert [d.kind for d in design.devices] == ["nmos", "pmos"]
    assert design.devices[0].terminals == {"g": "ua1", "d": "ua2", "s": "VGND", "b": "VGND"}


# ---------------------------------------------------------------------------
# Staleness: a netlist older than the schematic it came from.
# ---------------------------------------------------------------------------

import os

from mosbius.netlist import StaleNetlistError, check_netlist_fresh, schematic_for_netlist


def _pair(tmp_path, sch_newer):
    sch = tmp_path / "ring.sch"
    sch.write_text("v {xschem}\n")
    netlist = tmp_path / "ring.spice"
    netlist.write_text(f"** sch_path: {sch}\nXM1 a b VGND VGND mosbius_nmos w=1\n")
    # Explicit mtimes: writing both in the same test is far faster than the
    # filesystem's timestamp resolution, so relying on write order is flaky.
    os.utime(netlist, (1000, 1000))
    os.utime(sch, (2000, 2000) if sch_newer else (500, 500))
    return netlist


def test_netlist_older_than_its_schematic_is_refused(tmp_path):
    netlist = _pair(tmp_path, sch_newer=True)
    with pytest.raises(StaleNetlistError) as e:
        check_netlist_fresh(netlist)
    sch = tmp_path / "ring.sch"
    # The message has to name the fix, not just the problem (SPEC.md Sec 1.1).
    assert str(e.value) == messages.NETLIST_STALE.format(
        netlist_path=netlist, sch=sch, sch_name=sch.name,
    )


def test_netlist_newer_than_its_schematic_passes(tmp_path):
    check_netlist_fresh(_pair(tmp_path, sch_newer=False))  # must not raise


def test_unresolvable_sch_path_is_skipped_rather_than_guessed(tmp_path):
    """A netlist written in a container and read somewhere else records a
    path that does not exist here. Falsely calling a fresh netlist stale
    would be worse than not checking, so this stays quiet.
    """
    netlist = tmp_path / "orphan.spice"
    netlist.write_text("** sch_path: /nowhere/that/exists/orphan.sch\nXM1 a b VGND VGND mosbius_nmos w=1\n")
    assert schematic_for_netlist(netlist) is None
    check_netlist_fresh(netlist)  # must not raise


def test_netlist_without_a_sch_path_header_is_skipped(tmp_path):
    netlist = tmp_path / "handwritten.spice"
    netlist.write_text("XM1 a b VGND VGND mosbius_nmos w=1\n")
    assert schematic_for_netlist(netlist) is None
    check_netlist_fresh(netlist)


# An OTA netlist as xschem actually writes it: the design block, then the
# symbol bodies below it. mosbius_ota.sch builds its tail bank out of a
# mosbius_nsink and passes its own parameter through as `ratio=tail`, so a
# parser that reads the whole file matched that line and raised
# `ValueError: invalid literal for int() with base 10: 'tail'` -- every OTA
# design, from every real netlist.
OTA_NETLIST_WITH_SYMBOL_BODIES = """\
** sch_path: /work/examples/otabuf/otabuf.sch
**.subckt otabuf ibias ua1 ua2 ua3 ua4 ua5 VAPWR VDPWR VGND
*.iopin ibias
XA1 ua1 ua2 ua3 ua2 ibias VGND VAPWR mosbius_ota tail=4
**.ends

* expanding   symbol:  mosbius_ota.sym # of pins=4
.subckt mosbius_ota inp inm outp outm ibias bn bp  tail=2
XMtail net1 ibias bn mosbius_nsink ratio=tail
.ends

.subckt mosbius_nsink out ibias b  ratio=1
XM2 out ibias b b sky130_fd_pr__nfet_g5v0d10v5 L=0.5 W=10*ratio
.ends
"""


def test_symbol_bodies_are_not_part_of_the_design():
    design = parse_netlist(OTA_NETLIST_WITH_SYMBOL_BODIES)
    assert [d.name for d in design.devices] == ["XA1"]
    assert design.devices[0].kind == "ota"
    assert design.devices[0].properties == {"tail": 4}


def test_netlist_without_a_subckt_marker_is_read_whole():
    # Hand-written netlists (most of this suite) have no **.subckt line.
    design = parse_netlist("m1 ua1 ua2 VGND b mosbius_nmos w=1\n")
    assert [d.name for d in design.devices] == ["m1"]
