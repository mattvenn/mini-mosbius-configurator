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
from mosbius.program import ProgramError, program, read_board_identity
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
            raise ArgumentError(
                f"there is no file at {path}\n\n"
                f"  This looks like a path rather than a bitstream, and nothing is\n"
                f"  there. If you have not routed the design yet, that is the step\n"
                f"  that writes it:\n\n"
                f"    python3 -m mosbius.cli route build/<design>.spice --out {path}\n\n"
                f"  The netlist it reads comes from xschem's Netlist button, with\n"
                f"  xschem launched from the top of this repo so it picks up\n"
                f"  xschemrc and writes into build/.\n"
            )
        return value

    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        raise ArgumentError(
            f"{path} isn't something this command can read\n\n"
            f"  It expects either the 48 hex characters of a bitstream, or the\n"
            f"  path to a routed design -- the JSON file `mosbius route --out`\n"
            f"  writes, usually build/<design>.mosbius.json. This file is\n"
            f"  neither: it does not parse as JSON.\n\n"
            f"  If you meant the netlist (build/<design>.spice), route it first:\n\n"
            f"    python3 -m mosbius.cli route {path} --out build/<design>.mosbius.json\n"
        )

    stream = data.get("bitstream") if isinstance(data, dict) else None
    if not isinstance(stream, str):
        raise ArgumentError(
            f"{path} is JSON, but has no \"bitstream\" in it\n\n"
            f"  A routed design records its bitstream under that key. This file\n"
            f"  may be from an older version of the router, or hand-edited.\n"
            f"  Re-route the design to rewrite it:\n\n"
            f"    python3 -m mosbius.cli route build/<design>.spice --out {path}\n"
        )
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
        note = f" ({skipped} info note{'s' if skipped != 1 else ''} hidden, use --verbose)" if skipped else ""
        return f"OK -- no errors or warnings{note}."
    lines = []
    for f in shown:
        lines.append(f.message)
        lines.append("")
    return "\n".join(lines).rstrip("\n")


def cmd_decode(args: argparse.Namespace) -> int:
    try:
        config = SwitchConfig.from_bitstream(_bitstream_arg(args.bitstream), ibias=args.ibias)
    except (ArgumentError, BitstreamError) as e:
        print(f"CAN'T READ THAT\n\n  {e}", file=sys.stderr)
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
            f"can't ask the board which chip is in the socket, and which PCB pad\n"
            f"  each ua[k] comes out on depends on that -- Tiny Tapeout muxes the\n"
            f"  analog pins, so the same design on another shuttle lands on other\n"
            f"  pads. Guessing would print a table that looks measured and sends\n"
            f"  you to the wrong pad, so here is the underlying problem instead:\n\n"
            f"  {e}\n\n"
            f"  If you are away from the bench and just want to read the table,\n"
            f"  name the chip yourself:\n\n"
            f"    mosbius pads {args.bitstream} --shuttle {DEFAULT_SHUTTLE}"
        ) from e
    if identity.get("has_project") is False:
        raise PadLookupError(
            f"the chip in the socket is from shuttle {identity['shuttle']}, and\n"
            f"  {args.project} is not on it. There are no pads to name, because\n"
            f"  this bitstream cannot be programmed to that chip at all --\n"
            f"  `mosbius program` would stop with the same thing.\n\n"
            f"  Either put the right chip in, or say which project you mean with\n"
            f"  --project (it defaults to {DEFAULT_PROJECT}, this repo's own macro)."
        )
    return identity["shuttle"]


def cmd_pads(args: argparse.Namespace) -> int:
    try:
        config = SwitchConfig.from_bitstream(_bitstream_arg(args.bitstream), ibias=args.ibias)
    except (ArgumentError, BitstreamError) as e:
        print(f"CAN'T READ THAT\n\n  {e}", file=sys.stderr)
        return 1
    try:
        print(format_pad_table(config, _shuttle_for(args), args.project))
    except PadLookupError as e:
        print(f"CAN'T WORK OUT THE PADS\n\n  {e}", file=sys.stderr)
        return 1
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    try:
        config = SwitchConfig.from_bitstream(_bitstream_arg(args.bitstream), ibias=args.ibias)
    except (ArgumentError, BitstreamError) as e:
        print(f"CAN'T READ THAT\n\n  {e}", file=sys.stderr)
        return 1
    report = check(config)
    print(_format_report(report, verbose=args.verbose))
    return 1 if report.has_errors else 0


def cmd_route(args: argparse.Namespace) -> int:
    try:
        check_netlist_fresh(args.netlist)
        design = parse_netlist(args.netlist.read_text())
    except StaleNetlistError as e:
        print(f"OUT OF DATE\n\n  {e}", file=sys.stderr)
        return 1
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
    print("Bus rows:")
    for line in format_net_rows(routed) + format_pad_note(routed):
        print(line)
    print()
    print(f"Bitstream: {routed.config.to_bitstream()}")
    return 1 if report.has_errors else 0


def cmd_simulate(args: argparse.Namespace) -> int:
    try:
        check_routed_fresh(args.routed)
        name, spice_text = simulate_from_routed_json(args.routed)
    except SimulateError as e:
        print(f"CAN'T SIMULATE\n\n  {e}", file=sys.stderr)
        return 1
    out = args.out or args.routed.with_name(f"{name}_routed.spice")
    out.write_text(spice_text)
    print(f"OK -- wrote {out} ({name}_routed, real switch matrix + pads + coupling/wire caps)")
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    try:
        watch(args.netlist, once=args.once)
    except KeyboardInterrupt:
        # Ctrl-C is how anyone stops a watch -- it is the documented exit,
        # so it should not look like a crash. mosbius/watch.py's own
        # __main__ already did this; going through the cli did not.
        print("\nstopped watching.", file=sys.stderr)
    return 0


def _ibias_warning(result: dict, config: SwitchConfig) -> str | None:
    """What to say when the board could not deliver the bias current.

    Only the newer ETR demoboards carry the RP2350-controlled circuit that
    makes this current; on an older one `tt.analog_current_source` is None
    and the bias pin is simply unfed. The upload is still perfectly good --
    the 192 bits are on the chip -- but every mirror, differential-pair tail
    and OTA tail in the design is referenced to a current that isn't there,
    so a design using any of them measures nothing, quietly.
    """
    if result.get("ibias_set") is not False or not config.ibias:
        return None
    return (
        "\n  BIAS CURRENT NOT SET -- this demoboard has no current source.\n\n"
        f"  The bitstream is on the chip and correct. But {config.ibias * 1e6:.1f} uA was\n"
        "  asked for, and this board revision has no `analog_current_source`:\n"
        "  the RP2350-controlled bias circuit arrived on later ETR demoboards.\n"
        "  So the chip's bias pin is floating, and anything in this design that\n"
        "  mirrors it -- mosbius_nsink, mosbius_psource, mosbius_ntail,\n"
        "  mosbius_ptail, mosbius_ota -- has no operating point.\n\n"
        "  Feed it externally instead (SPEC.md Sec 3.4b): a bench supply through a\n"
        "  series resistor into the bias pad, sized so most of the supply is\n"
        "  dropped across the resistor. To confirm the pad and set the current:\n\n"
        "    python3 tools/measure_ibias_clamp_ad3.py --resistor 20000\n\n"
        "  A design of plain mosbius_nmos/mosbius_pmos FETs needs none of this."
    )


def cmd_program(args: argparse.Namespace) -> int:
    try:
        config = SwitchConfig.from_bitstream(_bitstream_arg(args.bitstream), ibias=args.ibias)
    except (ArgumentError, BitstreamError) as e:
        print(f"CAN'T READ THAT\n\n  {e}", file=sys.stderr)
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
    print(f"OK -- uploaded to {args.project}" + (" (verified)" if result.get("verify_ok") else ""))
    # The upload is only half of what someone at the bench needs: the
    # other half is where to put the probe, and the schematic cannot say
    # it (nothing on the board is labelled "ua2"). Which pad each ua[k] is
    # on depends on the shuttle, so the upload reads that off the chip's
    # own ROM on the way past.
    shuttle = args.shuttle or result.get("shuttle")
    if args.shuttle:
        print(f"   shuttle {shuttle} (from --shuttle, not from the chip)")
    elif shuttle:
        repo, commit = result.get("repo"), result.get("commit")
        provenance = f"read from the chip in the socket ({result.get('identity_source', 'chip ROM')})"
        print(f"   shuttle {shuttle} -- {provenance}")
        if repo:
            print(f"   chip {repo}" + (f" @ {commit}" if commit else ""))
    if not shuttle:
        # The bits are on the chip, so this is not a failed upload -- but a
        # pad table for a guessed shuttle would look exactly like a real one
        # and send someone probing a pad with nothing on it, so say nothing
        # rather than guess.
        print(
            "\n  (uploaded fine, but the board reported no shuttle, so which PCB\n"
            "   pad each ua[k] comes out on can't be worked out -- that mapping\n"
            "   is per shuttle. Re-run with --shuttle to get the table:\n\n"
            f"     mosbius pads {args.bitstream} --shuttle {DEFAULT_SHUTTLE})",
            file=sys.stderr,
        )
        warning = _ibias_warning(result, config)
        if warning:
            print(warning, file=sys.stderr)
        return 0
    warning = _ibias_warning(result, config)
    if warning:
        print(warning, file=sys.stderr)
    print()
    try:
        print(format_pad_table(config, shuttle, args.project))
    except PadLookupError as e:
        # The bits are on the chip either way -- this must not read as a
        # failed upload, so it is a note rather than an error.
        print(
            f"  (uploaded fine, but the pad table needs the shuttle index)\n\n  {e}",
            file=sys.stderr,
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="mosbius", description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)

    def add_ibias(p):
        p.add_argument("--ibias", type=float, default=DEFAULT_IBIAS, help="bias current in amps (default: 100uA)")

    def add_board(p):
        p.add_argument("--project", default=DEFAULT_PROJECT, help=f"project macro name (default: {DEFAULT_PROJECT})")
        p.add_argument(
            "--shuttle", default=None,
            help="shuttle the chip came from -- decides which pad each ua[k] is on "
                 "(default: read off the chip in the socket; without a board, pass "
                 f"e.g. --shuttle {DEFAULT_SHUTTLE})",
        )
        p.add_argument("--port", default=None, help="serial port, e.g. /dev/ttyACM0 (default: mpremote autodetects)")

    p = sub.add_parser("decode", help="show the circuit a 48-hex-char bitstream configures")
    p.add_argument("bitstream", help="a routed design (build/<design>.mosbius.json), or the 48 hex characters themselves")
    add_ibias(p)
    p.set_defaults(func=cmd_decode)

    p = sub.add_parser("pads", help="which PCB pad each connected pin comes out on, for a loaded bitstream")
    p.add_argument("bitstream", help="a routed design (build/<design>.mosbius.json), or the 48 hex characters themselves")
    add_ibias(p)
    add_board(p)
    p.set_defaults(func=cmd_pads)

    p = sub.add_parser("check", help="run the safety checker (SPEC.md Sec 3.1) against a bitstream")
    p.add_argument("bitstream", help="a routed design (build/<design>.mosbius.json), or the 48 hex characters themselves")
    add_ibias(p)
    p.add_argument("--verbose", "-v", action="store_true", help="also show INFO notes (e.g. unused bus rows)")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("route", help="netlist -> bitstream (parses, allocates, checks)")
    p.add_argument("netlist", type=Path, help="an xschem-netlisted .spice file")
    p.add_argument("--out", type=Path, help="persist/reuse routing here (SPEC.md Sec 3.2b sticky routing)")
    p.add_argument("--force", action="store_true", help="re-route even if --out's stored routing is still valid")
    p.add_argument("--verbose", "-v", action="store_true", help="also show INFO notes (e.g. unused bus rows)")
    p.set_defaults(func=cmd_route)

    p = sub.add_parser("simulate", help="routed design -> a real, silicon-accurate SPICE subcircuit")
    p.add_argument("routed", type=Path, help="a routed design JSON (<name>.mosbius.json), written by `mosbius route --out` -- not the netlist")
    p.add_argument("--out", type=Path, help="output .spice path (default: <name>_routed.spice next to the input)")
    p.set_defaults(func=cmd_simulate)

    p = sub.add_parser("watch", help="re-run route+check every time the netlist file changes")
    p.add_argument("netlist", type=Path)
    p.add_argument("--once", action="store_true", help="report once and exit, don't poll")
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("program", help="upload a bitstream to real hardware (SPEC.md Sec 3.5, M4)")
    p.add_argument("bitstream", help="a routed design (build/<design>.mosbius.json), or the 48 hex characters themselves")
    add_ibias(p)
    add_board(p)
    p.add_argument("--force", action="store_true", help="upload even if check() finds an error")
    p.add_argument("--no-reset", action="store_true", help="skip the known-state reset before shifting")
    p.add_argument("--verify", action="store_true", help="shift the bits back out and compare")
    p.set_defaults(func=cmd_program)

    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
