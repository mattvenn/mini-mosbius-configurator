# SPDX-License-Identifier: Apache-2.0
"""The `mosbius` command line (SPEC.md's `mosbius decode`/`mosbius watch`
examples): thin argument-parsing wrappers around the already-tested library
functions in decode.py/check.py/route.py/simulate.py/watch.py/program.py. No
new logic lives here -- each subcommand's job is turning argv into a function
call and its result into text on stdout, per CLAUDE.md's beginner-facing
diagnostics rule.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mosbius import messages
from mosbius.bitstream import BitstreamError
from mosbius.check import SafetyReport, check, check_design, check_routing, merge_findings
from mosbius.decode import decode, format_summary
from mosbius.model import DEFAULT_IBIAS, SwitchConfig
from mosbius.netlist import NetlistError, StaleNetlistError, check_netlist_fresh, parse_netlist
from mosbius.pads import (
    DEFAULT_PROJECT,
    DEFAULT_SHUTTLE,
    PadLookupError,
    format_pad_table,
)
from mosbius.program import (
    ProgramError,
    ibias_warning,
    program,
    read_board_identity,
)
from mosbius.route import (
    RouteError,
    format_device_roles,
    format_net_rows,
    format_pad_note,
    route as route_fresh,
    route_sticky,
)
from mosbius.simulate import SimulateError, check_routed_fresh, simulate_from_routed_json
from mosbius.watch import watch



class ArgumentError(ValueError):
    """A command-line argument isn't the kind of thing the command reads,
    explained rather than raised as a traceback.
    """


def _bitstream_arg(value: str) -> str:
    """Accept either the 48 hex characters themselves or the path to a
    routed design JSON, and read the bitstream out of the latter.

    Handing `mosbius decode` a `build/<name>.mosbius.json` is the obvious
    thing to try -- it is the file the rest of the pipeline passes around,
    and it is what `mosbius simulate` takes -- so it should work rather
    than ending in a BitstreamError traceback about hex length. The mirror
    slip (a routed JSON given to `route`) is already handled the same way.
    """
    path = Path(value)
    if not path.exists():
        # A bitstream is 48 hex characters and nothing else, so anything
        # with a slash or a file extension in it was meant as a path. Say
        # the file is missing, rather than letting it fall through to
        # from_bitstream() and come back as "27 hex characters, expected
        # 48" -- which is what someone sees who ran this before `route`
        # had written the file, i.e. exactly the person least able to
        # decode that answer.
        if "/" in value or path.suffix:
            raise ArgumentError(messages.CLI_NO_FILE_AT_PATH.format(path=path))
        return value

    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        raise ArgumentError(messages.CLI_UNRECOGNIZED_ARG.format(path=path))

    stream = data.get("bitstream") if isinstance(data, dict) else None
    if not isinstance(stream, str):
        raise ArgumentError(messages.CLI_JSON_NO_BITSTREAM_KEY.format(path=path))
    return stream


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
        plural = "s" if skipped != 1 else ""
        note = messages.CLI_REPORT_INFO_NOTE.format(skipped=skipped, plural=plural) if skipped else ""
        return messages.CLI_REPORT_OK.format(note=note)
    lines = []
    for f in shown:
        lines.append(f.message)
        lines.append("")
    return "\n".join(lines).rstrip("\n")


def cmd_decode(args: argparse.Namespace) -> int:
    try:
        config = SwitchConfig.from_bitstream(_bitstream_arg(args.bitstream), ibias=args.ibias)
    except (ArgumentError, BitstreamError) as e:
        print(messages.CLI_CANT_READ_THAT.format(e=e), file=sys.stderr)
        return 1
    print(format_summary(decode(config)))
    return 0


def _shuttle_for(args: argparse.Namespace) -> str:
    """Which shuttle's pad mapping to use: what the user said, else what
    the chip in the socket says about itself.

    Asking the board is the right answer because the pad letters follow
    from where the project sits on *that* shuttle, and the chip carries
    that in its own ROM -- so a different chip in the socket gives a
    different table without anyone having to remember a flag.

    There is no fallback, and that is deliberate. A pad table is an
    instruction to clip a probe onto a specific letter, so a guessed one is
    worse than none: it reads exactly like a measured one and sends someone
    probing a pad with nothing on it. Both ways of not knowing -- no board
    answering, or a board whose chip does not carry this project -- are
    also both ways of not being able to program the bitstream in the first
    place, so failing here says the same thing `mosbius program` would say
    a moment later. Working away from the bench is still fine; it just has
    to name the chip it means, with --shuttle.

    Raises PadLookupError, which cmd_pads already reports properly.
    """
    if args.shuttle:
        return args.shuttle
    try:
        identity = read_board_identity(project=args.project, port=getattr(args, "port", None))
    except ProgramError as e:
        raise PadLookupError(
            messages.CLI_CANT_ASK_BOARD.format(
                e=e, bitstream=args.bitstream, default_shuttle=DEFAULT_SHUTTLE
            )
        ) from e
    if identity.get("has_project") is False:
        raise PadLookupError(
            messages.CLI_PROJECT_NOT_ON_SHUTTLE.format(
                shuttle=identity["shuttle"],
                project=args.project,
                default_project=DEFAULT_PROJECT,
            )
        )
    return identity["shuttle"]


def cmd_pads(args: argparse.Namespace) -> int:
    try:
        config = SwitchConfig.from_bitstream(_bitstream_arg(args.bitstream), ibias=args.ibias)
    except (ArgumentError, BitstreamError) as e:
        print(messages.CLI_CANT_READ_THAT.format(e=e), file=sys.stderr)
        return 1
    try:
        print(format_pad_table(config, _shuttle_for(args), args.project))
    except PadLookupError as e:
        print(messages.CLI_CANT_WORK_OUT_PADS.format(e=e), file=sys.stderr)
        return 1
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    try:
        config = SwitchConfig.from_bitstream(_bitstream_arg(args.bitstream), ibias=args.ibias)
    except (ArgumentError, BitstreamError) as e:
        print(messages.CLI_CANT_READ_THAT.format(e=e), file=sys.stderr)
        return 1
    report = check(config)
    print(_format_report(report, verbose=args.verbose))
    return 1 if report.has_errors else 0


def cmd_route(args: argparse.Namespace) -> int:
    try:
        check_netlist_fresh(args.netlist)
        design = parse_netlist(args.netlist.read_text())
    except StaleNetlistError as e:
        print(messages.CLI_OUT_OF_DATE.format(e=e), file=sys.stderr)
        return 1
    except NetlistError as e:
        print(messages.CLI_IMPOSSIBLE.format(e=e), file=sys.stderr)
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
        print(messages.CLI_IMPOSSIBLE.format(e=e), file=sys.stderr)
        return 1

    report = SafetyReport(
        findings=design_report.findings
        + check_routing(routed).findings
        + check(routed.config).findings
    )
    print(_format_report(report, verbose=args.verbose))
    print()
    print(messages.CLI_DEVICE_ROLES_HEADER)
    for line in format_device_roles(routed):
        print(line)
    print()
    print(messages.CLI_BUS_ROWS_HEADER)
    for line in format_net_rows(routed) + format_pad_note(routed):
        print(line)
    print()
    print(messages.CLI_BITSTREAM_LINE.format(bitstream=routed.config.to_bitstream()))
    return 1 if report.has_errors else 0


def cmd_simulate(args: argparse.Namespace) -> int:
    try:
        check_routed_fresh(args.routed)
        name, spice_text = simulate_from_routed_json(args.routed)
    except SimulateError as e:
        print(messages.CLI_CANT_SIMULATE.format(e=e), file=sys.stderr)
        return 1
    out = args.out or args.routed.with_name(f"{name}_routed.spice")
    out.write_text(spice_text)
    print(messages.CLI_SIMULATE_OK.format(out=out, name=name))
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    try:
        watch(args.netlist, once=args.once)
    except KeyboardInterrupt:
        # Ctrl-C is how anyone stops a watch -- it is the documented exit,
        # so it should not look like a crash. mosbius/watch.py's own
        # __main__ already did this; going through the cli did not.
        print(messages.CLI_STOPPED_WATCHING, file=sys.stderr)
    return 0


def cmd_program(args: argparse.Namespace) -> int:
    try:
        config = SwitchConfig.from_bitstream(_bitstream_arg(args.bitstream), ibias=args.ibias)
    except (ArgumentError, BitstreamError) as e:
        print(messages.CLI_CANT_READ_THAT.format(e=e), file=sys.stderr)
        return 1
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
    verified = messages.CLI_PROGRAM_VERIFIED_SUFFIX if result.get("verify_ok") else ""
    print(messages.CLI_PROGRAM_UPLOADED.format(project=args.project) + verified)
    # The upload is only half of what someone at the bench needs: the
    # other half is where to put the probe, and the schematic cannot say
    # it (nothing on the board is labelled "ua2"). Which pad each ua[k] is
    # on depends on the shuttle, so the upload reads that off the chip's
    # own ROM on the way past.
    shuttle = args.shuttle or result.get("shuttle")
    if args.shuttle:
        print(messages.CLI_PROGRAM_SHUTTLE_FROM_FLAG.format(shuttle=shuttle))
    elif shuttle:
        repo, commit = result.get("repo"), result.get("commit")
        provenance = messages.CLI_PROGRAM_PROVENANCE.format(
            identity_source=result.get("identity_source", "chip ROM")
        )
        print(messages.CLI_PROGRAM_SHUTTLE_FROM_CHIP.format(shuttle=shuttle, provenance=provenance))
        if repo:
            commit_suffix = messages.CLI_PROGRAM_CHIP_COMMIT_SUFFIX.format(commit=commit) if commit else ""
            print(messages.CLI_PROGRAM_CHIP_LINE.format(repo=repo) + commit_suffix)
    if not shuttle:
        # The bits are on the chip, so this is not a failed upload -- but a
        # pad table for a guessed shuttle would look exactly like a real one
        # and send someone probing a pad with nothing on it, so say nothing
        # rather than guess.
        print(
            messages.CLI_PROGRAM_NO_SHUTTLE_NOTE.format(
                bitstream=args.bitstream, default_shuttle=DEFAULT_SHUTTLE
            ),
            file=sys.stderr,
        )
        warning = ibias_warning(result, config)
        if warning:
            print(warning, file=sys.stderr)
        return 0
    warning = ibias_warning(result, config)
    if warning:
        print(warning, file=sys.stderr)
    print()
    try:
        print(format_pad_table(config, shuttle, args.project))
    except PadLookupError as e:
        # The bits are on the chip either way -- this must not read as a
        # failed upload, so it is a note rather than an error.
        print(
            messages.CLI_PROGRAM_PAD_TABLE_UNAVAILABLE.format(e=e),
            file=sys.stderr,
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="mosbius", description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)

    def add_ibias(p):
        p.add_argument("--ibias", type=float, default=DEFAULT_IBIAS, help=messages.CLI_HELP_IBIAS)

    def add_board(p):
        p.add_argument(
            "--project", default=DEFAULT_PROJECT,
            help=messages.CLI_HELP_PROJECT.format(default_project=DEFAULT_PROJECT),
        )
        p.add_argument(
            "--shuttle", default=None,
            help=messages.CLI_HELP_SHUTTLE.format(default_shuttle=DEFAULT_SHUTTLE),
        )
        p.add_argument("--port", default=None, help=messages.CLI_HELP_PORT)

    p = sub.add_parser("decode", help=messages.CLI_HELP_DECODE)
    p.add_argument("bitstream", help=messages.CLI_HELP_BITSTREAM_ARG)
    add_ibias(p)
    p.set_defaults(func=cmd_decode)

    p = sub.add_parser("pads", help=messages.CLI_HELP_PADS)
    p.add_argument("bitstream", help=messages.CLI_HELP_BITSTREAM_ARG)
    add_ibias(p)
    add_board(p)
    p.set_defaults(func=cmd_pads)

    p = sub.add_parser("check", help=messages.CLI_HELP_CHECK)
    p.add_argument("bitstream", help=messages.CLI_HELP_BITSTREAM_ARG)
    add_ibias(p)
    p.add_argument("--verbose", "-v", action="store_true", help=messages.CLI_HELP_VERBOSE)
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("route", help=messages.CLI_HELP_ROUTE)
    p.add_argument("netlist", type=Path, help=messages.CLI_HELP_NETLIST_ARG)
    p.add_argument("--out", type=Path, help=messages.CLI_HELP_ROUTE_OUT)
    p.add_argument("--force", action="store_true", help=messages.CLI_HELP_ROUTE_FORCE)
    p.add_argument("--verbose", "-v", action="store_true", help=messages.CLI_HELP_VERBOSE)
    p.set_defaults(func=cmd_route)

    p = sub.add_parser("simulate", help=messages.CLI_HELP_SIMULATE)
    p.add_argument("routed", type=Path, help=messages.CLI_HELP_SIMULATE_ROUTED_ARG)
    p.add_argument("--out", type=Path, help=messages.CLI_HELP_SIMULATE_OUT)
    p.set_defaults(func=cmd_simulate)

    p = sub.add_parser("watch", help=messages.CLI_HELP_WATCH)
    p.add_argument("netlist", type=Path)
    p.add_argument("--once", action="store_true", help=messages.CLI_HELP_WATCH_ONCE)
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("program", help=messages.CLI_HELP_PROGRAM)
    p.add_argument("bitstream", help=messages.CLI_HELP_BITSTREAM_ARG)
    add_ibias(p)
    add_board(p)
    p.add_argument("--force", action="store_true", help=messages.CLI_HELP_PROGRAM_FORCE)
    p.add_argument("--no-reset", action="store_true", help=messages.CLI_HELP_PROGRAM_NO_RESET)
    p.add_argument("--verify", action="store_true", help=messages.CLI_HELP_PROGRAM_VERIFY)
    p.set_defaults(func=cmd_program)

    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
