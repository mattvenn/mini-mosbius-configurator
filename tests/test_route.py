# SPDX-License-Identifier: Apache-2.0
"""mosbius/route.py -- SPEC.md Sec 3.2/3.4 automatic routing.

M3 exit criterion: the inverter and SR-latch examples each produce a
bitstream. Both are verified here two ways: check() finds no errors, and
decode() reads back the exact circuit that was routed -- the same
self-consistency technique M1/M2 used before real hardware exists.
"""

from __future__ import annotations

import pytest

from mosbius.check import check
from mosbius.decode import decode
from mosbius.netlist import NetlistError, parse_netlist
from mosbius.route import RouteError, route

INVERTER_NETLIST = """
nfeta_0 ua1 ua2 VGND net1 mosbius_nmos w=1
pfeta_1 ua1 ua2 VAPWR net2 mosbius_pmos w=1
"""

# 6T SR latch: cross-coupled inverter pair + independent set/reset pull-downs.
# Q is wired to ua2 (an SR latch you can't read is a strange latch to build).
SR_LATCH_NETLIST = """
m1 qb ua2 VGND s1 mosbius_nmos w=2
m2 ua2 qb VGND s2 mosbius_nmos w=2
m3 qb ua2 VAPWR s3 mosbius_pmos w=2
m4 ua2 qb VAPWR s4 mosbius_pmos w=2
mset ua1 ua2 VGND s5 mosbius_nmos w=2
mreset reset qb VGND s6 mosbius_nmos w=2
"""


def test_inverter_routes_with_no_check_errors():
    design = parse_netlist(INVERTER_NETLIST)
    routed = route(design)
    report = check(routed.config)
    assert report.errors == []


def test_inverter_matches_hand_built_reference(inverter_config):
    # tests/conftest.py's make_inverter_config() was hand-built directly
    # from the bit map in M1, before route.py existed. The router
    # producing the exact same bitstream for the same circuit is strong
    # end-to-end confirmation.
    design = parse_netlist(INVERTER_NETLIST)
    routed = route(design)
    assert routed.config.bits == inverter_config.bits


def test_inverter_decodes_back_to_the_same_topology():
    design = parse_netlist(INVERTER_NETLIST)
    routed = route(design)
    decoded = decode(routed.config)
    by_name = {d.name: d for d in decoded.devices}
    assert set(by_name) == {"nfeta", "pfeta"}
    assert by_name["nfeta"].terminals["g"] == by_name["pfeta"].terminals["g"]
    assert by_name["nfeta"].terminals["d"] == by_name["pfeta"].terminals["d"]
    assert by_name["nfeta"].settings["source_tied_to_VGND"] is True
    assert by_name["pfeta"].settings["source_tied_to_VAPWR"] is True


def test_sr_latch_routes_with_no_check_errors():
    design = parse_netlist(SR_LATCH_NETLIST)
    routed = route(design)
    report = check(routed.config)
    assert report.errors == []


def test_sr_latch_uses_all_six_transistors():
    design = parse_netlist(SR_LATCH_NETLIST)
    routed = route(design)
    assert set(routed.device_roles.values()) == {
        "nfeta", "nfetb", "pfeta", "pfetb", "dpn+", "dpn-",
    }


def test_sr_latch_decodes_to_cross_coupled_inverters_plus_pulldowns():
    design = parse_netlist(SR_LATCH_NETLIST)
    routed = route(design)
    decoded = decode(routed.config)
    by_name = {d.name: d for d in decoded.devices}

    # nfeta/pfeta and nfetb/pfetb form two cross-coupled inverters: each
    # pair's gate is the other pair's drain.
    qb_net = by_name["nfeta"].terminals["g"]
    assert by_name["pfeta"].terminals["g"] == qb_net
    assert by_name["nfetb"].terminals["d"] == qb_net
    assert by_name["pfetb"].terminals["d"] == qb_net
    assert by_name["nfeta"].terminals["d"] == by_name["nfetb"].terminals["g"]
    assert by_name["nfeta"].terminals["d"] == "ua[2]"  # Q is observable on ua2

    # The two set/reset pull-downs (dpn+/dpn-, used standalone with their
    # shared tail tied to VGND) each pull one side low.
    assert by_name["dpn+"].terminals["d"] == by_name["nfeta"].terminals["d"]
    assert by_name["dpn-"].terminals["d"] == qb_net
    assert by_name["dpn+"].settings["shared_source_tied_to_VGND"] is True
    assert by_name["dpn-"].settings["shared_source_tied_to_VGND"] is True


def test_too_many_independent_source_nmos_reports_doesnt_fit():
    # 3 NMOS, all wanting genuinely different (non-rail) sources -- more
    # than the 2 independent slots, and none shareable via the diff pair.
    netlist = """
    m1 g1 d1 s1 b1 mosbius_nmos w=1
    m2 g2 d2 s2 b2 mosbius_nmos w=1
    m3 g3 d3 s3 b3 mosbius_nmos w=1
    """
    design = parse_netlist(netlist)
    with pytest.raises(RouteError, match="not enough NMOS"):
        route(design)


def test_vdpwr_net_is_rejected():
    netlist = "m1 g d VDPWR b mosbius_nmos w=1\n"
    design = parse_netlist(netlist)
    with pytest.raises(RouteError, match="VDPWR"):
        route(design)


def test_two_ota_devices_reports_doesnt_fit():
    netlist = """
    x1 inp1 inm1 outp1 outm1 ib1 bn1 bp1 mosbius_ota tail=2
    x2 inp2 inm2 outp2 outm2 ib2 bn2 bp2 mosbius_ota tail=2
    """
    design = parse_netlist(netlist)
    with pytest.raises(RouteError, match="only one OTA"):
        route(design)


def test_width_property_round_trips_through_decode():
    netlist = "m1 g d VGND b mosbius_nmos w=3\n"
    design = parse_netlist(netlist)
    routed = route(design)
    decoded = decode(routed.config)
    assert decoded.devices[0].settings["width"] == 3
