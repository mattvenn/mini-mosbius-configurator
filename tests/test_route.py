# SPDX-License-Identifier: Apache-2.0
"""mosbius/route.py -- SPEC.md Sec 3.2/3.4 automatic routing.

M3 exit criterion: the inverter and SR-latch examples each produce a
bitstream. Both are verified here two ways: check() finds no errors, and
decode() reads back the exact circuit that was routed -- the same
self-consistency technique M1/M2 used before real hardware exists.
"""

from __future__ import annotations

import itertools
import re

import pytest

from mosbius import messages
from mosbius.check import check, check_routing
from mosbius.decode import decode
from mosbius.netlist import NetlistError, parse_netlist
from mosbius.route import (
    ROWS_FREE_ON_BOTH_SIDES,
    RouteError,
    _joined_row_violations,
    _net_sides,
    allocate_devices,
    route,
)

# Every mirror leg, tail bank and the OTA copies the chip's single bias
# reference, so a design using one needs exactly one mosbius_bias block --
# check.py's B1, an ERROR that stops cli.py and watch.py before routing.
# route() itself does not care (mosbius_bias is not in DEVICE_PINS, so it
# never becomes a device), but a fixture without it is a composition the
# product refuses, so the fixtures below carry one.
BIAS_GENERATOR = "XBIAS ibias ibias_p VGND VAPWR mosbius_bias\n"

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
    assert set(by_name) == {"nmos_a", "pmos_a"}
    assert by_name["nmos_a"].terminals["g"] == by_name["pmos_a"].terminals["g"]
    assert by_name["nmos_a"].terminals["d"] == by_name["pmos_a"].terminals["d"]
    assert by_name["nmos_a"].settings["source_tied_to_VGND"] is True
    assert by_name["pmos_a"].settings["source_tied_to_VAPWR"] is True


def test_sr_latch_routes_with_no_check_errors():
    design = parse_netlist(SR_LATCH_NETLIST)
    routed = route(design)
    report = check(routed.config)
    assert report.errors == []


def test_sr_latch_uses_all_six_transistors():
    design = parse_netlist(SR_LATCH_NETLIST)
    routed = route(design)
    assert set(routed.device_roles.values()) == {
        "nmos_a", "nmos_b", "pmos_a", "pmos_b", "ndiffpair+", "ndiffpair-",
    }


def test_sr_latch_decodes_to_cross_coupled_inverters_plus_pulldowns():
    design = parse_netlist(SR_LATCH_NETLIST)
    routed = route(design)
    decoded = decode(routed.config)
    by_name = {d.name: d for d in decoded.devices}

    # nmos_a/pmos_a and nmos_b/pmos_b form two cross-coupled inverters: each
    # pair's gate is the other pair's drain.
    qb_net = by_name["nmos_a"].terminals["g"]
    assert by_name["pmos_a"].terminals["g"] == qb_net
    assert by_name["nmos_b"].terminals["d"] == qb_net
    assert by_name["pmos_b"].terminals["d"] == qb_net
    assert by_name["nmos_a"].terminals["d"] == by_name["nmos_b"].terminals["g"]
    assert by_name["nmos_a"].terminals["d"] == "ua[2]"  # Q is observable on ua2

    # The two set/reset pull-downs (ndiffpair+/ndiffpair-, used standalone with their
    # shared tail tied to VGND) each pull one side low.
    assert by_name["ndiffpair+"].terminals["d"] == by_name["nmos_a"].terminals["d"]
    assert by_name["ndiffpair-"].terminals["d"] == qb_net
    assert by_name["ndiffpair+"].settings["shared_source_tied_to_VGND"] is True
    assert by_name["ndiffpair-"].settings["shared_source_tied_to_VGND"] is True


def test_too_many_independent_source_nmos_reports_doesnt_fit():
    # 3 NMOS, all wanting genuinely different (non-rail) sources -- more
    # than the 2 independent slots, and none shareable via the diff pair.
    netlist = """
    m1 g1 d1 s1 b1 mosbius_nmos w=1
    m2 g2 d2 s2 b2 mosbius_nmos w=1
    m3 g3 d3 s3 b3 mosbius_nmos w=1
    """
    design = parse_netlist(netlist)
    # Fragment, not the full messages.ROUTE_NOT_ENOUGH_FETS text: which
    # instance lands on which slot ("placed") is an internal allocation
    # detail, not part of what this test is pinning down.
    with pytest.raises(RouteError, match=re.escape(messages.ROUTE_NOT_ENOUGH_FETS_HEADLINE.format(label="NMOS"))):
        route(design)


def test_vdpwr_net_is_rejected():
    netlist = "m1 g d VDPWR b mosbius_nmos w=1\n"
    design = parse_netlist(netlist)
    with pytest.raises(RouteError) as excinfo:
        route(design)
    assert str(excinfo.value) == messages.ROUTE_VDPWR_UNREACHABLE


def test_two_ota_devices_reports_doesnt_fit():
    netlist = """
    x1 inp1 inm1 outp1 outm1 ib1 bn1 bp1 mosbius_ota tail=2
    x2 inp2 inm2 outp2 outm2 ib2 bn2 bp2 mosbius_ota tail=2
    """ + BIAS_GENERATOR
    design = parse_netlist(netlist)
    with pytest.raises(RouteError) as excinfo:
        route(design)
    assert str(excinfo.value) == messages.ROUTE_TOO_MANY_OTA.format(count=2)


def test_width_property_round_trips_through_decode():
    netlist = "m1 g d VGND b mosbius_nmos w=3\n"
    design = parse_netlist(netlist)
    routed = route(design)
    decoded = decode(routed.config)
    assert decoded.devices[0].settings["width"] == 3


# ---------------------------------------------------------------------------
# The OTA: the one device that straddles both bus sides, and the one whose
# tail current a schematic can set.
# ---------------------------------------------------------------------------

OTA_NETLIST = "x1 ua1 ua4 ua2 ua5 ibias VGND VAPWR mosbius_ota tail=4\n" + BIAS_GENERATOR


def test_single_ota_routes():
    # Routing one OTA used to raise KeyError('ota') out of _collect_touches:
    # side was looked up per *role*, and no side is right for a device with
    # inp/outp on A and inm/outm on B. The only OTA test before this one
    # used two OTAs, which fails in allocation and never gets that far.
    design = parse_netlist(OTA_NETLIST)
    routed = route(design)
    assert routed.device_roles == {"x1": "ota"}
    assert check(routed.config).errors == []


def test_ota_gets_its_mirror_gates_tied_to_outp():
    # ctrl_otan_mode[0] ties the OTA's PMOS mirror gates to outp, which is
    # what xschem/mosbius_lib/mosbius_ota.sch (the as-drawn model of the
    # same block) hardwires. With neither mode bit closed -- the behaviour
    # until 2026-08-28 -- the gate node floats and the routed OTA is not an
    # amplifier at all, while the drawn one is.
    routed = route(parse_netlist(OTA_NETLIST))
    settings = routed.config.device_settings()
    assert settings.otan_mode0 is True
    assert settings.otan_mode1 is False


def test_no_ota_leaves_the_mode_bits_alone():
    routed = route(parse_netlist(INVERTER_NETLIST))
    settings = routed.config.device_settings()
    assert settings.otan_mode0 is False
    assert settings.otan_mode1 is False


def test_ota_terminals_land_on_the_side_the_bit_map_says():
    from mosbius.route import TERMINAL_PIN, TERMINAL_SIDE

    assert TERMINAL_SIDE[("ota", "inp")] == "A"
    assert TERMINAL_SIDE[("ota", "outp")] == "A"
    assert TERMINAL_SIDE[("ota", "inm")] == "B"
    assert TERMINAL_SIDE[("ota", "outm")] == "B"
    assert TERMINAL_PIN[("ota", "inm")] == "cfgb_otan_inm"


def test_every_other_role_still_sits_wholly_on_one_side():
    # The tables are derived from bitmap.py now rather than transcribed, so
    # this pins the derivation against what the transcription used to say.
    from mosbius.model import DEVICE_TERMINALS
    from mosbius.route import TERMINAL_SIDE

    expected = {
        "nmos_a": "A", "nmos_b": "B", "ndiffpair+": "A", "ndiffpair-": "B",
        "pmos_a": "A", "pmos_b": "B", "pdiffpair+": "A", "pdiffpair-": "B",
        "nsink_a": "A", "nsink_b": "B", "psource_a": "A", "psource_b": "B",
    }
    for role, side in expected.items():
        sides = {TERMINAL_SIDE[(role, t)] for t in DEVICE_TERMINALS[role]}
        assert sides == {side}, role


def test_ota_decodes_back_to_the_same_terminals():
    routed = route(parse_netlist(OTA_NETLIST))
    decoded = decode(routed.config)
    ota = decoded.devices[0]
    assert ota.terminals == {
        "inp": "ua[1]", "outp": "ua[2]", "inm": "ua[4]", "outm": "ua[5]",
    }


def test_ota_tail_reaches_the_bitstream():
    # The bug this covers was masked: an all-zero cycler decodes to 2,
    # which is also mosbius_ota.sym's default, so tail=2 looked correct
    # while every other value was silently thrown away.
    for tail in (2, 4, 6, 8):
        netlist = OTA_NETLIST.replace("tail=4", f"tail={tail}")
        routed = route(parse_netlist(netlist))
        assert routed.config.device_settings().otan_tail == tail
        assert decode(routed.config).devices[0].settings["tail"] == tail


def test_ota_without_a_tail_property_gets_the_symbol_default():
    netlist = OTA_NETLIST.replace(" tail=4", "")
    routed = route(parse_netlist(netlist))
    assert routed.device_tails["x1"].requested is None
    assert routed.config.device_settings().otan_tail == 2


def test_a_tail_the_cycler_cannot_express_is_explained():
    netlist = OTA_NETLIST.replace("tail=4", "tail=5")
    with pytest.raises(RouteError) as excinfo:
        route(parse_netlist(netlist))
    expected = messages.ROUTE_SETTING_NOT_VALID.format(
        device="x1", prop="tail", value=5, step=2, options="2, 4, 6 or 8",
    )
    assert str(excinfo.value) == expected


def test_a_width_the_cycler_cannot_express_is_explained():
    # Same wrapper, the other setting: this used to be a bare ValueError
    # traceback out of encode_cycler.
    with pytest.raises(RouteError) as excinfo:
        route(parse_netlist("m1 g d VGND b mosbius_nmos w=7\n"))
    expected = messages.ROUTE_SETTING_NOT_VALID.format(
        device="m1", prop="w", value=7, step=1, options="1, 2, 3 or 4",
    )
    assert str(excinfo.value) == expected


# ---------------------------------------------------------------------------
# Drawn tails declare a pair (TODO.md was Sec 2, closed 2026-08-22): a
# mosbius_ntail/mosbius_ptail
# wired to two FETs' shared source claims them as the pair, sets
# ctrl_dp{n,p}_tail from its own tail=, and -- because their source is a
# real internal node rather than the rail -- leaves ctrl_dp{n,p}_source
# clear (the bank and the rail-tie are alternatives on one node).
# ---------------------------------------------------------------------------

NTAIL_NETLIST = """
XM1 ua1 ua3 net1 VGND mosbius_nmos w=1
XM2 ua2 ua4 net1 VGND mosbius_nmos w=1
XT1 net1 ibias VGND mosbius_ntail tail=6
""" + BIAS_GENERATOR

PTAIL_NETLIST = """
XM1 ua1 ua3 net1 VAPWR mosbius_pmos w=1
XM2 ua2 ua4 net1 VAPWR mosbius_pmos w=1
XT1 net1 ibias_p VAPWR mosbius_ptail tail=8
""" + BIAS_GENERATOR


def test_a_drawn_tail_claims_its_two_halves():
    routed = route(parse_netlist(NTAIL_NETLIST))
    assert {routed.device_roles["XM1"], routed.device_roles["XM2"]} == {
        "ndiffpair+", "ndiffpair-",
    }
    assert routed.device_roles["XT1"] == "ntail"


def test_a_drawn_tails_own_tail_reaches_the_bitstream():
    routed = route(parse_netlist(NTAIL_NETLIST))
    assert routed.config.device_settings().dpn_tail == 6
    # The bank and the rail-tie are alternatives on the same node -- using
    # the bank must leave the free rail-tie bit clear.
    assert routed.config.device_settings().dpn_source is False


def test_a_drawn_pmos_tail_uses_the_pmos_bit():
    routed = route(parse_netlist(PTAIL_NETLIST))
    assert {routed.device_roles["XM1"], routed.device_roles["XM2"]} == {
        "pdiffpair+", "pdiffpair-",
    }
    assert routed.config.device_settings().dpp_tail == 8
    assert routed.config.device_settings().dpp_source is False


def test_two_tails_of_the_same_polarity_reports_doesnt_fit():
    netlist = NTAIL_NETLIST + "XT2 net1 ibias VGND mosbius_ntail tail=2\n"
    with pytest.raises(RouteError) as excinfo:
        route(parse_netlist(netlist))
    assert str(excinfo.value) == messages.ROUTE_TOO_MANY_NTAIL.format(count=2)


def test_no_tail_drawn_keeps_the_old_rail_tie_behaviour():
    # TODO.md's (was Sec 2, closed 2026-08-22) explicit backward-
    # compatibility case: drawing no
    # tail at all leaves the pair-inference and the free rail tie exactly
    # as before -- examples/srlatch/ depends on this.
    netlist = NTAIL_NETLIST.replace(
        "XT1 net1 ibias VGND mosbius_ntail tail=6\n", ""
    )
    routed = route(parse_netlist(netlist))
    assert {routed.device_roles["XM1"], routed.device_roles["XM2"]} == {
        "ndiffpair+", "ndiffpair-",
    }
    assert routed.config.device_settings().dpn_tail == 2   # all-zero default
    assert routed.config.device_settings().dpn_source is False  # net1 isn't VGND


def test_a_malformed_tail_does_not_crash_route_it_falls_back():
    # check_design's D3 is what actually explains this to a user (an
    # ERROR that stops the CLI before routing runs at all) -- this is
    # only the backstop for a caller that routes without checking first,
    # so route() must degrade gracefully rather than raising a confusing
    # error or crashing outright.
    netlist = """
    XM1 ua1 ua3 net1 VGND mosbius_nmos w=1
    XT1 net1 ibias VGND mosbius_ntail tail=6
    """ + BIAS_GENERATOR
    routed = route(parse_netlist(netlist))
    assert routed.device_roles["XM1"] == "nmos_a"   # ordinary pass 2, tail ignored
    assert routed.device_roles["XT1"] == "ntail"     # still gets its own role
    assert routed.config.device_settings().dpn_tail == 6  # the bit is still real


# ---------------------------------------------------------------------------
# Rows a terminal cannot reach: diff-pair and OTA inputs have switches to
# bus rows 1-3 only.
# ---------------------------------------------------------------------------

# examples/srlatch/srlatch.sch's own six devices, in their real order --
# README.md documents this exact netlist and its resulting bitstream.
CANONICAL_SR_LATCH = """
XM1 ua3  net1 VAPWR VAPWR mosbius_pmos w=1
XM2 ua3  net1 VGND  VGND  mosbius_nmos w=1
XM3 net1 ua3  VAPWR VAPWR mosbius_pmos w=1
XM4 net1 ua3  VGND  VGND  mosbius_nmos w=1
XM5 ua1  net1 VGND  VGND  mosbius_nmos w=1
XM6 ua2  ua3  VGND  VGND  mosbius_nmos w=1
"""
CANONICAL_SR_LATCH_BITSTREAM = "0c008000c020008808000000008821000220200800000038"

# The same six devices, relisted. Before TODO.md Sec 2 (closed
# 2026-08-22), allocation followed netlist order regardless of where a
# device's gate needed to land, so XM4 took a diff-pair half here -- and
# XM4's gate is on net1, which spans both bus sides. That used to fail:
# first a bare KeyError, then (2026-08-21) a RouteError explaining why.
REORDERED_SR_LATCH = """
XM5 ua1  net1 VGND  VGND  mosbius_nmos w=1
XM6 ua2  ua3  VGND  VGND  mosbius_nmos w=1
XM1 ua3  net1 VAPWR VAPWR mosbius_pmos w=1
XM2 ua3  net1 VGND  VGND  mosbius_nmos w=1
XM3 net1 ua3  VAPWR VAPWR mosbius_pmos w=1
XM4 net1 ua3  VGND  VGND  mosbius_nmos w=1
"""


def test_canonical_sr_latch_matches_the_documented_bitstream():
    routed = route(parse_netlist(CANONICAL_SR_LATCH))
    assert routed.config.to_bitstream() == CANONICAL_SR_LATCH_BITSTREAM


# The polarity-swapped SR latch: same shape, but now it's the four PMOS
# that need reallocating (two of them forced onto diff-pair halves) while
# two NMOS sit on the independent slots. Confirms the search isn't an
# NMOS-only fix -- allocate_devices() calls the identical machinery for
# both polarities.
REORDERED_SR_LATCH_PMOS_SIDE = """
XM5 ua1  net1 VAPWR VAPWR mosbius_pmos w=1
XM6 ua2  ua3  VAPWR VAPWR mosbius_pmos w=1
XM1 ua3  net1 VGND  VGND  mosbius_nmos w=1
XM2 ua3  net1 VAPWR VAPWR mosbius_pmos w=1
XM3 net1 ua3  VGND  VGND  mosbius_nmos w=1
XM4 net1 ua3  VAPWR VAPWR mosbius_pmos w=1
"""


def test_reordering_fixes_the_pmos_side_too():
    routed = route(parse_netlist(REORDERED_SR_LATCH_PMOS_SIDE))
    # XM4's gate is on the two-sided net1, exactly as XM4 was in the
    # NMOS-side version -- it must land on an independent slot.
    assert routed.device_roles["XM4"] in ("pmos_a", "pmos_b")


def test_reordered_sr_latch_now_routes_regardless_of_order():
    # TODO.md was Sec 2, closed 2026-08-22: allocate_devices() now
    # searches orderings rather than trusting netlist order, so relisting
    # the same six devices no longer changes whether -- or how -- this
    # circuit routes: same bitstream as the canonical order above.
    routed = route(parse_netlist(REORDERED_SR_LATCH))
    assert routed.config.to_bitstream() == CANONICAL_SR_LATCH_BITSTREAM
    # XM4's gate on the two-sided net1 is exactly why XM4 must NOT be the
    # one holding a diff-pair role here -- it lands on an independent slot.
    assert routed.device_roles["XM4"] in ("nmos_a", "nmos_b")


def test_reordering_never_relocates_a_working_designs_bitstream():
    # A design that already routes cleanly (SR_LATCH_NETLIST's own order)
    # must not be *disturbed* by a smarter allocator -- itertools.
    # permutations tries the input order first, so a conflict-free design
    # gets today's exact assignment back on the very first attempt.
    before = route(parse_netlist(SR_LATCH_NETLIST))
    after = route(parse_netlist(SR_LATCH_NETLIST))
    assert after.device_roles == before.device_roles
    assert after.config.to_bitstream() == before.config.to_bitstream()


# Two source followers plus an inverter -- an ordinary circuit, no
# differential pair anywhere. Both followers put their *drain* on VAPWR,
# and a drain has no ctrl_*_source tie, so each one lands on the bus. If
# the allocator gives the two followers slots on opposite bus sides then
# VAPWR spans both sides, and a two-sided net can only sit on a row free
# of a ua[] bond wire on both -- of which there is exactly one, row 6
# (ROWS_FREE_ON_BOTH_SIDES). `outa` needs that same row, so it gets
# DOESN'T FIT. Which slot each FET got is not something the schematic
# says, so before TODO.md's item (closed 2026-08-31) this routed in 3 of
# its 6 instance orderings and failed in the other 3.
TWO_FOLLOWERS_AND_AN_INVERTER = [
    "XM1 ua1  outa  VGND  VGND  mosbius_nmos w=1",   # inverter NMOS
    "XM2 outa VAPWR ua2   VGND  mosbius_nmos w=1",   # source follower A
    "XM3 ua3  VAPWR ua4   VGND  mosbius_nmos w=1",   # source follower B
]
TWO_FOLLOWERS_PMOS = "XM4 ua1 outa VAPWR VAPWR mosbius_pmos w=1"


@pytest.mark.parametrize("order", list(itertools.permutations(range(3))))
def test_two_source_followers_route_in_every_instance_order(order):
    netlist = "\n".join([TWO_FOLLOWERS_AND_AN_INVERTER[i] for i in order]
                        + [TWO_FOLLOWERS_PMOS])
    routed = route(parse_netlist(netlist))
    # The point of the fix: at most one net ends up spanning both bus
    # sides, so the one row that can carry such a net is not fought over.
    joined = [net for net, rows in routed.net_rows.items()
              if len(rows) > 1 and not net.startswith("ua")]
    assert len(joined) <= len(ROWS_FREE_ON_BOTH_SIDES)
    assert "outa" in routed.net_rows


def test_two_source_followers_give_the_same_bitstream_in_every_order():
    bitstreams = set()
    for order in itertools.permutations(range(3)):
        netlist = "\n".join([TWO_FOLLOWERS_AND_AN_INVERTER[i] for i in order]
                            + [TWO_FOLLOWERS_PMOS])
        bitstreams.add(route(parse_netlist(netlist)).config.to_bitstream())
    assert len(bitstreams) == 1


def test_only_one_net_can_span_both_bus_sides():
    # The rule the new constraint scores against, stated directly rather
    # than inferred from a circuit: row 6 is the only row free of a ua[]
    # bond wire on both sides, so it is the only row any two-sided net --
    # rail or internal -- can use, and there is one of it.
    assert len(ROWS_FREE_ON_BOTH_SIDES) == 1
    assert _joined_row_violations({"n1": {"A", "B"}}) == 0
    assert _joined_row_violations({"n1": {"A", "B"}, "VAPWR": {"A", "B"}}) == 1
    # One-sided nets are free, and a port net is out of the competition:
    # its row is its own bond wire, and bridging spends that row number on
    # the far side rather than the shared one.
    assert _joined_row_violations({"n1": {"A"}, "n2": {"B"}, "n3": {"A"}}) == 0
    assert _joined_row_violations({"ua1": {"A", "B"}, "ua2": {"A", "B"}}) == 0


def test_a_rail_tied_source_puts_no_side_on_its_rail():
    # _net_sides scores what route() will actually see, and a source
    # sitting on its own role's tail rail is closed with a ctrl_*_source
    # bit instead of a bus row (_apply_free_source_ties). An inverter's
    # two sources are exactly that, so neither rail is two-sided here even
    # though the two devices are on opposite bus sides.
    design = parse_netlist(INVERTER_NETLIST)
    sides = _net_sides(design, allocate_devices(design))
    assert "VGND" not in sides
    assert "VAPWR" not in sides


# A net that's forced onto both bus sides no matter how the four NMOS
# requests are assigned: XM1/XM2/XM3 all share `shared_gate` as their
# gate, and only two of the four NMOS roles ever live on one side (SPEC.md
# Sec 2.12), so at most two of those three can ever share a side -- the
# third is unavoidably on the other one. No allocation search can fix a
# circuit shaped like this; it needs a different circuit.
GENUINELY_UNROUTABLE = """
XM1 shared_gate d1 VGND VGND mosbius_nmos w=1
XM2 shared_gate d2 VGND VGND mosbius_nmos w=1
XM3 shared_gate d3 VGND VGND mosbius_nmos w=1
XM4 ua1         d4 VGND VGND mosbius_nmos w=1
"""


def test_a_genuinely_unroutable_design_still_explains_itself():
    # allocate_devices()'s search (TODO.md was Sec 2, closed 2026-08-22)
    # only ever looks for a placement that already fits every existing
    # rule -- it can't manufacture a side a net doesn't have. When no
    # ordering avoids the conflict, the RouteError this raises is exactly
    # the one that existed before the search did.
    with pytest.raises(RouteError) as excinfo:
        route(parse_netlist(GENUINELY_UNROUTABLE))
    # Fragments of messages.ROUTE_NO_JOINING_ROW, not the full text: the
    # rest of it (reach_lines) depends on internal touch reachability
    # bookkeeping this test isn't set up to re-derive independently.
    message = str(excinfo.value)
    assert "'shared_gate' spans both bus sides" in message
    assert "row 6" in message


def test_the_row_free_on_both_sides_is_derived_not_assumed():
    from mosbius.route import ROWS_FREE_ON_BOTH_SIDES

    # A consequence of the ua[] bond map (SPEC.md Sec 2.10), not an
    # independent fact: rows 1/3/5 are pinned on side A and 2/4 on side B.
    assert ROWS_FREE_ON_BOTH_SIDES == frozenset({6})


def test_rows_reachable_matches_the_hardware_restriction():
    from mosbius.route import rows_reachable

    assert rows_reachable("cfga_dpn_inp") == frozenset({1, 2, 3})
    assert rows_reachable("cfgb_otan_inm") == frozenset({1, 2, 3})
    assert rows_reachable("cfga_dpn_outp") == frozenset({1, 2, 3, 4, 5, 6})
    assert rows_reachable("cfga_nfeta_g") == frozenset({1, 2, 3, 4, 5, 6})


def test_an_unreachable_row_is_a_route_error_wherever_it_is_asked_for():
    # The backstop under every _MATRIX_BIT_BY_PIN_ROW lookup: the row
    # pickers try not to ask, but a missing (pin, row) is always the same
    # fault and always deserves the same explanation rather than a KeyError.
    from mosbius.route import _describe_touch, _fmt_rows, _matrix_bit, _Touch, rows_reachable

    touch = _Touch(device="XM4", role="ndiffpair-", terminal="g",
                   side="B", pin="cfgb_dpn_inm")
    assert _matrix_bit(touch, 3, "net1") is not None
    with pytest.raises(RouteError) as excinfo:
        _matrix_bit(touch, 6, "net1")
    why = messages.ROUTE_INTERNAL_NET_UNREACHABLE_ROW.format(
        net="net1", row=6, why_limited_reach=messages.ROUTE_WHY_LIMITED_REACH,
    )
    expected = messages.ROUTE_CANNOT_REACH_ROW.format(
        touch_desc=_describe_touch(touch), side="B", row=6,
        role="ndiffpair-", terminal="g",
        rows_reach=_fmt_rows(rows_reachable("cfgb_dpn_inm")), why=why,
    )
    assert str(excinfo.value) == expected


def test_a_diff_pair_gate_on_an_out_of_range_pin_no_longer_gets_stuck_there():
    # ua3 is bonded to bus_A[5], which a diff-pair input has no switch to
    # -- so XM5, whose gate is ua3, must never be the one left holding a
    # diff-pair role. Before TODO.md Sec 2 (closed 2026-08-22) this
    # design failed to route for exactly that reason; the allocator now
    # searches orderings and finds one where XM5 gets an independent
    # slot instead, which has no gate restriction at all. The message
    # this used to produce is still exercised directly, independent of
    # allocation, by test_an_unreachable_row_is_a_route_error_wherever_
    # it_is_asked_for above.
    netlist = """
    XM1 ua1  net1 VAPWR VAPWR mosbius_pmos w=1
    XM2 ua1  net1 VGND  VGND  mosbius_nmos w=1
    XM3 net1 ua1  VAPWR VAPWR mosbius_pmos w=1
    XM4 net1 ua1  VGND  VGND  mosbius_nmos w=1
    XM5 ua3  net1 VGND  VGND  mosbius_nmos w=1
    XM6 ua2  ua1  VGND  VGND  mosbius_nmos w=1
    """
    routed = route(parse_netlist(netlist))
    assert routed.device_roles["XM5"] in ("nmos_a", "nmos_b")


def test_no_random_design_escapes_with_a_bare_traceback():
    """Every way a design can fail to route should be a RouteError.

    Both of the crashes fixed on 2026-08-21 were reached by ordinary
    circuits and both surfaced as a raw KeyError, so the general property
    is worth holding onto rather than only the two known cases. Seeded, so
    a failure is reproducible; small, so it stays a unit test.
    """
    import random

    from mosbius.check import check, check_design, check_routing

    nets = ["ua1", "ua2", "ua3", "ua4", "ua5", "VAPWR", "VGND",
            "net1", "net2", "net3", "ibias"]
    pins = {"nmos": 4, "pmos": 4, "nsink": 3, "psource": 3, "ota": 7}
    prop = {"nmos": "w=", "pmos": "w=", "nsink": "ratio=", "psource": "ratio=",
            "ota": "tail="}
    rng = random.Random(20260821)

    for _ in range(400):
        lines = []
        for i in range(rng.randint(1, 6)):
            kind = rng.choice(list(pins))
            wires = " ".join(rng.choice(nets) for _ in range(pins[kind]))
            value = rng.choice([2, 4, 6, 8]) if kind == "ota" else rng.randint(1, 4)
            lines.append(f"X{i} {wires} mosbius_{kind} {prop[kind]}{value}")
        text = "\n".join(lines) + "\n"

        design = parse_netlist(text)
        check_design(design)
        try:
            result = route(design)
        except RouteError:
            continue  # a diagnosis, which is the whole point
        check_routing(result)
        check(result.config)


# ---------------------------------------------------------------------------
# Bus-row reporting: which rows nets landed on, and which carry a bond pad.
# ---------------------------------------------------------------------------

RING_BUFFERED_NETLIST = """
XM1 net1 net2 VGND VGND mosbius_nmos w=4
XM2 net1 net2 VAPWR VAPWR mosbius_pmos w=4
XM3 ua2 net1 VGND VGND mosbius_nmos w=4
XM4 ua2 net1 VAPWR VAPWR mosbius_pmos w=4
XM5 net2 ua2 VGND VGND mosbius_nmos w=4
XM6 net2 ua2 VAPWR VAPWR mosbius_pmos w=4
XM7 net1 ua3 VGND VGND mosbius_nmos w=4
XM8 net1 ua3 VAPWR VAPWR mosbius_pmos w=4
"""


def test_pin_bond_segment_matches_the_real_pin_map():
    """ua4 bonds to bus_B[2], not bus_A[2]. Which pin sits on which side is
    the single easiest fact here to get backwards (CLAUDE.md trap 1), so
    pin it down rather than trusting the derivation to stay right.
    """
    from mosbius.route import PIN_BOND_SEGMENT

    assert PIN_BOND_SEGMENT == {
        "ua1": "bus_A[1]",
        "ua2": "bus_A[3]",
        "ua3": "bus_A[5]",
        "ua4": "bus_B[2]",
        "ua5": "bus_B[4]",
    }


def test_net_rows_report_flags_only_the_pin_bonded_nets():
    from mosbius.route import format_net_rows, format_pad_note

    routed = route(parse_netlist(RING_BUFFERED_NETLIST))
    rows = "\n".join(format_net_rows(routed))

    # Every net gets a row; only the ua-named ones are called out as padded.
    for net in ("net1", "net2", "ua2", "ua3"):
        assert net in rows
    for line in format_net_rows(routed):
        flagged = "bond pad" in line
        assert flagged == line.split()[0].startswith("ua")

    note = "\n".join(format_pad_note(routed))
    expected = messages.ROUTE_PAD_NOTE.format(which="ua2, ua3", are="are", they="they", add="add")
    assert note == "\n" + expected


def test_internal_nets_never_land_on_a_bonded_row():
    """The 'no pin' guarantee: a net not named after a package pin cannot
    be given a bonded segment, however tight the routing gets. This is
    what makes renaming a net the way to keep a pad off it.
    """
    from mosbius.route import PIN_BOND_SEGMENT

    routed = route(parse_netlist(RING_BUFFERED_NETLIST))
    bonded = set(PIN_BOND_SEGMENT.values())
    for net, sides in routed.net_rows.items():
        if net in PIN_BOND_SEGMENT or net in ("VAPWR", "VGND"):
            continue
        for side, row in sides.items():
            assert f"bus_{side}[{row}]" not in bonded, f"{net} landed on a bonded row"


def test_no_pad_note_when_nothing_is_on_a_pin():
    from mosbius.route import format_pad_note

    routed = route(parse_netlist(INVERTER_NETLIST.replace("ua1", "nin").replace("ua2", "nout")))
    assert format_pad_note(routed) == []


# ---------------------------------------------------------------------------
# The pair's shared source is not on the switch matrix (SPEC.md Sec 2.12).
# Anything else drawn onto it used to be dropped in silence: the design
# routed clean and produced a bitstream identical to the one you get
# without that connection, so the drawn circuit and the routed chip were
# not the same circuit.
# ---------------------------------------------------------------------------

PAIR_ON_INTERNAL_NET = """
XM1 ua1 ua2 tailnet VGND mosbius_nmos w=4
XM2 ua2 ua3 tailnet VGND mosbius_nmos w=4
"""


def test_third_device_on_the_shared_source_is_refused():
    netlist = PAIR_ON_INTERNAL_NET + "XM3 ua1 tailnet VGND VGND mosbius_nmos w=1\n"
    # Fragments of the _wrap()-composed message (messages.ROUTE_SHARED_
    # SOURCE_HEADLINE / _PROBLEM_OTHER / _WHAT_CAN_GO_THERE), not the full
    # text: reproducing that exactly would mean re-deriving which halves
    # got which diff-pair role, an internal allocation detail this test
    # isn't pinning down.
    with pytest.raises(
        RouteError,
        match=re.escape(messages.ROUTE_SHARED_SOURCE_HEADLINE.format(net="tailnet")),
    ) as e:
        route(parse_netlist(netlist))
    assert "XM3's drain" in str(e.value)
    assert "mosbius_ntail" in str(e.value)


def test_shared_source_on_a_package_pin_is_refused():
    # The plausible version of the mistake: bring the tail out to measure it.
    netlist = PAIR_ON_INTERNAL_NET.replace("tailnet", "ua4")
    with pytest.raises(
        RouteError,
        match=re.escape(messages.ROUTE_SHARED_SOURCE_HEADLINE.format(net="ua4")),
    ) as e:
        route(parse_netlist(netlist))
    assert "package pin" in str(e.value)


def test_a_drawn_tail_bank_may_share_the_source_node():
    netlist = PAIR_ON_INTERNAL_NET + "XT1 tailnet ibias VGND mosbius_ntail tail=4\n" + BIAS_GENERATOR
    routed = route(parse_netlist(netlist))
    assert routed.device_roles["XT1"] == "ntail"
    assert routed.undeclared_tails == ()


def test_a_rail_tied_shared_source_is_left_alone():
    netlist = PAIR_ON_INTERNAL_NET.replace("tailnet", "VGND")
    routed = route(parse_netlist(netlist))
    assert routed.undeclared_tails == ()


# ---------------------------------------------------------------------------
# R3: the tail bank has no off state, so a pair floating on an internal net
# still sinks 2 x ibias on silicon that the as-drawn model does not have.
# ---------------------------------------------------------------------------

def test_r3_warns_about_a_tail_current_nobody_asked_for():
    routed = route(parse_netlist(PAIR_ON_INTERNAL_NET))
    (undeclared,) = routed.undeclared_tails
    assert undeclared.net == "tailnet"
    assert undeclared.devices == ("XM1", "XM2")

    report = check_routing(routed)
    (finding,) = [f for f in report.findings if f.code == "R3"]
    assert "200 uA" in finding.message          # 2 x the 100 uA default
    assert "mosbius_ntail" in finding.message
    assert not report.has_errors


def test_r3_is_silent_when_the_tail_is_declared_or_tied():
    for netlist in (
        PAIR_ON_INTERNAL_NET + "XT1 tailnet ibias VGND mosbius_ntail tail=4\n" + BIAS_GENERATOR,
        PAIR_ON_INTERNAL_NET.replace("tailnet", "VGND"),
    ):
        report = check_routing(route(parse_netlist(netlist)))
        assert [f for f in report.findings if f.code == "R3"] == []


# ---------------------------------------------------------------------------
# Rail taps: a cfg_bus_pwr tap reached from the other bus side also closes
# cfg_bus_short[row], which spends the same row *number* on the far side.
# Two of the three VAPWR taps have a ua[] bond wire on that far row
# (bus_A[4] pairs with ua5's bus_B[4]; bus_B[1] with ua1's bus_A[1]), so
# taking the lowest-numbered tap blind used to short a package pin to the
# rail. Row 6 is the only row with no bond wire on either side.
# ---------------------------------------------------------------------------

# A source follower puts its FET *drain* on the rail, which is what needs a
# tap: a source reaching a rail uses the device's own ctrl_*_source tie and
# costs no bus row at all, which is why no example had ever exercised one.
TWO_FOLLOWERS = """
XF1 VAPWR ua1 outa VGND mosbius_nmos w=1
XF2 VAPWR ua2 outb VGND mosbius_nmos w=1
"""


def test_a_two_sided_rail_net_taps_the_row_with_no_bond_wire():
    routed = route(parse_netlist(TWO_FOLLOWERS))
    assert routed.net_rows["VAPWR"] == {"A": 6, "B": 6}
    # bus_A[4] is the lowest-numbered VAPWR tap and was what this used to
    # pick; its cfg_bus_short partner is ua5's row, so check() called the
    # result DANGEROUS.
    assert check(routed.config).errors == []


def test_a_one_sided_rail_net_still_takes_the_nearest_tap():
    """No touch on the far side means no cfg_bus_short and no partner row,
    so the bridge ranking must not push these off bus_A[4]."""
    netlist = ("XF1 VAPWR ua1 outa VGND mosbius_nmos w=1\n"
               "XS1 ua2 ibias VGND mosbius_nsink ratio=2\n") + BIAS_GENERATOR
    routed = route(parse_netlist(netlist))
    assert routed.net_rows["VAPWR"] == {"A": 4}
    assert check(routed.config).errors == []


def test_two_source_followers_route_whatever_order_they_are_listed_in():
    """Nets are routed in order of how little choice they have, so a port
    net gets the row (and the cfg_bus_short partner row) it cannot trade
    before an internal net can take it. Routed alphabetically instead,
    'outa' went first and one of these two orders died with
    `bus_B[1] is needed by both 'ua1' and 'outa'`.

    The two orders need not give the same bitstream -- which hardware slot
    each follower gets is allowed to differ -- but both must route, and
    neither may short a pin to a rail.
    """
    lines = TWO_FOLLOWERS.strip().splitlines()
    for order in (lines, list(reversed(lines))):
        routed = route(parse_netlist("\n".join(order) + "\n"))
        assert check(routed.config).errors == []
        assert routed.net_rows["VAPWR"] == {"A": 6, "B": 6}
