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

from mosbius.check import check
from mosbius.netlist import NetlistError, parse_netlist
from mosbius.route import RouteError, route

POLL_INTERVAL_SECONDS = 0.2


def _now() -> str:
    return time.strftime("%H:%M:%S")


def _report(netlist_path: Path) -> str:
    """Run parse -> route -> check once and return the report text."""
    try:
        text = netlist_path.read_text()
    except OSError as e:
        return f"mosbius watch -- {netlist_path.name}          {_now()}   CAN'T READ\n\n  {e}"

    header = f"mosbius watch -- {netlist_path.name}          {_now()}"

    try:
        design = parse_netlist(text)
    except NetlistError as e:
        return f"{header}   IMPOSSIBLE\n\n  {e}"

    try:
        routed = route(design)
    except RouteError as e:
        return f"{header}   IMPOSSIBLE\n\n  {e}"

    result = check(routed.config)
    if result.has_errors:
        lines = [f"{header}   DANGEROUS"]
        for f in result.errors:
            lines.append("")
            lines.append("\n".join(f"  {line}" for line in f.message.splitlines()))
        return "\n".join(lines)

    lines = [f"{header}   OK"]
    for dev_name, role in sorted(routed.device_roles.items()):
        lines.append(f"  {dev_name:<12} -> {role}")
    if result.warnings:
        lines.append("")
        lines.append(f"  {len(result.warnings)} warning(s) -- see 'mosbius check' for detail")
    return "\n".join(lines)


def watch(netlist_path: Path, *, once: bool = False, out=sys.stdout) -> None:
    """Poll `netlist_path` and print a report every time it changes.

    `once=True` runs a single report and returns (used by tests, and by
    `mosbius watch --once` for scripting/CI).
    """
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
