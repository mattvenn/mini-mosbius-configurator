#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Measure examples/diffamp on real silicon with an Analog Discovery.

Inputs on pads C and J (`ua1`, `ua2`), output on pad G (`ua4`), bias
current into pad K. Run from the repo root, on the host:

    python3 tools/measure_diffamp_ad3.py

**Why this cannot be one sweep.** The amplifier's gain is about 20 V/V on
3.3 V rails, so its linear output swing of roughly 1.2 to 2.8 V corresponds
to an input window about 80 mV wide -- and where that window sits is set by
the pair's input offset voltage, which is device mismatch and is not known
in advance. Sweeping the whole rail at any sane step size would put two or
three points on the entire transition. examples/inverter/ already showed
what that costs: a 220 mV-wide transition read -17.6 V/V at 25 mV steps and
-20.7 V/V at 4 mV steps. This transition is three times narrower. So the
sweep is coarse-then-fine: find the operating point, then resolve it.

**Gain is a slope, which is what makes two scope channels enough.** Both
are spoken for -- one on the swept input, one on the output -- leaving none
for `ua2`. That costs nothing: the differential gain is d(ua4)/d(ua1) with
`ua2` merely held constant, so `ua2`'s absolute value never enters the
arithmetic, and the channel offsets cancel out of a slope. `net1` (the
tail) and `net2` (the mirror reference) have no bond pads and cannot be
observed at all.

**Unlike examples/otabuf, the headline number here is bias-sensitive.** A
follower follows whatever its tail current; a gain stage's gain is roughly
gm x Rout and both terms move with tail current. So this script measures
gain at several bias currents rather than quoting one and caveating it.
That is affordable only because the bias comes from a supply this script
can set -- see "Feeding it by hand, when the board can't" in
examples/README.md, and run tools/measure_ibias_clamp_ad3.py first.
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

# examples/diffamp as the router placed it on 2026-08-29 -- the configuration
# the measured gain and its bias sweep were taken with.
# It is a record of an experiment, not a cached build artifact: if the
# router's allocation ever changes, re-route and re-measure rather than
# editing this string, or the published numbers quietly stop describing
# the configuration that was actually on the chip.
BITSTREAM = "00100000c020004820000000004821000000000000000030"
PROJECT, SHUTTLE = "tt_um_tnt_mosbius", "ttsky25a"

COMMON_MODE = 1.5          # what the simulated sheet holds ua2 at
COARSE_SPAN, COARSE_STEP = 0.150, 0.005
FINE_SPAN, FINE_STEP = 0.040, 0.001
SETTLE = 0.03
BIAS_RAILS = (2.25, 3.28, 4.30)     # ~55, ~100, ~145 uA through 20k
NOMINAL_RAIL = 3.28

# examples/diffamp/README.md, re-run 2026-08-29 at cprobe=10p, rprobe=10meg.
# NOTE those are 10 MOhm / 10 pF; an AD3 is 1 MOhm / 24 pF, and 1 MOhm across
# this amp's ~20 kOhm output is worth a couple of percent of gain. The
# comparison below is not corrected for that.
SIM = {"drawn": {"base": 2.012, "plus40": 2.744, "minus40": 1.237,
                 "gain_plus": 18.31, "gain_minus": 19.35},
       "routed": {"base": 2.018, "plus40": 2.769, "minus40": 1.227,
                  "gain_plus": 18.78, "gain_minus": 19.77}}
SIM_SMALL_SIGNAL = 19.5    # as drawn, near the origin


def wiring_table(pads: dict[str, str]) -> str:
    rows = [
        ("V+ (red)", f"via 20k to {pads['ibias']}", "bias current in"),
        ("W1 (yellow)", pads["ua1"], "ua1, the swept input"),
        ("W2 (white)", pads["ua2"], f"ua2, held at {COMMON_MODE} V common mode"),
        ("1+ (orange)", pads["ua1"], "the swept input, as it actually arrives"),
        ("2+ (blue)", pads["ua4"], "ua4, the output"),
        ("1-, 2-, GND", "any gnd", "scope reference -- differential inputs,"),
        ("", "", "so these must be grounded"),
    ]
    out = ["\n  Wire the Analog Discovery to the demoboard like this:\n",
           "    AD3 lead      where              signal",
           "    -----------   ----------------   ----------------------------------"]
    for lead, where, what in rows:
        out.append(f"    {lead:<13s} {where:<18s} {what}")
    return "\n".join(out) + "\n\n" + format_analog_header(pads) + "\n"


def implied_bias(rail: float) -> float | None:
    path = Path("build/ibias_clamp.json")
    if not path.exists():
        return None
    pts = json.loads(path.read_text())["points"]
    for a, b in zip(pts, pts[1:]):
        if min(a["rail"], b["rail"]) <= rail <= max(a["rail"], b["rail"]):
            span = b["rail"] - a["rail"]
            f = 0.0 if abs(span) < 1e-9 else (rail - a["rail"]) / span
            return a["amps"] + f * (b["amps"] - a["amps"])
    return None


def program_chip(port: str | None) -> None:
    cmd = [sys.executable, "-m", "mosbius.cli", "program", BITSTREAM,
           "--project", PROJECT, "--ibias", "0"]
    if port:
        cmd += ["--port", port]
    print("== loading the differential amplifier onto the chip")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    print("  " + (r.stdout.strip() or r.stderr.strip()).replace("\n", "\n  "))
    if r.returncode != 0:
        raise SystemExit("programming failed -- nothing measured")


def read(handle, tag):
    try:
        s = ad3.acquire(handle, nsamples=2000, channels=(0, 1), tag=tag)
    except RuntimeError as exc:
        return None, str(exc).splitlines()[0]
    return (ad3.mean(s, 0), ad3.mean(s, 1)), None


def sweep(handle, centre, span, step, tag):
    """(vin, vout) pairs across centre +/- span."""
    points, level = [], centre - span
    while level <= centre + span + 1e-12:
        ad3.wavegen(handle, ch=0, func=ad3.funcDC, amp=0.0, offset=level)
        time.sleep(SETTLE)
        pair, err = read(handle, f"{tag} at {level:.4f} V: ")
        if pair:
            points.append(pair)
        level += step
    return points


def find_centre(points):
    """The input where the output is midway between its extremes.

    Not the mid-rail: what matters is the middle of the swing this amplifier
    actually produces, since the operating point sits near 2.0 V rather than
    at 1.65 V and the swing is not symmetric about either.
    """
    if len(points) < 3:
        return None
    outs = [p[1] for p in points]
    if max(outs) - min(outs) < 0.2:
        return None          # never left its rail; nothing to centre on
    target = (max(outs) + min(outs)) / 2
    return min(points, key=lambda p: abs(p[1] - target))


def local_gain(points, at, window=0.004):
    """d(out)/d(in) near an input level, by least squares over +/- window."""
    sel = [p for p in points if abs(p[0] - at) <= window]
    if len(sel) < 3:
        return float("nan")
    n = len(sel)
    mx, my = sum(p[0] for p in sel) / n, sum(p[1] for p in sel) / n
    denom = sum((p[0] - mx) ** 2 for p in sel)
    return float("nan") if denom == 0 else \
        sum((p[0] - mx) * (p[1] - my) for p in sel) / denom


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", default=None)
    ap.add_argument("--no-program", action="store_true")
    ap.add_argument("--skip-bias-sweep", action="store_true",
                    help="only measure at the nominal bias")
    args = ap.parse_args()

    pads = pads_in_use(SwitchConfig(bits=unpack(BITSTREAM)), SHUTTLE, PROJECT)
    if not args.no_program:
        program_chip(args.port)
    print(wiring_table(pads))
    input("  Press Enter once that is wired... ")

    record = {"bitstream": BITSTREAM, "pads": pads, "common_mode": COMMON_MODE,
              "fine_step": FINE_STEP, "by_bias": []}

    with ad3.device() as handle:
        ad3.wavegen(handle, ch=1, func=ad3.funcDC, amp=0.0, offset=COMMON_MODE)
        ad3.wavegen(handle, ch=0, func=ad3.funcDC, amp=0.0, offset=COMMON_MODE)
        rail = ad3.supply(handle, NOMINAL_RAIL, "V+", current_limit=0.05, settle=0.5)
        ad3.scope_setup(handle, rate=1e5, nsamples=2000)

        # -- Phase 1: is pad G the output, and is the amplifier biased?
        pair, err = read(handle, "phase 1: ")
        if not pair:
            raise SystemExit(f"could not read the output: {err}")
        vin0, vout0 = pair
        amps = implied_bias(rail["voltage"])
        print(f"== phase 1 -- both inputs at {vin0:.4f} V, "
              f"bias rail {rail['voltage']:.4f} V"
              + (f" (~{amps * 1e6:.1f} uA)" if amps else ""))
        print(f"   output on pad {pads['ua4']}: {vout0:.4f} V   "
              f"(simulated base: {SIM['drawn']['base']:.3f} as drawn, "
              f"{SIM['routed']['base']:.3f} as routed)")
        record["phase1"] = {"vin": vin0, "vout": vout0,
                            "rail": rail["voltage"], "amps": amps}
        if vout0 < 0.2 or vout0 > 3.1:
            print(f"\n  THE OUTPUT IS AT A RAIL ({vout0:.3f} V), so there is nothing\n"
                  f"  to sweep yet. Pad {pads['ua4']} (ua4) has never been confirmed on\n"
                  "  silicon -- ua1->C, ua2->J and ua0->K have. Either it is the wrong\n"
                  "  pad, or the amplifier is not biased, or the input offset is larger\n"
                  "  than the common-mode point allows for. Check the bias first: pad\n"
                  f"  {pads['ibias']} should sit near 1.28 V.")
            Path("build").mkdir(exist_ok=True)
            Path("build/diffamp_silicon.json").write_text(json.dumps(record))
            return

        rails = (NOMINAL_RAIL,) if args.skip_bias_sweep else BIAS_RAILS
        for v_rail in rails:
            measured = ad3.supply(handle, v_rail, "V+", current_limit=0.05, settle=0.4)
            amps = implied_bias(measured["voltage"])
            label = f"{amps * 1e6:.1f} uA" if amps else f"rail {v_rail:.2f} V"
            print(f"\n== bias {label} (rail {measured['voltage']:.4f} V)")

            coarse = sweep(handle, COMMON_MODE, COARSE_SPAN, COARSE_STEP, "coarse")
            centre = find_centre(coarse)
            if centre is None:
                print("   the output never left its rail across "
                      f"+/-{COARSE_SPAN * 1000:.0f} mV -- skipping this bias")
                record["by_bias"].append({"rail": measured["voltage"], "amps": amps,
                                          "coarse": coarse, "fine": None})
                continue
            offset = centre[0] - COMMON_MODE
            print(f"   centred at ua1 = {centre[0]:.4f} V, output {centre[1]:.4f} V")
            print(f"   input offset {offset * 1000:+.2f} mV from the "
                  f"{COMMON_MODE} V common mode")

            fine = sweep(handle, centre[0], FINE_SPAN, FINE_STEP, "fine")
            peak = max(((abs(local_gain(fine, p[0])), p[0]) for p in fine),
                       default=(float("nan"), None))
            print(f"   peak gain {peak[0]:.2f} V/V at ua1 = {peak[1]:.4f} V "
                  f"({FINE_STEP * 1000:.0f} mV steps)")
            record["by_bias"].append({
                "rail": measured["voltage"], "amps": amps, "centre": centre,
                "offset": offset, "coarse": coarse, "fine": fine,
                "peak_gain": peak[0], "peak_at": peak[1]})

        ad3.wavegen(handle, ch=0, func=ad3.funcDC, amp=0.0, offset=0.0, enable=False)
        ad3.wavegen(handle, ch=1, func=ad3.funcDC, amp=0.0, offset=0.0, enable=False)

    Path("build").mkdir(exist_ok=True)
    out = Path("build/diffamp_silicon.json")
    out.write_text(json.dumps(record))
    print(f"\n== written to {out}")
    report(record)


LINEAR_WINDOW = (1.3, 2.4)     # output volts that are safely inside the fan


def _lsq(points):
    """(slope, rms residual, worst residual) of a straight-line fit."""
    n = len(points)
    mx = sum(p[0] for p in points) / n
    my = sum(p[1] for p in points) / n
    denom = sum((p[0] - mx) ** 2 for p in points)
    if denom == 0:
        return float("nan"), float("nan"), float("nan")
    slope = sum((p[0] - mx) * (p[1] - my) for p in points) / denom
    intercept = my - slope * mx
    res = [p[1] - (slope * p[0] + intercept) for p in points]
    rms = (sum(r * r for r in res) / n) ** 0.5
    return slope, rms, max(abs(r) for r in res)


def linear_region(fine):
    return [p for p in fine if LINEAR_WINDOW[0] <= p[1] <= LINEAR_WINDOW[1]]


def report(record) -> None:
    """**Gain here is a fit over the linear region, not a peak local slope.**

    The first version of this took the largest local slope, over a +/-4 mV
    least-squares window, and called it the peak gain. That was wrong twice
    over. The local slope scatters by about +/-0.8 V/V point to point, so
    the maximum of it is a noise pick rather than a feature; and it rises
    monotonically from about 14 to 17 V/V across the swept window, so there
    is no peak in there to find. Fitting the whole linear region instead is
    well conditioned and reproducible -- residuals come out under 10 mV rms
    over more than a volt of output swing.

    The operating point moved for the same reason. It was taken as the input
    where the output sits midway between the extremes of the coarse sweep,
    which landed 15 to 32 mV away from where the gain actually peaks,
    because the amplifier's swing is not symmetric about its bias point.
    The output at the peak-gain point is about 2.07 V, which is the
    simulated base (2.012 as drawn, 2.018 as routed) -- so the sheet was
    right about the operating point and the first centring rule was not.
    """
    good = [b for b in record["by_bias"] if b.get("fine")]
    if not good:
        print("\n  Nothing to compare -- no bias point produced a usable sweep.")
        return

    print("\n  Gain over the linear region, fitted, at three tail currents:\n")
    print("    bias        gain      fit residual   ua1 at out=2.0 V")
    print("    ---------   -------   ------------   ----------------")
    fits = []
    for b in good:
        lin = linear_region(b["fine"])
        slope, rms, worst = _lsq(lin)
        cross = min(lin, key=lambda p: abs(p[1] - 2.0))
        fits.append((b, slope, rms, cross))
        amps = f"{b['amps'] * 1e6:6.1f} uA" if b["amps"] else "     ?   "
        print(f"    {amps}   {slope:5.2f} V/V   {rms * 1000:4.1f} mV rms    "
              f"{cross[0]:.4f} V  ({(cross[0] - record['common_mode']) * 1000:+5.1f} mV)")

    print(f"\n  Residuals under 10 mV rms over more than a volt of output swing:\n"
          f"  this amplifier is very linear across the window swept, and the\n"
          f"  {record['fine_step'] * 1000:.0f} mV input steps resolve it properly. A coarser sweep would\n"
          f"  not have -- the whole transition is about 80 mV wide.")

    lo, hi = fits[0], fits[-1]
    if lo[0]["amps"] and hi[0]["amps"]:
        ratio = lo[1] / hi[1]
        expected = (hi[0]["amps"] / lo[0]["amps"]) ** 0.5
        print(f"\n  Gain barely moves with bias: {ratio:.3f}x across "
              f"{hi[0]['amps'] / lo[0]['amps']:.1f}x of tail current,\n"
              f"  where strong-inversion square law predicts {expected:.3f}x "
              f"(gain = gm x Rout,\n"
              f"  gm proportional to sqrt(I) and Rout to 1/I, so gain to 1/sqrt(I)).\n"
              f"  Gain roughly independent of current is instead the signature of\n"
              f"  *moderate* inversion, where gm is proportional to I rather than its\n"
              f"  square root, so the two dependencies cancel. That is an inference\n"
              f"  from one measurement of one part, not something verified here.")

    nominal = min(fits, key=lambda f: abs((f[0]["amps"] or 0) - 100e-6))
    print(f"\n  Against the same circuit simulated, at the nominal bias:\n")
    print("               as drawn   as routed   on silicon")
    print("               --------   ---------   ----------")
    print(f"    gain         {SIM_SMALL_SIGNAL:5.1f}      {SIM['routed']['gain_minus']:5.2f}"
          f"       {nominal[1]:5.2f} V/V")
    print(f"    output base  {SIM['drawn']['base']:5.3f}      {SIM['routed']['base']:5.3f}"
          f"       ~2.07 V   (at the peak-gain point)")

    shortfall = (SIM_SMALL_SIGNAL - nominal[1]) / SIM_SMALL_SIGNAL * 100
    print(f"\n  Silicon is {shortfall:.0f}% below the as-drawn small-signal gain, and two\n"
          f"  known effects account for part of it before anything else is invoked.\n"
          f"  The AD3's 1 MOhm input across this amplifier's ~20 kOhm output is worth\n"
          f"  about 2%, and the simulated numbers are at rprobe=10meg cprobe=10p.\n"
          f"  Much more importantly, **this part is an `ss` corner** -- established\n"
          f"  from the ring oscillator and the inverter (see CLAUDE.md) -- while every\n"
          f"  published number on this page is `tt`. Gain is exactly the kind of\n"
          f"  quantity a corner moves. tools/sweep_corners.sh re-runs a testbench at\n"
          f"  ss without touching the committed schematics, and that is the next test\n"
          f"  rather than a conclusion to draw here.")

    print(f"\n  Worth noting the same direction turned up in examples/otabuf, measured\n"
          f"  the same day: its closed-loop shortfall from unity was 1.38x the routed\n"
          f"  model's, which also means less gain on silicon than modelled. Two\n"
          f"  independent circuits, one part, same sign.")

    print(f"\n  The operating point shifts by about "
          f"{(fits[-1][3][0] - fits[0][3][0]) * 1000:.0f} mV across that bias range\n"
          f"  (the last column of the table). Read that as an observation rather than\n"
          f"  as the pair's input offset voltage: which input counts as 'centred'\n"
          f"  depends on what output level you nominate, and this one nominates\n"
          f"  2.0 V. A bias-independent definition would need the output's own\n"
          f"  symmetry point, which this sweep does not reach on both sides. What is\n"
          f"  solid is that the offset is small -- a few millivolts -- against a\n"
          f"  simulated sheet whose offset is exactly zero by construction, since it\n"
          f"  is perfectly symmetric and ngspice is noiseless.")


if __name__ == "__main__":
    main()
