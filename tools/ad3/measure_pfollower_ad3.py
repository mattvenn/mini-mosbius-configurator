#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Measure a one-shot PMOS source follower on real silicon (Andrew Kang's
part only), to check TODO.md Sec 2's PMOS-bulk-tie claim before any fix is
written.

Not a committed example -- the schematic lives in build/pfollower/
(build/pfollower/pfollower.sch, build/pfollower/tb_pfollower.sch), which is
gitignored, so re-run tools/regenerate_routed.sh yourself if build/ has been
cleaned:

    MOSBIUS_PROJECT=tt_um_mosbius sh tools/regenerate_routed.sh build/pfollower/pfollower.sch

Then run this on the host, with a demoboard and an Analog Discovery:

    python3 tools/ad3/measure_pfollower_ad3.py

**What this checks.** xschem/mosbius_lib/mosbius_pmos.sym hard-wires every
PMOS's bulk to VAPWR (template="... b=VAPWR"). On Andrew Kang's part, the
real silicon ties a PMOS's bulk to its own source instead (diff_n.sch's
M1/M2 do the same for the NMOS pair, on `itail` -- see CLAUDE.md's
2026-09-10 entry). That is invisible whenever a PMOS's source sits on a
rail, which is every existing example, but this follower's source (ua2)
moves with the input (ua1) -- exactly the case CLAUDE.md flags as "about
20% low".

A standalone 3-device SPICE check (bulk on VAPWR vs bulk on the device's
own source, otherwise identical) got 0.794 vs 0.975 V/V -- 18.5% low, right
in line with the extrapolation. Simulating this actual follower circuit
both ways landed the same direction: 0.746 V/V as drawn (ideal library,
bulk on VAPWR) against 0.918 V/V as routed (`mosbius simulate`, built from
Andrew Kang's own extracted device library, which already carries the real
bulk tie) -- an 18.7% gap, entirely from the switch matrix's own device
models, not from anything this script measures. That is strong evidence on
its own; this script is the last check, on the actual part.

**What "on silicon matches as-routed" would mean.** If the real chip's
gain lands near 0.918 V/V (not 0.746), that confirms `mosbius simulate`'s
switch-matrix models already have this right -- because they come from
Andrew Kang's own extracted device library, not from `mosbius_pmos` -- and
the only thing to fix is the *ideal* library's default bulk tie. If it
lands near 0.746, or somewhere between, the picture is more complicated,
and the TODO.md item needs rethinking before any fix is written.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ad3  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from mosbius.chips import KANG  # noqa: E402
from mosbius.model import SwitchConfig  # noqa: E402
from mosbius.program import (  # noqa: E402
    ProgramError,
    ibias_warning,
    program,
)
from mosbius.pads import format_analog_header, pads_in_use  # noqa: E402

SHUTTLE = "ttsky25a"
PROJECT = "tt_um_mosbius"

# build/pfollower/pfollower.sch routed for tt_um_mosbius on 2026-09-10 --
# mosbius_pmos M1 (g=ua1, d=VGND, s=ua2) biased by mosbius_psource PS1
# (ratio=2, out=ua2), one mosbius_bias generator. Re-route rather than edit
# this if the router's allocation for this part ever changes.
BITSTREAM = "0000000402080000002080000000000000021200000000000"

# The board's own onboard current source is NOT what this circuit is
# biased with -- fed by hand instead, the same way
# tools/ad3/measure_diffamp_ad3.py and measure_pdiffamp_ad3.py do it (see
# their program_chip(): both pass ibias=0 and drive V+ through 20k into the
# ibias pad themselves). Copying measure_inverter_ad3.py's pattern instead
# (onboard default, no external supply) was this script's first version,
# and it silently measured an unbiased chip -- a plain inverter draws no
# bias-referenced current at all, so that script never actually exercises
# whether the onboard source delivers current; a follower's psource does.
# First hit 2026-09-10: output pinned near 0 V across the whole sweep,
# gain 0.000 V/V, indistinguishable at a glance from "the psource just has
# no drive" -- which is exactly what it was.
NOMINAL_RAIL = 3.28   # ~100 uA through 20k -> ~200 uA at the follower (ratio=2)

# tb_pfollower.sch, DC sweep, chord from vin=1.5 to vin=1.7 (0.2 V), at the
# default ibias_amps=100u (-> 200 uA at ratio=2), rprobe=10meg cprobe=10p.
SIM = {
    "drawn": {"vout_1_6": 2.906, "gain": 0.746},
    "routed": {"vout_1_6": 2.824, "gain": 0.918},
}

VIN_LO, VIN_HI, STEP = 1.0, 2.3, 0.025
CHORD_LO, CHORD_HI = 1.5, 1.7


def wiring_table(pads: dict[str, str]) -> str:
    rows = [
        ("V+ (red)", f"via 20k to {pads['ibias']}", "bias current in"),
        ("W1 (yellow)", pads["ua1"], "follower input, design ua1 (M1's gate)"),
        ("1+ (orange)", pads["ua1"], "the same node, monitors the drive"),
        ("2+ (blue)", pads["ua2"], "follower output, design ua2 (M1's source)"),
        ("1-, 2-, GND", "any gnd", "scope reference -- differential inputs,"),
        ("", "", "so these must be grounded or every reading is wrong"),
    ]
    out = ["\n  Wire the Analog Discovery to the demoboard like this:\n",
           "    AD3 lead      where          signal",
           "    -----------   ------------   ------------------------------------------"]
    for lead, pad, what in rows:
        out.append(f"    {lead:<13s} {pad:<14s} {what}")
    return "\n".join(out) + "\n\n" + format_analog_header(pads) + "\n"


def program_chip(bitstream: str, port: str | None) -> None:
    """Upload the configuration through mosbius.program.program().

    Not `python3 -m mosbius.cli program` in a subprocess -- see
    tools/ad3/measure_inverter_ad3.py's program_chip() for why: the result
    dict's `ibias_set` field is checked directly rather than string-matched
    out of the CLI's English.
    """
    config = SwitchConfig.from_bitstream(bitstream, chip=KANG, ibias=0)
    print(f"== loading the PMOS follower onto the chip ({PROJECT})")
    try:
        result = program(config, project=PROJECT, port=port)
    except ProgramError as exc:
        raise SystemExit(f"programming failed -- nothing measured\n\n{exc}")
    warning = ibias_warning(result, config)
    if warning:
        print(warning)


def sweep(handle) -> list[tuple[float, float]]:
    ad3.scope_setup(handle, rate=1e5, nsamples=4000)
    points, level = [], VIN_LO
    while level <= VIN_HI + 1e-9:
        ad3.wavegen(handle, ch=0, func=ad3.funcDC, amp=0.0, offset=level)
        time.sleep(0.03)
        samples = ad3.acquire(handle, nsamples=4000, tag=f"at {level:.3f} V drive: ")
        points.append((ad3.mean(samples, 0), ad3.mean(samples, 1)))
        level += STEP
    ad3.wavegen(handle, ch=0, func=ad3.funcDC, amp=0.0, offset=0.0, enable=False)
    return points


def _lsq(points: list[tuple[float, float]]) -> tuple[float, float]:
    """(slope, rms residual) of a straight-line fit."""
    n = len(points)
    mx = sum(p[0] for p in points) / n
    my = sum(p[1] for p in points) / n
    denom = sum((p[0] - mx) ** 2 for p in points)
    if denom == 0:
        return float("nan"), float("nan")
    slope = sum((p[0] - mx) * (p[1] - my) for p in points) / denom
    intercept = my - slope * mx
    res = [p[1] - (slope * p[0] + intercept) for p in points]
    rms = (sum(r * r for r in res) / n) ** 0.5
    return slope, rms


def report(points: list[tuple[float, float]]) -> None:
    chord = [p for p in points if CHORD_LO - 1e-9 <= p[0] <= CHORD_HI + 1e-9]
    at_1_6 = min(points, key=lambda p: abs(p[0] - 1.6))
    slope, rms = _lsq(points)
    chord_slope, chord_rms = _lsq(chord) if len(chord) >= 3 else (float("nan"), float("nan"))

    print(f"\n  Output at ua1=1.6 V: {at_1_6[1]:.4f} V  "
          f"(simulated: {SIM['drawn']['vout_1_6']:.3f} as drawn, "
          f"{SIM['routed']['vout_1_6']:.3f} as routed)")
    print(f"\n  Gain, {CHORD_LO}-{CHORD_HI} V chord (0.2 V, matching the simulated "
          f"sheet): {chord_slope:.3f} V/V  ({chord_rms * 1000:.1f} mV rms)")
    print(f"  Gain, whole {VIN_LO}-{VIN_HI} V sweep, fitted: "
          f"{slope:.3f} V/V  ({rms * 1000:.1f} mV rms)")

    print("\n  Against the same circuit simulated:\n")
    print("               as drawn   as routed   on silicon")
    print("               --------   ---------   ----------")
    print(f"    gain         {SIM['drawn']['gain']:.3f}      {SIM['routed']['gain']:.3f}"
          f"       {chord_slope:.3f} V/V")

    drawn_gap = abs(chord_slope - SIM["drawn"]["gain"])
    routed_gap = abs(chord_slope - SIM["routed"]["gain"])
    print(f"\n  Silicon sits {drawn_gap:.3f} V/V from the as-drawn number "
          f"(bulk hard-wired to VAPWR)\n  and {routed_gap:.3f} V/V from the as-routed number "
          f"(bulk on the real device's\n  own source, via Andrew Kang's extracted device library).")
    if routed_gap < drawn_gap:
        print("\n  Closer to AS ROUTED: the bulk-tie difference is real on this part, and\n"
              "  the fix belongs in the ideal library (mosbius_pmos), not in\n"
              "  `mosbius simulate`'s switch-matrix models, which already have it right.")
    elif drawn_gap < routed_gap:
        print("\n  Closer to AS DRAWN: something in this picture is wrong -- either the\n"
              "  bulk-tie reading of diff_n.sch/nmos_prog.sch/pmos_prog.sch, this test\n"
              "  circuit's own bias point, or the AD3 measurement. Don't write the fix\n"
              "  yet; re-check the schematics and the sweep before concluding anything.")
    else:
        print("\n  Roughly equidistant from both -- not conclusive either way. Check the\n"
              "  fit residual above before trusting this; a wide sweep window can pick\n"
              "  up compression near a rail and flatten the fitted slope.")

    print("\n  An uncalibrated Analog Discovery carries tens of mV of offset per\n"
          "  channel; the gain survives it (a ratio of differences, offsets cancel)\n"
          "  but run WaveForms' calibration before trusting the absolute levels.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", default=None)
    ap.add_argument("--no-program", action="store_true")
    args = ap.parse_args()

    pads = pads_in_use(SwitchConfig.from_bitstream(BITSTREAM, chip=KANG), SHUTTLE, PROJECT)
    if not args.no_program:
        program_chip(BITSTREAM, args.port)
    print(wiring_table(pads))
    input("  Press Enter once that is wired... ")

    with ad3.device() as handle:
        rail = ad3.supply(handle, NOMINAL_RAIL, "V+", current_limit=0.05, settle=0.5)
        print(f"== bias rail {rail['voltage']:.4f} V (~100 uA through 20k into "
              f"pad {pads['ibias']} -> ~200 uA at the follower)")

        # A quick check before spending a 53-point sweep on a chip that
        # turns out not to be biased -- exactly what happened the first
        # time this script ran (see NOMINAL_RAIL's comment above).
        ad3.scope_setup(handle, rate=1e5, nsamples=2000)
        ad3.wavegen(handle, ch=0, func=ad3.funcDC, amp=0.0, offset=1.6)
        time.sleep(0.05)
        probe = ad3.acquire(handle, nsamples=2000, tag="phase 1: ")
        vin0, vout0 = ad3.mean(probe, 0), ad3.mean(probe, 1)
        print(f"   phase 1 -- ua1 driven to {vin0:.4f} V, output {vout0:.4f} V  "
              f"(simulated: {SIM['drawn']['vout_1_6']:.3f} as drawn, "
              f"{SIM['routed']['vout_1_6']:.3f} as routed)")
        if vout0 < 0.3:
            print(f"\n  THE OUTPUT IS NEAR 0 V, so the follower is not biased. Check pad "
                  f"{pads['ibias']} directly\n  (multimeter or a spare AD3 channel) -- it "
                  f"should sit around 1.2-1.3 V. If it is also\n  near 0 V, the 20k resistor "
                  f"or the V+ connection is the thing to check first, not\n  this circuit.")
            ad3.wavegen(handle, ch=0, func=ad3.funcDC, amp=0.0, offset=0.0, enable=False)
            return

        points = sweep(handle)

    out = Path("build/pfollower_kang_silicon_dc.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(points))
    print(f"== {len(points)} points written to {out}")
    report(points)


if __name__ == "__main__":
    main()
