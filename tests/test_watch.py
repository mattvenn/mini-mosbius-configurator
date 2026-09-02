# SPDX-License-Identifier: Apache-2.0
"""mosbius/watch.py -- SPEC.md Sec 3.3 live netlist watcher.

M3 exit criterion: "mosbius watch reports a deliberately broken edit
within about a second". The polling loop itself (mtime-based, see the
module docstring for why not inotify) is simple and time-based, so these
tests exercise report generation (_report) directly plus one lightweight
end-to-end pass through watch(once=True) -- not the sleep loop's timing.
"""

from __future__ import annotations

import io
from pathlib import Path

from mosbius import messages
from mosbius.watch import _report, watch

INVERTER_NETLIST = """
nfeta_0 ua1 ua2 VGND net1 mosbius_nmos w=1
pfeta_1 ua1 ua2 VAPWR net2 mosbius_pmos w=1
"""


def test_ok_report_lists_device_roles(tmp_path: Path):
    netlist = tmp_path / "design.spice"
    netlist.write_text(INVERTER_NETLIST)
    report = _report(netlist)
    assert messages.WATCH_STATUS_OK in report.splitlines()[0]
    assert "nfeta_0" in report and "-> nmos_a" in report
    assert "pfeta_1" in report and "-> pmos_a" in report


def test_missing_file_reports_cant_read(tmp_path: Path):
    report = _report(tmp_path / "does_not_exist.spice")
    assert messages.WATCH_CANT_READ.split("\n")[0] in report.splitlines()[0]


def test_netlist_with_no_devices_reports_impossible(tmp_path: Path):
    netlist = tmp_path / "empty.spice"
    netlist.write_text("* nothing here\n")
    report = _report(netlist)
    assert messages.CLI_IMPOSSIBLE.split("\n")[0] in report.splitlines()[0]
    assert "no mosbius_" in report


def test_over_capacity_design_reports_impossible_with_explanation(tmp_path: Path):
    netlist = tmp_path / "broken.spice"
    netlist.write_text("""
    m1 g1 d1 s1 b1 mosbius_nmos w=1
    m2 g2 d2 s2 b2 mosbius_nmos w=1
    m3 g3 d3 s3 b3 mosbius_nmos w=1
    """)
    report = _report(netlist)
    assert messages.WATCH_STATUS_IMPOSSIBLE in report.splitlines()[0]
    assert "DOESN'T FIT" in report
    assert "m3" in report  # names the specific device that didn't fit


def test_editing_between_two_once_calls_changes_the_report(tmp_path: Path):
    # Simulates "user edits the schematic, re-netlists" without needing
    # to exercise the actual polling loop's timing.
    netlist = tmp_path / "design.spice"
    netlist.write_text(INVERTER_NETLIST)
    good = _report(netlist)
    assert messages.WATCH_STATUS_OK in good.splitlines()[0]

    netlist.write_text("* broke it\n")
    bad = _report(netlist)
    assert messages.WATCH_STATUS_IMPOSSIBLE in bad.splitlines()[0]


def test_watch_once_true_reports_and_returns(tmp_path: Path):
    netlist = tmp_path / "design.spice"
    netlist.write_text(INVERTER_NETLIST)
    out = io.StringIO()
    watch(netlist, once=True, out=out)  # must return, not loop forever
    assert messages.WATCH_STATUS_OK in out.getvalue()


def test_watch_once_true_on_missing_file_still_returns(tmp_path: Path):
    out = io.StringIO()
    watch(tmp_path / "nope.spice", once=True, out=out)
    assert messages.WATCH_CANT_READ.split("\n")[0] in out.getvalue()
