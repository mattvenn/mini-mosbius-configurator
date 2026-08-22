# SPDX-License-Identifier: Apache-2.0
"""The `mosbius` command line (SPEC.md's `mosbius decode`/`mosbius watch`
examples): thin argument-parsing wrappers around the already-tested library
functions in decode.py/check.py/route.py/watch.py/program.py. No new logic
lives here -- each subcommand's job is turning argv into a function call and
its result into text on stdout, per CLAUDE.md's beginner-facing diagnostics
rule.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mosbius.check import SafetyReport, check, check_design, check_routing, merge_findings
from mosbius.decode import decode, format_summary
from mosbius.model import DEFAULT_IBIAS, SwitchConfig
from mosbius.netlist import NetlistError, parse_netlist
from mosbius.program import ProgramError, program
from mosbius.route import (
    RouteError,
    format_device_roles,
    route as route_fresh,
    route_sticky,
)
from mosbius.watch import watch


def _format_report(report, *, verbose: bool = False) -> str:
    shown = report.errors + report.warnings
    if verbose:
        shown += [f for f in report.findings if f.severity == "INFO"]
    # merge_findings (TODO.md was Sec 3, closed 2026-08-22) collapses
    # several near-identical findings -- e.g. two diff-pair halves both
    # losing their w= -- into one block naming every device instead of
    # repeating the same 20-line explanation per device.
    shown = merge_findings(shown)
    if not shown:
        skipped = len(merge_findings(report.findings))  # all INFO here; merged count, not raw
        note = f" ({skipped} info note{'s' if skipped != 1 else ''} hidden, use --verbose)" if skipped else ""
        return f"OK -- no errors or warnings{note}."
    lines = []
    for f in shown:
        lines.append(f.message)
        lines.append("")
    return "\n".join(lines).rstrip("\n")


def cmd_decode(args: argparse.Namespace) -> int:
    config = SwitchConfig.from_bitstream(args.bitstream, ibias=args.ibias)
    print(format_summary(decode(config)))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    config = SwitchConfig.from_bitstream(args.bitstream, ibias=args.ibias)
    report = check(config)
    print(_format_report(report, verbose=args.verbose))
    return 1 if report.has_errors else 0


def cmd_route(args: argparse.Namespace) -> int:
    try:
        design = parse_netlist(args.netlist.read_text())
    except NetlistError as e:
        print(f"IMPOSSIBLE\n\n  {e}", file=sys.stderr)
        return 1

    # Netlist-level checks first: a design fault can make the router fail
    # for a reason that has nothing to do with the real mistake, and an
    # error here means there is no point routing at all.
    design_report = check_design(design)
    if design_report.has_errors:
        print(_format_report(design_report, verbose=args.verbose), file=sys.stderr)
        return 1

    try:
        if args.out:
            routed = route_sticky(design, args.out, force=args.force)
        else:
            routed = route_fresh(design)
    except RouteError as e:
        # Design warnings go out even on the failure path -- when one
        # fires, it is usually the explanation for the failure below.
        if design_report.warnings:
            print(_format_report(design_report, verbose=args.verbose), file=sys.stderr)
            print(file=sys.stderr)
        print(f"IMPOSSIBLE\n\n  {e}", file=sys.stderr)
        return 1

    report = SafetyReport(
        findings=design_report.findings
        + check_routing(routed).findings
        + check(routed.config).findings
    )
    print(_format_report(report, verbose=args.verbose))
    print()
    print("Device roles:")
    for line in format_device_roles(routed):
        print(line)
    print()
    print(f"Bitstream: {routed.config.to_bitstream()}")
    return 1 if report.has_errors else 0


def cmd_watch(args: argparse.Namespace) -> int:
    watch(args.netlist, once=args.once)
    return 0


def cmd_program(args: argparse.Namespace) -> int:
    config = SwitchConfig.from_bitstream(args.bitstream, ibias=args.ibias)
    try:
        result = program(
            config,
            project=args.project,
            force=args.force,
            reset=not args.no_reset,
            verify=args.verify,
            port=args.port,
        )
    except ProgramError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f"OK -- uploaded to {args.project}" + (" (verified)" if result.get("verify_ok") else ""))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="mosbius", description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)

    def add_ibias(p):
        p.add_argument("--ibias", type=float, default=DEFAULT_IBIAS, help="bias current in amps (default: 100uA)")

    p = sub.add_parser("decode", help="show the circuit a 48-hex-char bitstream configures")
    p.add_argument("bitstream", help="48 hex characters, e.g. 0000000000a4...")
    add_ibias(p)
    p.set_defaults(func=cmd_decode)

    p = sub.add_parser("check", help="run the safety checker (SPEC.md Sec 3.1) against a bitstream")
    p.add_argument("bitstream", help="48 hex characters")
    add_ibias(p)
    p.add_argument("--verbose", "-v", action="store_true", help="also show INFO notes (e.g. unused bus rows)")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("route", help="netlist -> bitstream (parses, allocates, checks)")
    p.add_argument("netlist", type=Path, help="an xschem-netlisted .spice file")
    p.add_argument("--out", type=Path, help="persist/reuse routing here (SPEC.md Sec 3.2b sticky routing)")
    p.add_argument("--force", action="store_true", help="re-route even if --out's stored routing is still valid")
    p.add_argument("--verbose", "-v", action="store_true", help="also show INFO notes (e.g. unused bus rows)")
    p.set_defaults(func=cmd_route)

    p = sub.add_parser("watch", help="re-run route+check every time the netlist file changes")
    p.add_argument("netlist", type=Path)
    p.add_argument("--once", action="store_true", help="report once and exit, don't poll")
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("program", help="upload a bitstream to real hardware (SPEC.md Sec 3.5, M4)")
    p.add_argument("bitstream", help="48 hex characters")
    add_ibias(p)
    p.add_argument("--project", default="tt_um_tnt_mosbius")
    p.add_argument("--force", action="store_true", help="upload even if check() finds an error")
    p.add_argument("--no-reset", action="store_true", help="skip the known-state reset before shifting")
    p.add_argument("--verify", action="store_true", help="shift the bits back out and compare")
    p.add_argument("--port", default=None, help="serial port, e.g. /dev/ttyACM0 (default: mpremote autodetects)")
    p.set_defaults(func=cmd_program)

    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
