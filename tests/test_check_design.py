# SPDX-License-Identifier: Apache-2.0
"""mosbius/check.py -- check_design(), the netlist-level checks (D1-D4).

These run before routing, on a MosbiusDesign rather than a SwitchConfig.
D1 exists because of a real misdiagnosis: shorting the two rails in xschem
makes xschem merge them into one net, so the short is *gone* from the
netlist by the time the tool sees it and the only symptom left is the
router running out of transistors. See the D1 docstring in check.py.
"""

from __future__ import annotations

from pathlib import Path

from mosbius.check import check_design
from mosbius.cli import main
from mosbius.netlist import parse_netlist


def design(*lines: str):
    return parse_netlist("\n".join(lines) + "\n")


# A healthy 3-stage ring: every source on its own body's rail. The two
# leftover FETs land on diff-pair halves, which only works because their
# shared tail can be tied to the rail the sources are already on.
HEALTHY_RING = (
    "M1 ua1 net1 VGND VGND mosbius_nmos w=1",
    "M2 ua1 net1 VAPWR VAPWR mosbius_pmos w=1",
    "M3 net2 ua1 VGND VGND mosbius_nmos w=1",
    "M4 net2 ua1 VAPWR VAPWR mosbius_pmos w=1",
    "M5 net1 net2 VGND VGND mosbius_nmos w=1",
    "M6 net1 net2 VAPWR VAPWR mosbius_pmos w=1",
)

# The same ring with the rails shorted in the schematic. xschem merged the
# two nets and kept the name VAPWR, so every drawn VGND came back as
# VAPWR -- except the body, which is a template string, not a wire.
SHORTED_RING = tuple(
    line.replace("VGND VGND mosbius_nmos", "VAPWR VGND mosbius_nmos")
    for line in HEALTHY_RING
)


def test_healthy_design_has_no_findings():
    assert check_design(design(*HEALTHY_RING)).findings == []


def test_merged_rails_are_an_error_not_a_warning():
    report = check_design(design(*SHORTED_RING))
    assert len(report.errors) == 1
    assert report.warnings == []
    assert report.errors[0].code == "D1"


def test_merged_rails_message_names_the_cause_and_the_fix():
    message = check_design(design(*SHORTED_RING)).errors[0].message
    assert "VAPWR and VGND are joined" in message
    assert "M1, M3, M5" in message                  # every offender named
    assert 'b=VGND' in message                      # why the body still disagrees
    assert "extra=" in message
    assert "delete it" in message                   # what to actually do


def test_only_the_affected_kind_is_reported():
    # The PMOS sources are on VAPWR, which is right for them -- the merge
    # is invisible from the PMOS side, so D1 must not double-report it.
    message = check_design(design(*SHORTED_RING)).errors[0].message
    assert "mosbius_nmos" in message
    assert "M2" not in message and "M4" not in message


def test_one_wrong_source_with_both_rails_present_is_only_a_warning():
    # VGND is still wired elsewhere, so the rails are fine and this is an
    # ordinary wiring mistake -- routable, hence WARN not ERROR.
    report = check_design(design(
        "M1 ua1 net1 VGND VGND mosbius_nmos w=1",
        "M2 ua2 net1 VAPWR VGND mosbius_nmos w=1",
    ))
    assert report.errors == []
    assert len(report.warnings) == 1
    assert "M2" in report.warnings[0].message
    assert "flipped vertically" in report.warnings[0].message


def test_warning_explains_the_doesnt_fit_the_user_will_see():
    report = check_design(design(
        "M1 ua1 net1 VGND VGND mosbius_nmos w=1",
        "M2 ua2 net1 VAPWR VGND mosbius_nmos w=1",
    ))
    message = report.warnings[0].message
    assert "ctrl_dpn_source" in message
    assert "nmos_a and nmos_b" in message
    assert "not enough NMOS" in message


def test_pmos_source_on_vgnd_is_caught_with_pmos_vocabulary():
    report = check_design(design(
        "M1 ua1 net1 VAPWR VAPWR mosbius_pmos w=1",
        "M2 ua2 net1 VGND VAPWR mosbius_pmos w=1",
    ))
    assert len(report.warnings) == 1
    message = report.warnings[0].message
    assert "ctrl_dpp_source" in message
    assert "pmos_a and pmos_b" in message


def test_body_terminal_alone_does_not_count_as_wiring_a_rail():
    # Every mosbius_nmos carries b=VGND from its template. If that counted
    # as a VGND connection, the merged-rail case would downgrade itself to
    # a warning and stop blocking.
    report = check_design(design(*SHORTED_RING))
    assert report.has_errors


# ---------------------------------------------------------------------------
# Wiring into the CLI: the checks have to actually run before routing.
# ---------------------------------------------------------------------------

def _write(tmp_path: Path, lines) -> Path:
    path = tmp_path / "design.spice"
    path.write_text("\n".join(lines) + "\n")
    return path


def test_route_refuses_a_merged_rail_design(tmp_path, capsys):
    rc = main(["route", str(_write(tmp_path, SHORTED_RING))])
    captured = capsys.readouterr()
    assert rc == 1
    assert "VAPWR and VGND are joined" in captured.err
    # The old behaviour: a misleading DOESN'T FIT about running out of NMOS.
    assert "DOESN'T FIT" not in captured.err
    assert "Bitstream" not in captured.out


def test_route_still_reports_the_warning_when_routing_then_fails(tmp_path, capsys):
    # Three NMOS with their sources on VAPWR, but VGND wired elsewhere, so
    # this is the warning path -- and the router does then run out of NMOS.
    # The warning has to survive onto the failure path, since it is the
    # explanation for the failure printed beneath it.
    lines = list(SHORTED_RING) + ["M7 ua3 ua4 VGND VGND mosbius_nmos w=1"]
    rc = main(["route", str(_write(tmp_path, lines))])
    err = capsys.readouterr().err
    assert rc == 1
    assert "source on VAPWR where VGND is expected" in err
    assert "DOESN'T FIT" in err


def test_route_passes_a_healthy_design_through_unchanged(tmp_path, capsys):
    rc = main(["route", str(_write(tmp_path, HEALTHY_RING))])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Bitstream:" in out
    # R1 does warn here (M5/M6 land on diff-pair halves -- see
    # test_check_routing.py); what must stay quiet is D1.
    assert "is expected" not in out and "joined" not in out


def test_watch_reports_the_merged_rails_too(tmp_path, capsys):
    rc = main(["watch", "--once", str(_write(tmp_path, SHORTED_RING))])
    out = capsys.readouterr().out
    assert rc == 0
    assert "DANGEROUS" in out
    assert "VAPWR and VGND are joined" in out


# ---------------------------------------------------------------------------
# D2: drain on the rail, source on an internal net -- a reversed transistor.
# ---------------------------------------------------------------------------

# The 3-stage ring that motivated D2, with the PMOS drawn upside down:
# drain on VAPWR, source on the internal node. The netlist is legal, the
# allocator reads it as three PMOS each wanting a routable source, and the
# only thing the user used to see was "not enough PMOS".
REVERSED_PMOS_RING = (
    "M1 ua1 net1 VGND VGND mosbius_nmos w=1",
    "M2 ua1 VAPWR net1 VAPWR mosbius_pmos w=1",
    "M3 net2 ua1 VGND VGND mosbius_nmos w=1",
    "M4 net2 VAPWR net3 VAPWR mosbius_pmos w=1",
    "M5 net1 net2 VGND VGND mosbius_nmos w=1",
    "M6 net1 VAPWR net2 VAPWR mosbius_pmos w=1",
)


def test_reversed_pmos_is_a_warning_naming_every_offender():
    report = check_design(design(*REVERSED_PMOS_RING))
    assert [f.code for f in report.warnings] == ["D2"]
    assert report.errors == []
    message = report.warnings[0].message
    assert message.startswith("WARNING -- drain and source look swapped on M2, M4, M6")


def test_reversed_pmos_message_connects_to_the_failure_the_user_sees():
    message = check_design(design(*REVERSED_PMOS_RING)).warnings[0].message
    # The point of the check: explain the "DOESN'T FIT" that follows.
    assert "not enough PMOS with independent sources" in message
    assert "flipped vertically" in message
    assert "source at the top" in message      # mosbius_pmos's real geometry
    assert "cascode" in message                # why it stays a hint


def test_a_healthy_design_does_not_trip_it():
    assert check_design(design(*HEALTHY_RING)).findings == []


def test_a_source_on_a_package_pin_is_not_flagged():
    # A source follower driving ua2 is an ordinary thing to draw, so the
    # check deliberately fires only on a source that is neither a rail nor
    # a ua[] pin.
    follower = ("M1 ua1 VGND ua2 VGND mosbius_nmos w=1",)
    assert check_design(design(*follower)).findings == []


def test_a_source_on_an_internal_net_alone_is_not_flagged():
    # Source on an internal node with the drain doing real work: a cascode
    # or a degenerated stage. Only drain-on-the-rail *as well* is nonsense.
    cascode = (
        "M1 ua1 ua2 net1 VGND mosbius_nmos w=1",
        "M2 ua3 net1 VGND VGND mosbius_nmos w=1",
    )
    assert check_design(design(*cascode)).findings == []


def test_reversed_nmos_reports_the_nmos_rail_and_geometry():
    reversed_nmos = ("M1 ua1 VGND net1 VGND mosbius_nmos w=1",)
    message = check_design(design(*reversed_nmos)).warnings[0].message
    assert "drain on VGND" in message
    assert "drain at the top" in message        # mosbius_nmos is the other way up
    assert "not enough NMOS with independent sources" in message


def test_route_prints_the_hint_before_the_doesnt_fit(tmp_path, capsys):
    path = tmp_path / "ring.spice"
    path.write_text("\n".join(REVERSED_PMOS_RING) + "\n")
    rc = main(["route", str(path)])
    err = capsys.readouterr().err
    assert rc == 1
    assert err.index("drain and source look swapped") < err.index("DOESN'T FIT")


# ---------------------------------------------------------------------------
# D3/D4: a drawn mosbius_ntail/mosbius_ptail (TODO.md was Sec 2, closed
# 2026-08-22) whose drain
# doesn't cleanly declare a pair -- either the wrong number of same-polarity
# sources share it, or it's wired straight to the rail the bank feeds.
# ---------------------------------------------------------------------------

# A healthy NMOS tail: exactly two mosbius_nmos share its drain net.
HEALTHY_TAIL = (
    "XM1 ua1 ua3 net1 VGND mosbius_nmos w=1",
    "XM2 ua2 ua4 net1 VGND mosbius_nmos w=1",
    "XT1 net1 ibias VGND mosbius_ntail tail=6",
)


def test_a_healthy_tail_has_no_findings():
    assert check_design(design(*HEALTHY_TAIL)).findings == []


def test_a_tail_with_no_matching_sources_is_an_error():
    orphan = ("XT1 net1 ibias VGND mosbius_ntail tail=6",)
    report = check_design(design(*orphan))
    assert len(report.errors) == 1
    assert report.errors[0].code == "D3"
    assert "nothing else in the design has its source" in report.errors[0].message


def test_a_tail_with_one_matching_source_names_it():
    one_half = ("XM1 ua1 ua3 net1 VGND mosbius_nmos w=1",
                "XT1 net1 ibias VGND mosbius_ntail tail=6")
    message = check_design(design(*one_half)).errors[0].message
    assert "1 mosbius_nmos devices have their source there: XM1" in message


def test_a_tail_with_three_matching_sources_is_also_wrong_arity():
    three = HEALTHY_TAIL + ("XM3 ua5 ua4 net1 VGND mosbius_nmos w=1",)
    message = check_design(design(*three)).errors[0].message
    assert "3 mosbius_nmos devices have their source there" in message
    assert "XM1, XM2, XM3" in message


def test_a_tail_wired_straight_to_the_rail_is_a_different_error():
    rail_tied = ("XT1 VGND ibias VGND mosbius_ntail tail=6",)
    report = check_design(design(*rail_tied))
    assert len(report.errors) == 1
    assert report.errors[0].code == "D4"
    assert "wired straight to VGND" in report.errors[0].message
    assert "never both at once" in report.errors[0].message


def test_a_pmos_tail_uses_pmos_vocabulary():
    pmos_tail = (
        "XM1 ua1 ua3 net1 VAPWR mosbius_pmos w=1",
        "XM2 ua2 ua4 net1 VAPWR mosbius_pmos w=1",
        "XT1 net1 ibias_p VAPWR mosbius_ptail tail=4",
    )
    assert check_design(design(*pmos_tail)).findings == []
    orphan = ("XT1 net1 ibias_p VAPWR mosbius_ptail tail=4",)
    message = check_design(design(*orphan)).errors[0].message
    assert "mosbius_pmos" in message
    assert "ctrl_dpp_tail" in message


def test_route_refuses_a_malformed_tail_before_routing(tmp_path, capsys):
    path = tmp_path / "orphan_tail.spice"
    path.write_text("XT1 net1 ibias VGND mosbius_ntail tail=6\n")
    rc = main(["route", str(path)])
    err = capsys.readouterr().err
    assert rc == 1
    assert "D3" in err or "doesn't declare a pair" in err
