# SPDX-License-Identifier: Apache-2.0
"""mosbius/check.py -- SPEC.md Sec 3.1 circuit safety checker.

M1 exit criterion: a hand-built short (bus_pwr[3] + bus_pwr[6] +
bus_short[6]) is caught by E1 with the switch path printed. SPEC.md Sec 6.3
also wants a corpus of known-dangerous configs that must all be rejected
and known-good configs (every example) that must all pass cleanly -- a
false positive is as damaging as a false negative, since it teaches the
user to reach for --force.
"""

from __future__ import annotations

from mosbius.check import check
from mosbius.model import SwitchConfig

from .conftest import bit_for, setting_bit


def test_known_good_inverter_has_no_errors_or_warnings(inverter_config):
    report = check(inverter_config)
    assert report.errors == []
    assert report.warnings == []


def test_empty_config_has_no_errors():
    # All switches open is always safe -- SPEC.md Sec 2.1 (rst_n's default state).
    report = check(SwitchConfig(bits=frozenset()))
    assert report.errors == []


# -- E1: supply short --------------------------------------------------------

def test_e1_hand_built_short_bus_pwr_3_and_6_and_bus_short_6():
    # SPEC.md Sec 3.1: bus_A[6] -> VGND (cfg_bus_pwr[3]), bus_B[6] -> VAPWR
    # (cfg_bus_pwr[6]), cfg_bus_short[6] joins bus_A[6]/bus_B[6]. 3 bits,
    # the exact scenario SPEC.md Sec 1.1's example message walks through.
    bits = {
        bit_for("cfg_bus_pwr", 3),
        bit_for("cfg_bus_pwr", 6),
        bit_for("cfg_bus_short", 6),
    }
    report = check(SwitchConfig(bits=frozenset(bits)))
    e1 = [f for f in report.errors if f.code == "E1"]
    assert len(e1) == 1
    assert report.has_errors
    msg = e1[0].message
    # The switch path must actually be printed, not just "short detected".
    assert "VAPWR" in msg and "VGND" in msg
    assert "cfg_bus_pwr[6]" in msg
    assert "cfg_bus_short[6]" in msg
    assert "cfg_bus_pwr[3]" in msg
    assert "3 closed switches" in msg


def test_e1_not_triggered_by_unrelated_rail_taps():
    # Each rail tap alone, without the short joining them, is not a hazard.
    bits = {bit_for("cfg_bus_pwr", 3), bit_for("cfg_bus_pwr", 6)}
    report = check(SwitchConfig(bits=frozenset(bits)))
    assert [f for f in report.errors if f.code == "E1"] == []


# -- E2: ibias shorted to a rail ---------------------------------------------

def test_e2_not_triggered_by_default():
    # ua[0]/ibias bonds only to itself (SPEC.md Sec 2.6) -- the matrix has
    # no path onto it, so an ordinary config never trips E2. This is the
    # negative case; E2 itself is exercised directly against the graph in
    # test_e2_fires_when_ibias_and_a_rail_share_a_component below.
    report = check(SwitchConfig(bits=frozenset()))
    assert [f for f in report.errors if f.code == "E2"] == []


def test_e2_fires_when_ibias_and_a_rail_share_a_component():
    # The real hardware gives ibias no matrix path to a rail at all, so
    # exercise E2's detection logic directly: monkeypatch build_graph via a
    # config subclass isn't warranted for one test -- instead confirm the
    # checker's rail-adjacency logic by constructing the graph by hand.
    from mosbius.model import Edge

    config = SwitchConfig(bits=frozenset())
    graph = config.build_graph()
    graph["ibias"].append(Edge(neighbor="VAPWR", label="test-only edge"))
    graph["VAPWR"].append(Edge(neighbor="ibias", label="test-only edge"))

    from mosbius.check import _check_e2_ibias_short
    from mosbius.model import connected_components

    comp = connected_components(graph)
    findings = _check_e2_ibias_short(graph, comp)
    assert len(findings) == 1
    assert findings[0].code == "E2"
    assert "VAPWR" in findings[0].message


# -- E3 / E4: external pins ---------------------------------------------------

def test_e3_driven_pin_shorted_to_rail():
    # SPEC.md Sec 2.10: pinned and rail-tappable rows are disjoint, so no
    # single bus_pwr tap ever touches a pinned row directly -- reaching one
    # always takes a bus_short plus a tap on the joined row. ua[1]=bus_A[1];
    # cfg_bus_short[1] joins it to bus_B[1], which cfg_bus_pwr[4] taps to
    # VAPWR.
    bits = {bit_for("cfg_bus_short", 1), bit_for("cfg_bus_pwr", 4)}
    report = check(SwitchConfig(bits=frozenset(bits)))
    e3 = [f for f in report.errors if f.code == "E3"]
    assert len(e3) == 1
    assert "ua[1]" in e3[0].message
    assert "VAPWR" in e3[0].message


def test_e4_two_pins_shorted_together():
    # ua[1]=bus_A[1], ua[2]=bus_A[3]. Bridge the two rows through a shared
    # nmos_a.d crosspoint switch on each.
    bits = {bit_for("cfga_nfeta_d", 1), bit_for("cfga_nfeta_d", 3)}
    report = check(SwitchConfig(bits=frozenset(bits)))
    e4 = [f for f in report.errors if f.code == "E4"]
    assert len(e4) == 1
    assert "ua[1]" in e4[0].message and "ua[2]" in e4[0].message


# -- W1: shorted channel -------------------------------------------------------

def test_w1_drain_and_source_on_same_row():
    bits = {bit_for("cfga_nfeta_d", 1), bit_for("cfga_nfeta_s", 1)}
    report = check(SwitchConfig(bits=frozenset(bits)))
    w1 = [f for f in report.warnings if f.code == "W1"]
    assert len(w1) == 1
    assert "nmos_a" in w1[0].message


def test_w1_not_triggered_when_drain_and_source_differ(inverter_config):
    report = check(inverter_config)
    assert [f for f in report.warnings if f.code == "W1"] == []


# -- W2: floating crosspoint ----------------------------------------------------

def test_w2_rail_tappable_row_floats_if_the_tap_itself_is_open():
    # bus_A[2] is VGND-tappable (cfg_bus_pwr[1], SPEC.md Sec 2.7) but not
    # externally pinned. Wiring a *gate* onto it without closing the pwr tap
    # leaves both the row and the crosspoint with no DC anchor at all.
    # (A gate specifically: it is the one terminal with no channel behind
    # it, so nothing can bias it except the matrix.)
    bits = {bit_for("cfga_nfeta_g", 2)}
    report = check(SwitchConfig(bits=frozenset(bits)))
    w2 = [f for f in report.warnings if f.code == "W2"]
    assert len(w2) == 1
    assert "nmos_a.g" in w2[0].message


def test_w2_not_triggered_once_the_tap_is_also_closed():
    # Same net, but now with the VGND tap actually closed -- anchored.
    bits = {bit_for("cfga_nfeta_g", 2), bit_for("cfg_bus_pwr", 1)}
    report = check(SwitchConfig(bits=frozenset(bits)))
    assert [f for f in report.warnings if f.code == "W2"] == []


def test_w2_silent_on_a_ring_oscillator():
    """The case that motivated rewriting this check (TODO.md Sec 4).

    Every internal node of a chained design reaches a rail only through
    the transistors driving it. Before DEVICE_DC_PATHS existed this
    3-stage ring -- a real, measured, working circuit -- produced eight
    W2 warnings for its two internal nets, each telling the user to give
    an inverter output "a DC path to a rail", i.e. to break it.
    """
    config = SwitchConfig.from_bitstream(
        "0c008800c004001801000020100804000060040100000021"
    )
    assert [f for f in check(config).warnings if f.code == "W2"] == []


def test_w2_mirror_output_is_not_floating():
    # A mirror leg's source is its rail inside the block, so `out` always
    # has a DC path there -- that is what makes it a current sink rather
    # than an inert node.
    bits = {bit_for("cfga_mirn_a", 2)}
    report = check(SwitchConfig(bits=frozenset(bits)))
    assert [f for f in report.warnings if f.code == "W2"] == []


def test_w2_diff_pair_drain_depends_on_the_tail_tie():
    # The diff-pair tail has no matrix terminal (SPEC.md Sec 2.12), so the
    # half's channel leads somewhere reachable only when ctrl_dpn_source
    # ties that tail to VGND. With the bit clear the drain really is
    # unbiased and W2 should say so.
    wired = {bit_for("cfga_dpn_outp", 2)}
    floating = check(SwitchConfig(bits=frozenset(wired)))
    assert len([f for f in floating.warnings if f.code == "W2"]) == 1

    tied = check(SwitchConfig(bits=frozenset(wired | {setting_bit("ctrl_dpn_source")})))
    assert [f for f in tied.warnings if f.code == "W2"] == []


def test_w2_reports_one_finding_per_net_not_per_crosspoint():
    # Two gates on one row is one floating net, so one warning naming both
    # -- not two warnings that each say most of the same thing.
    bits = {bit_for("cfga_nfeta_g", 2), bit_for("cfga_pfeta_g", 2)}
    report = check(SwitchConfig(bits=frozenset(bits)))
    w2 = [f for f in report.warnings if f.code == "W2"]
    assert len(w2) == 1
    assert "nmos_a.g" in w2[0].message and "pmos_a.g" in w2[0].message


def test_w2_not_triggered_by_a_pinned_row(inverter_config):
    # SPEC.md Sec 2.10: pinned and rail-tappable rows are a disjoint,
    # exhaustive partition of all 12 -- a pinned row anchors via its ua[]
    # pin instead, and shouldn't need a rail tap to avoid W2.
    report = check(inverter_config)
    assert [f for f in report.warnings if f.code == "W2"] == []


# -- W3: unconnected terminal ----------------------------------------------------

def test_w3_gate_wired_drain_floating():
    bits = {bit_for("cfga_nfeta_g", 1)}
    report = check(SwitchConfig(bits=frozenset(bits)))
    w3 = [f for f in report.warnings if f.code == "W3"]
    assert len(w3) == 1
    assert "nmos_a" in w3[0].message


def test_w3_not_triggered_when_all_terminals_used(inverter_config):
    report = check(inverter_config)
    assert [f for f in report.warnings if f.code == "W3"] == []


# -- I1: sparse bus segment -------------------------------------------------------

def test_i1_unused_segment_flagged():
    report = check(SwitchConfig(bits=frozenset()))
    i1_segments = {f.message.split()[2] for f in report.findings if f.code == "I1"}
    assert "bus_A[6]" in i1_segments  # never touched by anything in an empty config


def test_i1_not_flagged_for_fully_wired_segment(inverter_config):
    report = check(inverter_config)
    i1_segments = {f.message.split()[2] for f in report.findings if f.code == "I1"}
    assert "bus_A[1]" not in i1_segments  # ua[1] bond + nmos_a.g + pmos_a.g
    assert "bus_A[3]" not in i1_segments  # ua[2] bond + nmos_a.d + pmos_a.d


def test_w2_names_the_tail_tie_bit_when_that_is_the_cause():
    # A diff-pair drain floats because its shared tail is untied, and that
    # is one bit -- so say which bit rather than only the generic advice.
    report = check(SwitchConfig(bits=frozenset({bit_for("cfga_dpn_outp", 2)})))
    w2 = [f for f in report.warnings if f.code == "W2"]
    assert len(w2) == 1
    assert "ctrl_dpn_source" in w2[0].message
