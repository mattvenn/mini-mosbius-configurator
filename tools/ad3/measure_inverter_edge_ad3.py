#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Time the inverter's output rise on real silicon.

TODO.md's bench item: `examples/inverter/README.md`'s rise-time row reads
8.16 ns as drawn, 24.63 ns as routed, and "not measured" on the chip. This
drives ua1 with a real edge and times ua2's 10%-90% rise, the same shape as
`tools/ad3/measure_srlatch_edge_ad3.py` (a delay) and
`tools/ad3/measure_settling_ad3.py` (a slew/tau). Run from the repo root,
on the host:

    python3 tools/ad3/measure_inverter_edge_ad3.py

**This exists to test an assumption, not confirm one.** TODO.md guesses the
AD3's own generator is too slow to drive an edge this fast to say anything
useful about it. That was a guess, not a measurement -- nobody had put the
AD3 on this circuit and looked. This script reports ua1's own 10%-90% edge
(what the generator actually delivers into the chip) beside ua2's, so the
margin between them is visible instead of assumed. If the two are close,
the number below is mostly a measurement of the instrument; if ua2's edge
is comfortably slower, it is not.

**Compare the result against the routed figure only after re-simulating at
the AD3's loading.** `tb_inverter.sch` assumes a 10x probe (`rprobe=10meg
cprobe=10p`); the AD3 presents `rprobe=1meg cprobe=24p` on the pin it is
measuring, and this output node is exactly where TODO.md says that
difference matters most. This script does not re-run that deck -- it only
says whether the bench edge is fast enough to be worth re-running it
against.

**`--no-input-probe` exists because monitoring ua1 turned out to slow it
down.** W1 wired straight into the scope (nothing else in the path) showed
a clean 30 ns edge, but the same generator "as it arrives" at ua1 with `1+`
also attached there measured 74 ns -- 1+'s own ~24 pF, sitting in parallel
with the pad's, is loading the very node it is trying to observe. Since the
trigger only needs ua2 (channel 1), this flag drops `1+` from the capture
entirely so ua1 can be driven unloaded; wire only the drive lead and `2+`
this way. If ua2's measured rise barely moves with `1+` disconnected, the
output number is dominated by the circuit rather than the stimulus, which
is the thing worth knowing. It cannot report ua1's own edge in this mode --
there is nothing left to measure it with.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ad3  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from mosbius.bitstream import unpack  # noqa: E402
from mosbius.model import SwitchConfig  # noqa: E402
from mosbius.program import (  # noqa: E402
    ProgramError,
    ibias_warning,
    program,
)
from mosbius.pads import format_analog_header, pads_in_use  # noqa: E402

# examples/inverter as the router placed it on 2026-08-28, ua1 in, ua2 out --
# the same string tools/ad3/measure_inverter_ad3.py programs.
# It is a record of an experiment, not a cached build artifact: if the
# router's allocation ever changes, re-route and re-measure rather than
# editing this string, or the published numbers quietly stop describing the
# configuration that was actually on the chip.
BITSTREAM = "080000004010000001000000000000000040000400000000"
PROJECT = "tt_um_tnt_mosbius"
SHUTTLE = "ttsky25a"
VAPWR, MIDRAIL = 3.3, 1.65

NSAMPLES = 4096
CAPTURES = 20
STIMULUS_HZ = 20_000.0   # 50 us period -- generous margin over a tens-of-ns edge

IN_CH, OUT_CH = 0, 1     # ua1 (drive + monitor) on 1+, ua2 (output) on 2+


def wiring_table(no_input_probe: bool = False) -> str:
    pads = pads_in_use(SwitchConfig(bits=unpack(BITSTREAM)), SHUTTLE, PROJECT)
    rows = [("W1 (yellow)", pads["ua1"], "inverter input, design ua1 -- the edge being driven")]
    if no_input_probe:
        rows.append(("", "", "leave 1+ DISCONNECTED -- its ~24 pF loads ua1 down,"))
        rows.append(("", "", "see this script's docstring on --no-input-probe"))
    else:
        rows.append(("1+ (orange)", pads["ua1"], "the same node, so the stimulus is measured where it"))
        rows.append(("", "", "arrives rather than where it is commanded"))
    rows.append(("2+ (blue)", pads["ua2"], "inverter output, design ua2 -- the edge being timed"))
    rows.append(("1-, 2-, GND" if not no_input_probe else "2-, GND",
                 "gnd", "scope reference -- differential inputs"))
    out = ["\n  Wire the Analog Discovery to the demoboard like this:\n",
           "    AD3 lead      pad      signal",
           "    -----------   -----    ------------------------------------------"]
    for lead, pad, what in rows:
        out.append(f"    {lead:<13s} {pad:<8s} {what}")
    return "\n".join(out) + "\n\n" + format_analog_header(pads) + "\n"


def program_chip(port: str | None) -> None:
    """Upload the configuration through mosbius.program.program().

    Not `python3 -m mosbius.cli program` in a subprocess -- see
    tools/ad3/measure_inverter_ad3.py's program_chip() for why: the result
    dict's `ibias_set` field is read directly rather than string-matched out
    of the CLI's rendered warning.
    """
    config = SwitchConfig.from_bitstream(BITSTREAM)
    print("== loading the inverter onto the chip")
    try:
        result = program(config, project=PROJECT, port=port)
    except ProgramError as exc:
        raise SystemExit(f"programming failed -- nothing measured\n\n{exc}")
    warning = ibias_warning(result, config)
    if warning:
        print(warning)


def _smooth(values, k=9):
    out = []
    for i in range(len(values)):
        a, b = max(0, i - k // 2), min(len(values), i + k // 2 + 1)
        out.append(sum(values[a:b]) / (b - a))
    return out


def edge_10_90(values, dt, centre=None, half=200, rising=True):
    """10%-90% width of one transition near `centre`, in seconds.

    Same shape as `tools/ad3/measure_settling_ad3.py`'s `edge_10_90()`:
    restrict the search to a window around the trigger and smooth it first,
    or a first-crossing search over the whole buffer can find noise on the
    flat part instead of the edge. This circuit's swing is the full 3.3 V
    rail, much larger than diffamp's 80 mV, so it is far less exposed to
    that trap -- the window is kept anyway so the result is robust to
    whichever edge in the buffer happens to land nearest the trigger.
    """
    n = len(values)
    centre = n // 2 if centre is None else centre
    a, b = max(0, centre - half), min(n, centre + half)
    lo = statistics.median(values[max(0, a - 300):a] or values[:1])
    hi = statistics.median(values[b:b + 300] or values[-1:])
    if abs(hi - lo) < 0.5:
        return None
    seg = _smooth(values[a:b])
    t10 = ad3.crossing(seg, lo + 0.1 * (hi - lo), rising, dt)
    t90 = ad3.crossing(seg, lo + 0.9 * (hi - lo), rising, dt)
    return None if t10 is None or t90 is None else abs(t90 - t10)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", default=None)
    ap.add_argument("--no-program", action="store_true")
    ap.add_argument("--captures", type=int, default=CAPTURES)
    ap.add_argument("--no-input-probe", action="store_true",
                    help="drive ua1 without 1+ attached -- see docstring")
    args = ap.parse_args()
    channels = (OUT_CH,) if args.no_input_probe else (IN_CH, OUT_CH)

    if not args.no_program:
        program_chip(args.port)
    print(wiring_table(args.no_input_probe))
    input("  Press Enter once that is wired... ")

    with ad3.device() as handle:
        ad3.square_wave(handle, 0, 0.0, VAPWR, STIMULUS_HZ, symmetry=50.0)
        ad3.dwf.FDwfAnalogOutConfigure(handle, ad3.c_int(0), ad3.c_int(1))
        time.sleep(0.3)

        rate = ad3.max_rate(handle)
        dt = 1.0 / rate
        print(f"  driving ua1 0..{VAPWR:.1f} V at {STIMULUS_HZ / 1e3:.0f} kHz, "
              f"capturing at {rate / 1e6:.0f} MS/s ({dt * 1e9:.0f} ns/sample), "
              f"{NSAMPLES} samples, triggered on ua2 rising through {MIDRAIL} V"
              + (" (1+ disconnected)" if args.no_input_probe else "") + "\n")

        ad3.scope_setup_triggered(handle, rate, NSAMPLES, OUT_CH, MIDRAIL,
                                  rising=True, position=0.0, channels=channels)

        stim_edges, out_edges, trace = [], [], None
        for i in range(args.captures):
            got = ad3.capture_triggered(handle, NSAMPLES, channels=channels,
                                        tag=f"capture {i + 1}: ")
            if got is None:
                print(f"  capture {i + 1} never triggered -- skipping")
                continue
            trace = trace or got
            out = edge_10_90(got[OUT_CH], dt, rising=True)    # ua2 rises
            if out is not None:
                out_edges.append(out)
            if not args.no_input_probe:
                stim = edge_10_90(got[IN_CH], dt, rising=False)   # ua1 falls
                if stim is not None:
                    stim_edges.append(stim)

    if not out_edges:
        raise SystemExit(
            "no output edge could be timed.\n\n"
            "  Check the wiring above and that the chip still holds the bitstream\n"
            "  (re-run without --no-program). If ua1's own edge is also missing, the\n"
            "  trigger level or the wiring is the problem, not the timing math."
        )

    out_ns = [e * 1e9 for e in out_edges]
    stim_ns = [e * 1e9 for e in stim_edges]
    out_path = Path("build/inverter_silicon_edge_unloaded.json"
                    if args.no_input_probe else "build/inverter_silicon_edge.json")
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps({
        "rate": rate, "out_edge_ns": out_ns, "stim_edge_ns": stim_ns,
        "trace": ({"out": trace[OUT_CH]} if args.no_input_probe
                  else {"in": trace[IN_CH], "out": trace[OUT_CH]}) if trace else None,
    }))

    mean_out = statistics.mean(out_ns)
    sd_out = statistics.pstdev(out_ns) if len(out_ns) > 1 else 0.0
    print(f"  ua2, 10%-90% rise    {mean_out:6.2f} ns   "
          f"(sd {sd_out:.2f} ns over {len(out_ns)} captures)")
    if args.no_input_probe:
        # 95.43 ns: this same measurement, 1+ attached, from
        # tools/ad3/measure_inverter_edge_ad3.py on 2026-08-31.
        baseline = 95.43
        shift = abs(mean_out - baseline) / baseline * 100
        print(f"\n  With 1+ attached (2026-08-31): {baseline:.2f} ns. "
              f"{shift:.0f}% {'higher' if mean_out > baseline else 'lower'} here.")
        if shift < 10:
            print("  Barely moved -- the output edge is dominated by the circuit, not by\n"
                  "  1+'s loading on ua1 or by the stimulus. This number is trustworthy in\n"
                  "  a way the probed one was not.")
        else:
            print("  Moved substantially -- ua1's own edge still matters to this result,\n"
                  "  which means we still don't have a clean, isolated measurement of ua2's\n"
                  "  own rise time.")
    if stim_ns:
        mean_stim = statistics.mean(stim_ns)
        margin = mean_out / mean_stim if mean_stim else None
        print(f"  ua1, 10%-90% fall    {mean_stim:6.2f} ns   (the generator's own edge)")
        if margin:
            if margin >= 3:
                verdict = "comfortably clear of the generator -- trust this number"
            elif margin >= 1.5:
                verdict = ("not comfortably clear of the generator -- treat this as an "
                           "upper bound, not a clean measurement")
            else:
                verdict = "close to the generator's own edge -- this times the AD3 more than the chip"
            print(f"  margin (output / stimulus)   {margin:.1f}x   -- {verdict}")
    print("\n  Sim comparison needs the AD3's own loading, not the sheet's default:\n"
          "  8.16 ns (as drawn) and 24.63 ns (as routed) are both at rprobe=10meg\n"
          "  cprobe=10p, while the AD3 presents rprobe=1meg cprobe=24p on this pin.\n"
          "  Re-run tb_inverter.sch's .tran deck with those params before comparing\n"
          "  this number against either one.")
    print(f"\n== {len(out_edges)} usable captures written to {out_path}")


if __name__ == "__main__":
    main()
