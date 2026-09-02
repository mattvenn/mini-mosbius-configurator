# SPDX-License-Identifier: Apache-2.0
"""Live netlist watcher (SPEC.md Sec 3.3): re-runs parse -> route -> check
every time xschem writes the netlist file, and prints a short report.

Polls the netlist's mtime rather than using inotify/watchdog. This isn't
just the simplest option: xschem runs in the IIC-OSIC-TOOLS container
while this watches the file from the host, across the bind mount CLAUDE.md
describes -- and inotify events don't reliably cross that boundary on
every platform (notably macOS's virtiofs/osxfs). Polling every 200ms
sidesteps that entirely and comfortably meets the "within about a second"
target.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from mosbius import messages
from mosbius.check import check, check_design, check_routing, merge_findings
from mosbius.netlist import NetlistError, StaleNetlistError, check_netlist_fresh, parse_netlist
from mosbius.route import (
    RouteError,
    format_device_roles,
    format_net_rows,
    format_pad_note,
    route,
)

POLL_INTERVAL_SECONDS = 0.2


def _now() -> str:
    return time.strftime("%H:%M:%S")


def _report(netlist_path: Path) -> str:
    """Run parse -> route -> check once and return the report text."""
    try:
        text = netlist_path.read_text()
    except OSError as e:
        header = messages.WATCH_HEADER.format(name=netlist_path.name, time=_now())
        return f"{header}   " + messages.WATCH_CANT_READ.format(e=e)

    header = messages.WATCH_HEADER.format(name=netlist_path.name, time=_now())

    try:
        # Watch follows the netlist, not the schematic, so an edit that was
        # never netlisted looks like nothing happened at all. Say so on
        # every pass rather than re-reporting the old circuit as current.
        check_netlist_fresh(netlist_path)
        design = parse_netlist(text)
    except StaleNetlistError as e:
        return f"{header}   " + messages.CLI_OUT_OF_DATE.format(e=e)
    except NetlistError as e:
        return f"{header}   " + messages.CLI_IMPOSSIBLE.format(e=e)

    # Netlist-level checks (check.py's check_design) run before routing:
    # an error here makes routing pointless, and a warning here is usually
    # the explanation for whatever the router says next.
    design_report = check_design(design)
    if design_report.has_errors:
        lines = [f"{header}   " + messages.WATCH_STATUS_DANGEROUS]
        for f in merge_findings(design_report.errors):
            lines.append("")
            lines.append("\n".join(f"  {line}" for line in f.message.splitlines()))
        return "\n".join(lines)
    # merge_findings (TODO.md was Sec 3, closed 2026-08-22): several
    # near-identical findings -- e.g. every diff-pair half losing its w=,
    # or every unused bus segment -- print as one block naming every
    # device instead of repeating the same explanation per device.
    design_notes = [
        "\n".join(f"  {line}" for line in f.message.splitlines())
        for f in merge_findings(design_report.warnings)
    ]

    try:
        routed = route(design)
    except RouteError as e:
        lines = [f"{header}   " + messages.WATCH_STATUS_IMPOSSIBLE]
        for note in design_notes:
            lines += ["", note]
        lines += ["", f"  {e}"]
        return "\n".join(lines)

    # Post-routing checks join the netlist-level ones: both describe the
    # design rather than the bitstream, so both print in full here.
    design_notes += [
        "\n".join(f"  {line}" for line in f.message.splitlines())
        for f in merge_findings(check_routing(routed).warnings)
    ]

    result = check(routed.config)
    if result.has_errors:
        lines = [f"{header}   " + messages.WATCH_STATUS_DANGEROUS]
        for f in merge_findings(result.errors):
            lines.append("")
            lines.append("\n".join(f"  {line}" for line in f.message.splitlines()))
        return "\n".join(lines)

    ok_line = f"{header}   " + messages.WATCH_STATUS_OK
    ok_warn_line = f"{header}   " + messages.WATCH_STATUS_OK_WITH_WARNINGS
    lines = [ok_line] if not design_notes else [ok_warn_line]
    for note in design_notes:
        lines += ["", note, ""]
    lines += format_device_roles(routed)
    lines += ["", messages.CLI_BUS_ROWS_HEADER] + format_net_rows(routed) + format_pad_note(routed)
    if result.warnings:
        lines.append("")
        lines.append(messages.WATCH_MORE_WARNINGS.format(n=len(result.warnings)))
    return "\n".join(lines)


def watch(netlist_path: Path, *, once: bool = False, out=None) -> None:
    """Poll `netlist_path` and print a report every time it changes.

    `once=True` runs a single report and returns (used by tests, and by
    `mosbius watch --once` for scripting/CI).
    """
    # Resolved at call time, not import time: a `sys.stdout` default
    # argument binds whatever stdout *was* when this module first loaded,
    # silently ignoring any later reassignment (e.g. pytest's capsys, or
    # any other stdout redirection set up after import).
    if out is None:
        out = sys.stdout
    last_mtime: float | None = None
    while True:
        try:
            mtime = netlist_path.stat().st_mtime
        except OSError:
            mtime = None
        if mtime != last_mtime:
            last_mtime = mtime
            if mtime is not None:
                print(_report(netlist_path), file=out)
                print(file=out)
            if once:
                return
        elif once:
            # File didn't exist / hasn't changed since we started watching --
            # for a one-shot call, report on it once regardless.
            print(_report(netlist_path), file=out)
            print(file=out)
            return
        time.sleep(POLL_INTERVAL_SECONDS)


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("netlist", type=Path, help="the .spice file xschem writes")
    ap.add_argument("--once", action="store_true", help="report once and exit, don't poll")
    args = ap.parse_args(argv)

    try:
        watch(args.netlist, once=args.once)
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
