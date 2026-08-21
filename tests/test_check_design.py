# SPDX-License-Identifier: Apache-2.0
"""mosbius/check.py -- check_design(), the netlist-level checks (D1).

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
