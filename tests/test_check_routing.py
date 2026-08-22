# SPDX-License-Identifier: Apache-2.0
"""mosbius/check.py -- check_routing(), the post-routing checks (R1), and
the width bookkeeping in route.py that feeds it.

A device the allocator puts on a diff-pair half keeps its w= in the
netlist and has it ignored in the bitstream, because those halves have no
width bits. The value it is silently dropped *to* is w=4, not w=1, so a
schematic that looks symmetric gets built asymmetric.
"""

from __future__ import annotations

from pathlib import Path

from mosbius.check import check_routing
from mosbius.cli import main
from mosbius.netlist import parse_netlist
from mosbius.route import FIXED_WIDTH, device_widths, route

RING = """
M1 ua1 net1 VGND VGND mosbius_nmos w=1
M2 ua1 net1 VAPWR VAPWR mosbius_pmos w=1
M3 net2 ua1 VGND VGND mosbius_nmos w=1
M4 net2 ua1 VAPWR VAPWR mosbius_pmos w=1
M5 net1 net2 VGND VGND mosbius_nmos w=1
M6 net1 net2 VAPWR VAPWR mosbius_pmos w=1
"""

# The same ring drawn at the width the diff-pair halves are fixed at, so
# every stage matches -- what examples/ringosc/README.md actually uses.
MATCHED_RING = RING.replace("w=1", "w=4")


def routed(text: str):
    return route(parse_netlist(text))


def test_diff_pair_halves_are_fixed_at_the_programmable_maximum():
    # nmos_prog's slices are 1x + 1x + 2x, so its maximum is w=4, and
    # diff_n's halves are that same W=40 nf=8. Same story for the PMOS.
    assert set(FIXED_WIDTH.values()) == {4}


def test_width_is_reported_for_every_device():
    widths = routed(RING).device_widths
    assert set(widths) == {"M1", "M2", "M3", "M4", "M5", "M6"}
    assert widths["M1"].effective == 1 and widths["M1"].programmable
    assert widths["M5"].effective == 4 and not widths["M5"].programmable


def test_dropped_width_is_flagged_on_the_diff_pair_halves_only():
    report = check_routing(routed(RING))
    assert [f.code for f in report.warnings] == ["R1", "R1"]
    assert report.errors == []
    # Check the headlines, not the whole body: the body cites "diff_n.sch
    # M1/M2", which is sky130 instance names inside the submodule, not the
    # user's M1.
    headlines = sorted(f.message.splitlines()[0] for f in report.warnings)
    assert headlines[0].startswith("WARNING -- M5's w=1 was ignored")
    assert headlines[1].startswith("WARNING -- M6's w=1 was ignored")


def test_message_names_the_geometry_and_the_matching_fix():
    warning = check_routing(routed(RING)).warnings[0].message
    assert "W=40 nf=8" in warning        # what the half actually is
    assert "diff_n.sch" in warning       # verifiable against the submodule
    assert "w=4" in warning              # what you get
    assert "w=1" in warning              # what you asked for
    assert "examples/ringosc" in warning # a worked example of the fix


def test_asking_for_the_fixed_width_loses_nothing_and_is_silent():
    # w=4 is what a half is anyway, so nothing was dropped.
    assert check_routing(routed(MATCHED_RING)).warnings == []


def test_pmos_half_reports_pmos_geometry():
    warning = [
        f.message for f in check_routing(routed(RING)).warnings if "M6" in f.message
    ][0]
    assert "W=120 nf=16" in warning
    assert "diff_p.sch" in warning
    assert "pmos_prog.sch" in warning


def test_sticky_replay_recomputes_widths_rather_than_losing_them(tmp_path):
    # device_widths is deliberately not persisted (it is a pure function of
    # the design and the roles), so the replay path has to rebuild it --
    # otherwise the warning appears on the first run and vanishes after.
    from mosbius.route import route_sticky

    design = parse_netlist(RING)
    config_path = tmp_path / "ring.mosbius.json"
    first = route_sticky(design, config_path)
    second = route_sticky(design, config_path)
    assert second.device_widths == first.device_widths
    assert check_routing(second).warnings != []


def test_legacy_role_names_still_get_their_widths(tmp_path):
    # A .mosbius.json written before the 2026-08-21 rename stores "dpn+".
    # Widths are keyed off the translated role, so they must survive it.
    from mosbius.route import route_sticky, save_routed_design

    design = parse_netlist(RING)
    config_path = tmp_path / "ring.mosbius.json"
    save_routed_design(route(design), design, config_path)
    stored = config_path.read_text().replace('"ndiffpair+"', '"dpn+"')
    config_path.write_text(stored)
    replayed = route_sticky(design, config_path)
    assert replayed.device_roles["M5"] == "ndiffpair+"
    assert replayed.device_widths["M5"].effective == 4


# ---------------------------------------------------------------------------
# The route table itself: the width actually
# programmed to be reported per device, not just the roles.
# ---------------------------------------------------------------------------

def test_route_table_shows_each_devices_real_width(tmp_path, capsys):
    path = tmp_path / "ring.spice"
    path.write_text(RING)
    rc = main(["route", str(path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "M1           -> nmos_a        w=1" in out
    assert "M5           -> ndiffpair+    w=4 (fixed)" in out


def test_watch_reports_the_dropped_width_too(tmp_path, capsys):
    path = tmp_path / "ring.spice"
    path.write_text(RING)
    rc = main(["watch", "--once", str(path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "was ignored" in out
    assert "w=4 (fixed)" in out


# ---------------------------------------------------------------------------
# R2: the same rule as R1, for the other setting a device can carry --
# a tail= that no bit in the bitstream can hold (TODO.md was Sec 2,
# closed 2026-08-22).
# ---------------------------------------------------------------------------

# The SR latch, whose last two NMOS land on the diff-pair halves, with a
# tail written on one of them. Nothing in the schematic can reach
# ctrl_dpn_tail, so the value has nowhere to go.
LATCH_WITH_TAIL = """
XM1 ua3  net1 VAPWR VAPWR mosbius_pmos w=1
XM2 ua3  net1 VGND  VGND  mosbius_nmos w=1
XM3 net1 ua3  VAPWR VAPWR mosbius_pmos w=1
XM4 net1 ua3  VGND  VGND  mosbius_nmos w=1
XM5 ua1  net1 VGND  VGND  mosbius_nmos w=1 tail=6
XM6 ua2  ua3  VGND  VGND  mosbius_nmos w=1
"""

OTA = "x1 ua1 ua4 ua2 ua5 ibias VGND VAPWR mosbius_ota tail=6\n"


def test_a_tail_on_a_diff_pair_half_is_reported_not_dropped():
    report = check_routing(routed(LATCH_WITH_TAIL))
    codes = [f.code for f in report.warnings]
    assert "R2" in codes
    r2 = [f for f in report.warnings if f.code == "R2"][0]
    assert r2.message.startswith("WARNING -- XM5's tail=6 was ignored")


def test_the_tail_message_points_at_the_tail_symbols():
    r2 = [f for f in check_routing(routed(LATCH_WITH_TAIL)).warnings
          if f.code == "R2"][0].message
    assert "mosbius_ntail" in r2      # the way to actually reach this bit
    assert "mosbius_ptail" in r2
    assert "mosbius_ota" in r2        # the other device that has a tail=


def test_a_tail_the_chip_can_carry_is_silent():
    report = check_routing(routed(OTA))
    assert [f.code for f in report.warnings] == []


def test_tail_is_reported_for_every_device():
    tails = routed(LATCH_WITH_TAIL).device_tails
    assert set(tails) == {"XM1", "XM2", "XM3", "XM4", "XM5", "XM6"}
    assert tails["XM5"].requested == 6 and not tails["XM5"].programmable
    assert tails["XM5"].effective is None    # no bit carries a half's own tail
    assert tails["XM2"].effective is None    # nmos_a has no tail at all


def test_a_devices_own_tail_is_shown_in_the_route_table(tmp_path, capsys):
    path = tmp_path / "ota.spice"
    path.write_text(OTA)
    rc = main(["route", str(path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "x1           -> ota           tail=6" in out


def test_sticky_replay_recomputes_tails_rather_than_losing_them(tmp_path):
    from mosbius.route import route_sticky

    design = parse_netlist(LATCH_WITH_TAIL)
    config_path = tmp_path / "latch.mosbius.json"
    first = route_sticky(design, config_path)
    second = route_sticky(design, config_path)
    assert second.device_tails == first.device_tails
    assert [f.code for f in check_routing(second).warnings if f.code == "R2"] == ["R2"]


def test_a_tail_on_a_device_that_has_none_says_so_differently():
    # nmos_a is a single transistor: it has no tail current at all, so the
    # diff-pair explanation would send the reader looking in the wrong place.
    report = check_routing(routed("XM1 ua1 ua2 VGND VGND mosbius_nmos w=1 tail=4\n"))
    r2 = [f for f in report.warnings if f.code == "R2"][0].message
    assert r2.startswith("WARNING -- XM1's tail=4 was ignored: nmos_a has no tail current")
    assert "ctrl_dpn_tail" not in r2          # not this device's problem
    assert "w= (1, 2, 3 or 4)" in r2          # what they probably meant
