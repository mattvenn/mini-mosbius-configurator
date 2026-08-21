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


# ---------------------------------------------------------------------------
# The OTA: the one device that straddles both bus sides, and the one whose
# tail current a schematic can set.
# ---------------------------------------------------------------------------

OTA_NETLIST = "x1 ua1 ua4 ua2 ua5 ibias VGND VAPWR mosbius_ota tail=4\n"


def test_single_ota_routes():
    # Routing one OTA used to raise KeyError('ota') out of _collect_touches:
    # side was looked up per *role*, and no side is right for a device with
    # inp/outp on A and inm/outm on B. The only OTA test before this one
    # used two OTAs, which fails in allocation and never gets that far.
    design = parse_netlist(OTA_NETLIST)
    routed = route(design)
    assert routed.device_roles == {"x1": "ota"}
    assert check(routed.config).errors == []


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
    with pytest.raises(RouteError, match="tail=5") as excinfo:
        route(parse_netlist(netlist))
    assert "2, 4, 6 or 8" in str(excinfo.value)


def test_a_width_the_cycler_cannot_express_is_explained():
    # Same wrapper, the other setting: this used to be a bare ValueError
    # traceback out of encode_cycler.
    with pytest.raises(RouteError, match="w=7") as excinfo:
        route(parse_netlist("m1 g d VGND b mosbius_nmos w=7\n"))
    assert "1, 2, 3 or 4" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Rows a terminal cannot reach: diff-pair and OTA inputs have switches to
# bus rows 1-3 only.
# ---------------------------------------------------------------------------

# The SR latch's six devices, relisted. Allocation still follows netlist
# order, so XM4 takes a diff-pair half here -- and XM4's gate is on net1,
# which spans both bus sides. That used to be KeyError: ('cfgb_dpn_inm', 6).
REORDERED_SR_LATCH = """
XM5 ua1  net1 VGND  VGND  mosbius_nmos w=1
XM6 ua2  ua3  VGND  VGND  mosbius_nmos w=1
XM1 ua3  net1 VAPWR VAPWR mosbius_pmos w=1
XM2 ua3  net1 VGND  VGND  mosbius_nmos w=1
XM3 net1 ua3  VAPWR VAPWR mosbius_pmos w=1
XM4 net1 ua3  VGND  VGND  mosbius_nmos w=1
"""


def test_diff_pair_input_on_a_two_sided_net_is_explained_not_a_keyerror():
    with pytest.raises(RouteError) as excinfo:
        route(parse_netlist(REORDERED_SR_LATCH))
    message = str(excinfo.value)
    assert "'net1' spans both bus sides" in message
    assert "XM4's gate (ndiffpair-.g)" in message   # which device, in its own words
    assert "only bus rows 1, 2 and 3" in message    # what it can reach
    assert "row 6" in message                       # what a two-sided net needs
    assert "SPEC.md Sec 2.12" in message            # why the hardware is like that


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
    from mosbius.route import _matrix_bit, _Touch

    touch = _Touch(device="XM4", role="ndiffpair-", terminal="g",
                   side="B", pin="cfgb_dpn_inm")
    assert _matrix_bit(touch, 3, "net1") is not None
    with pytest.raises(RouteError, match="cannot reach bus_B\\[6\\]"):
        _matrix_bit(touch, 6, "net1")


def test_a_diff_pair_gate_on_an_out_of_range_pin_names_the_pins_that_work():
    # ua3 is bonded to bus_A[5], which a diff-pair input has no switch to.
    # The row is a bond wire, so the only fix is a different pin -- and the
    # message works out which ones those are rather than leaving it to the
    # reader (examples/srlatch/README.md documents the same three).
    netlist = """
    XM1 ua1  net1 VAPWR VAPWR mosbius_pmos w=1
    XM2 ua1  net1 VGND  VGND  mosbius_nmos w=1
    XM3 net1 ua1  VAPWR VAPWR mosbius_pmos w=1
    XM4 net1 ua1  VGND  VGND  mosbius_nmos w=1
    XM5 ua3  net1 VGND  VGND  mosbius_nmos w=1
    XM6 ua2  ua1  VGND  VGND  mosbius_nmos w=1
    """
    with pytest.raises(RouteError) as excinfo:
        route(parse_netlist(netlist))
    message = str(excinfo.value)
    assert "XM5's gate (ndiffpair+.g) cannot reach bus_A[5]" in message
    assert "ua3 is always bus_A[5]" in message
    assert "(ua1, ua2 or ua4)" in message


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
