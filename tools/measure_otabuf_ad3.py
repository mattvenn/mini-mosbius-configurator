#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Measure examples/otabuf on real silicon with an Analog Discovery.

The OTA unity-gain follower: input on pad C (`ua1`), output on pad J
(`ua2`, which is also the feedback node). Run from the repo root, on the
host -- it needs USB for the demoboard:

    python3 tools/measure_otabuf_ad3.py

**This is the first example measured here that needs a bias current.** The
OTA's tail is a slave of the chip's bias reference, so with `ibias` unfed
the whole circuit has no operating point and the output sits whereever the
leakage puts it. On a demoboard with no bias circuit that current comes
from V+ through a series resistor into pad K -- see "Feeding it by hand" in
examples/README.md, and run tools/measure_ibias_clamp_ad3.py first to
confirm the pad and find the setting. This script sets V+ itself and reads
build/ibias_clamp.json, if it is there, to say what current that implies.

**What it measures, and why those things.** `tb_otabuf.sch` ramps the input
slowly from 0.2 to 3.1 V, because a follower tracking a slow ramp makes two
numbers fall out at once: output minus input is the loop's offset, and the
ends of the ramp are where the input common-mode range runs out. This
sweeps the same range in steps, holding each level until the output has
arrived, which is the same measurement by a different route.

Slew rate -- the sheet's third number -- is NOT measured here. It needs a
real edge, and ad3.wavegen() makes levels rather than edges (see its
docstring: a DC offset change is slewed over milliseconds and produces a
clean, plausible, entirely wrong ramp). That wants the triggered-capture
idiom in tools/measure_srlatch_edge_ad3.py, as its own script.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ad3  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mosbius.bitstream import unpack  # noqa: E402
from mosbius.model import SwitchConfig  # noqa: E402
from mosbius.pads import format_analog_header, pads_in_use  # noqa: E402

# examples/otabuf as the router placed it on 2026-08-29 -- the configuration
# the measured slew and its tail sweep were taken with.
# It is a record of an experiment, not a cached build artifact: if the
# router's allocation ever changes, re-route and re-measure rather than
# editing this string, or the published numbers quietly stop describing
# the configuration that was actually on the chip.
BITSTREAM = "404000000000000000000000000000000000000000850210"
PROJECT = "tt_um_tnt_mosbius"
SHUTTLE = "ttsky25a"

RAMP_LO, RAMP_HI, STEP = 0.2, 3.1, 0.025
SETTLE = 0.03
BIAS_RAIL = 3.28          # V+ for ~100 uA through 20k, from the clamp sweep
BIAS_RESISTOR = 20000.0

# examples/otabuf/README.md, measured 2026-08-28 at ibias=100u, tail=4.
SIM_OFFSETS = {1.00: (+30.2, +25.0), 1.65: (+8.6, +5.9), 2.50: (-31.7, -33.1)}
SIM_CMR = (0.85, 2.9)
TRACKING = 0.100          # |out - in| under this counts as following


def wiring_table(pads: dict[str, str]) -> str:
    rows = [
        ("V+ (red)", f"via 20k to {pads['ibias']}", f"bias current in, V+ = {BIAS_RAIL} V"),
        ("W1 (yellow)", pads["ua1"], "OTA + input -- the follower's input"),
        ("1+ (orange)", pads["ua1"], "the same node, monitors the drive"),
        ("2+ (blue)", pads["ua2"], "OTA - output, and the feedback node"),
        ("1-, 2-, GND", "any gnd", "scope reference -- the inputs are differential,"),
        ("", "", "so these must be grounded or every reading is wrong"),
    ]
    out = ["\n  Wire the Analog Discovery to the demoboard like this:\n",
           "    AD3 lead      where            signal",
           "    -----------   --------------   ---------------------------------------"]
    for lead, where, what in rows:
        out.append(f"    {lead:<13s} {where:<16s} {what}")
    out.append("")
    out.append(format_analog_header(pads))
    return "\n".join(out) + "\n"


def implied_bias(rail: float) -> str:
    """What the clamp sweep says this rail setting delivers, if it was run."""
    path = Path("build/ibias_clamp.json")
    if not path.exists():
        return ("  (run tools/measure_ibias_clamp_ad3.py to know what current this is)")
    data = json.loads(path.read_text())
    pts = data["points"]
    for a, b in zip(pts, pts[1:]):
        if min(a["rail"], b["rail"]) <= rail <= max(a["rail"], b["rail"]):
            span = b["rail"] - a["rail"]
            f = 0.0 if abs(span) < 1e-9 else (rail - a["rail"]) / span
            amps = a["amps"] + f * (b["amps"] - a["amps"])
            return (f"  bias about {amps * 1e6:.1f} uA, interpolated from "
                    f"{path} ({data['resistor'] / 1000:g}k into pad {data['pad']})")
    return f"  ({rail:.2f} V is outside the range {path} swept)"


def program_chip(port: str | None) -> None:
    cmd = [sys.executable, "-m", "mosbius.cli", "program", BITSTREAM,
           "--project", PROJECT, "--ibias", "0"]
    if port:
        cmd += ["--port", port]
    print("== loading the OTA follower onto the chip")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    print("  " + (result.stdout.strip() or result.stderr.strip()).replace("\n", "\n  "))
    if result.returncode != 0:
        raise SystemExit("programming failed -- nothing measured")


def sweep(handle) -> list[tuple[float, float]]:
    ad3.wavegen(handle, ch=0, func=ad3.funcDC, amp=0.0, offset=RAMP_LO)
    ad3.scope_setup(handle, rate=1e5, nsamples=4000)
    points, level = [], RAMP_LO
    while level <= RAMP_HI + 1e-9:
        ad3.wavegen(handle, ch=0, func=ad3.funcDC, amp=0.0, offset=level)
        time.sleep(SETTLE)
        try:
            samples = ad3.acquire(handle, nsamples=4000, tag=f"at {level:.3f} V drive: ")
        except RuntimeError as exc:
            # A follower pinned at a rail comes back perfectly flat, which is
            # a real result here rather than a bad range -- record the drive
            # and move on rather than losing the whole sweep to it.
            print(f"  (skipped {level:.3f} V: {str(exc).splitlines()[0]})")
            level += STEP
            continue
        points.append((ad3.mean(samples, 0), ad3.mean(samples, 1)))
        level += STEP
    ad3.wavegen(handle, ch=0, func=ad3.funcDC, amp=0.0, offset=0.0, enable=False)
    return points


def _local_slopes(points, half=2):
    """d(out)/d(in) at each point, by central difference over +/- `half`."""
    out = []
    for i in range(len(points)):
        a, b = points[max(0, i - half)], points[min(len(points) - 1, i + half)]
        span = b[0] - a[0]
        out.append(None if abs(span) < 1e-9 else (b[1] - a[1]) / span)
    return out


def _tracking_band(points):
    """The longest contiguous run where the output actually follows the input.

    **Nearness is not enough, and assuming it was gave a wrong answer once.**
    Below the input common-mode range the output does not follow -- it sits
    pinned at a floor, about 0.31 V on this part. The input ramps up through
    that floor, so output minus input sweeps through zero on the way past
    and stays small for a couple of hundred millivolts either side. A plain
    "is |out - in| small" test therefore marks the dead region as tracking,
    and so does adding contiguity, because the dead region and the live one
    join up. What separates them is the slope: a pinned output moves at
    about 0.02 V/V, a following one at 1.00. Two clues that the first
    version had it wrong -- the fitted slope over the "band" came out at
    0.96 rather than 1.00, and the lower edge sat *below* where the
    simulated one gives up, which is the wrong direction for silicon.
    """
    slopes = _local_slopes(points)
    best, run = [], []
    for (vin, vout), slope in zip(points, slopes):
        following = (abs(vout - vin) < TRACKING
                     and slope is not None and 0.8 <= slope <= 1.2)
        if following:
            run.append((vin, vout))
            if len(run) > len(best):
                best = run
        else:
            run = []
    return best


def report(points: list[tuple[float, float]]) -> None:
    if len(points) < 5:
        print("\n  Too few points survived to say anything. See the errors above.")
        return
    tracking = _tracking_band(points)

    print("\n  Offset (output minus input), against the same circuit simulated:\n")
    print("    input     as drawn   as routed   on silicon")
    print("    -------   --------   ---------   ----------")
    for target, (drawn, routed) in sorted(SIM_OFFSETS.items()):
        vin, vout = min(points, key=lambda p: abs(p[0] - target))
        print(f"    {target:.2f} V    {drawn:+6.1f} mV   {routed:+6.1f} mV   "
              f"{(vout - vin) * 1000:+7.1f} mV   (at {vin:.3f} V)")

    print("\n  Input common-mode range -- where the output follows at all:\n")
    if tracking:
        lo, hi = tracking[0][0], tracking[-1][0]
        print(f"    on silicon    {lo:.2f} V to {hi:.2f} V")
    else:
        lo = hi = None
        print("    on silicon    it never followed -- see the verdict below")
    print(f"    simulated     {SIM_CMR[0]:.2f} V to {SIM_CMR[1]:.2f} V "
          "(both branches, within 50 mV of each other)")

    if not tracking:
        print("\n  THE FOLLOWER IS NOT FOLLOWING. Before suspecting the routing,\n"
              "  check the bias: this is the first example here that needs one, and\n"
              "  with ibias unfed the OTA has no operating point and its output goes\n"
              "  wherever leakage puts it. Move scope 2+ to pad D (ua3) -- that is\n"
              "  the mirror node, and it says whether the OTA is biased at all.\n"
              "  A follower follows regardless of how much tail current it has, so\n"
              "  no tracking anywhere is a bias or a connection problem, not a\n"
              "  wrong bias value.")
        return

    span = [abs(vout - vin) for vin, vout in tracking]
    print(f"\n  Over that band the output stays within {max(span) * 1000:.1f} mV of the input.")

    # The slope is the number to trust here, and the offsets are not. Both
    # channels carry tens of millivolts of uncalibrated offset, and out minus
    # in carries their *difference* directly -- the same error that moved
    # examples/inverter's threshold by 44 mV. A slope is a ratio of
    # differences, one per channel, so a constant offset cancels out of it.
    lo, hi = _at(points, 1.00), _at(points, 2.50)
    two_point = 1.0 + ((hi[1] - hi[0]) - (lo[1] - lo[0])) / (hi[0] - lo[0])
    drawn = 1.0 + (SIM_OFFSETS[2.50][0] - SIM_OFFSETS[1.00][0]) / 1000 / 1.5
    routed = 1.0 + (SIM_OFFSETS[2.50][1] - SIM_OFFSETS[1.00][1]) / 1000 / 1.5
    print("\n  Closed-loop gain -- the slope, not the offset:\n")
    print("               as drawn   as routed   on silicon")
    print("               --------   ---------   ----------")
    print(f"    1.00-2.50 V   {drawn:.4f}     {routed:.4f}      {two_point:.4f}")
    print(f"    whole band       --          --      {_slope(tracking):.4f}"
          f"   ({tracking[0][0]:.2f}-{tracking[-1][0]:.2f} V)")
    print(f"\n  A follower's slope falls short of 1 by its own finite-gain error, so\n"
          f"  silicon's shortfall being {(1 - two_point) / (1 - routed):.2f}x the routed model's says the\n"
          f"  real OTA's open-loop gain is lower than modelled by about that factor.\n"
          f"  This is the trustworthy half of the measurement: a slope is a ratio of\n"
          f"  differences within each channel, so the tens of millivolts of\n"
          f"  uncalibrated offset each one carries cancels out of it.")
    print("\n  The offset column above does NOT survive that reasoning -- output\n"
          "  minus input carries the *difference* of the two channel offsets, which\n"
          "  on this instrument is the same tens of millivolts as the offsets being\n"
          "  measured. Calibrate (WaveForms -> Settings -> Device Manager ->\n"
          "  Calibrate) before quoting them; the sign change near 1.65 V is real,\n"
          "  the absolute values are not yet.")
    print("\n  A follower follows regardless of tail current, which is why this was\n"
          "  the right example to measure first with a hand-made bias: whether it\n"
          "  works at all does not depend on the one number that is least well\n"
          "  known. The gain error does -- loop gain scales with tail current -- so\n"
          "  read that against the bias this ran at, not as a property of the chip.")


def _at(points, target):
    """The measured (in, out) pair nearest a target input level."""
    return min(points, key=lambda p: abs(p[0] - target))


def _slope(tracking: list[tuple[float, float]]) -> float:
    n = len(tracking)
    mx = sum(p[0] for p in tracking) / n
    my = sum(p[1] for p in tracking) / n
    denom = sum((p[0] - mx) ** 2 for p in tracking)
    return 0.0 if denom == 0 else sum((p[0] - mx) * (p[1] - my) for p in tracking) / denom


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rail", type=float, default=BIAS_RAIL,
                        help=f"V+ feeding the bias resistor (default: {BIAS_RAIL})")
    parser.add_argument("--port", default=None, help="demoboard serial port")
    parser.add_argument("--no-program", action="store_true")
    args = parser.parse_args()

    pads = pads_in_use(SwitchConfig(bits=unpack(BITSTREAM)), SHUTTLE, PROJECT)
    if not args.no_program:
        program_chip(args.port)
    print(wiring_table(pads))

    with ad3.device() as handle:
        measured = ad3.supply(handle, args.rail, "V+", current_limit=0.05, settle=0.5)
        print(f"== bias rail set: asked {args.rail:.3f} V, "
              f"measured {measured['voltage']:.4f} V")
        print(implied_bias(measured["voltage"]))
        points = sweep(handle)

    out = Path("build/otabuf_silicon_dc.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(points))
    print(f"\n== {len(points)} points written to {out}")
    report(points)


if __name__ == "__main__":
    main()
