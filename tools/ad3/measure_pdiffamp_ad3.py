#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Measure examples/pdiffamp on real silicon with an Analog Discovery.

Inputs on pads C and J (`ua1`, `ua2`), output on pad G (`ua4`), bias
current into pad K -- the same four pads examples/diffamp uses, because it
is the same amplifier in the opposite polarity. Run from the repo root, on
the host:

    python3 tools/ad3/measure_pdiffamp_ad3.py

**First run on silicon 2026-08-29**: 17.82 V/V fitted at 99.4 uA against
21.22 as drawn, with a +18 mV input offset. The two lessons this script inherits from
tools/ad3/measure_diffamp_ad3.py, both learned the expensive way there, are
why the reported gain is a fit over the linear region rather than a peak
local slope (the peak local slope reads 19.6 V/V here, and is a noise
pick), and why the operating point is taken from the fit rather than from
the midpoint of the coarse sweep's extremes.

**Why this cannot be one sweep.** The amplifier's gain is about 21 V/V, so
its linear output swing corresponds to an input window well under 100 mV
wide -- and where that window sits is set by the pair's input offset
voltage, which is device mismatch and is not known in advance. So the
sweep is coarse-then-fine: find the operating point, then resolve it.

**What differs from the NMOS diff amp, at the bench.** The output sits one
NMOS load Vgs *above* VGND -- about 1.12 V simulated, where the diff amp's
sits about 2.0 V, one PMOS Vgs below VAPWR. So the output has less room
below it than above, and the linear window used for the fit is placed
accordingly. A reading near 0 V means the pad is wrong or the amplifier is
unbiased; it does not mean "low but working".

**Gain is a slope, which is what makes two scope channels enough.** Both
are spoken for -- one on the swept input, one on the output -- leaving none
for `ua2`. That costs nothing: the differential gain is d(ua4)/d(ua1) with
`ua2` merely held constant, so `ua2`'s absolute value never enters the
arithmetic, and the channel offsets cancel out of a slope. `net1` (the
tail) and `net2` (the mirror reference) have no bond pads and cannot be
observed at all.

**The headline number is bias-sensitive**, as it is for the NMOS pair: a
gain stage's gain is roughly gm x Rout and both terms move with tail
current, so this script measures at several bias currents rather than
quoting one and caveating it. That is affordable only because the bias
comes from a supply this script can set -- see "Feeding it by hand, when
the board can't" in examples/README.md, and run
tools/ad3/measure_ibias_clamp_ad3.py first.
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
from mosbius.bitstream import unpack  # noqa: E402
from mosbius.model import SwitchConfig  # noqa: E402
from mosbius.program import (  # noqa: E402
    ProgramError,
    ibias_warning,
    program,
)
from mosbius.pads import format_analog_header, pads_in_use  # noqa: E402

# examples/pdiffamp as the router placed it on 2026-08-29 -- the configuration
# the 17.82 V/V fit and the +18 mV input offset were measured with.
# It is a record of an experiment, not a cached build artifact: if the
# router's allocation ever changes, re-route and re-measure rather than
# editing this string, or the published numbers quietly stop describing
# the configuration that was actually on the chip.
BITSTREAM = "0c0000040000000000000120840000000820100800000030"
PROJECT, SHUTTLE = "tt_um_tnt_mosbius", "ttsky25a"

COMMON_MODE = 1.5          # what the simulated sheet holds ua2 at
COARSE_SPAN, COARSE_STEP = 0.150, 0.005
FINE_SPAN, FINE_STEP = 0.040, 0.001
SETTLE = 0.03
BIAS_RAILS = (2.25, 3.28, 4.30)     # ~55, ~100, ~145 uA through 20k
NOMINAL_RAIL = 3.28

# examples/pdiffamp/README.md, measured 2026-08-29 at cprobe=10p, rprobe=10meg.
# NOTE those are 10 MOhm / 10 pF; an AD3 is 1 MOhm / 24 pF, and 1 MOhm across
# this amp's output is worth a couple of percent of gain. The comparison
# below is not corrected for that.
SIM = {"drawn": {"base": 1.112, "plus10": 1.328, "minus10": 0.904,
                 "gain_plus": 21.60, "gain_minus": 20.84},
       "routed": {"base": 1.121, "plus10": 1.339, "minus10": 0.910,
                  "gain_plus": 21.82, "gain_minus": 21.11}}
SIM_SMALL_SIGNAL = 21.6    # as drawn, near the origin


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
    """Upload the configuration through mosbius.program.program().

    Not `python3 -m mosbius.cli program` in a subprocess. The result dict
    carries an `ibias_set` field saying whether the board actually
    delivered the bias current, and the CLI renders that as a paragraph of
    English on stderr; reading the field is not merely tidier, because
    string-matching that paragraph fails in the DANGEROUS direction -- a
    reworded warning reads as "this board has a current source", and the
    script would then measure an unbiased chip very carefully.
    tools/ad3/measure_currentsource_ad3.py has always done it this way.
    """
    config = SwitchConfig.from_bitstream(BITSTREAM, ibias=0)
    print("== loading the PMOS differential amplifier onto the chip")
    try:
        result = program(config, project=PROJECT, port=port)
    except ProgramError as exc:
        raise SystemExit(f"programming failed -- nothing measured\n\n{exc}")
    warning = ibias_warning(result, config)
    if warning:
        print(warning)


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
    actually produces, since the operating point sits near 1.12 V rather than
    at 1.65 V and the swing is not symmetric about either. This is only a
    starting point for the fine sweep -- report() takes the operating point
    from the peak-gain point instead, for the reason recorded there.
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
                  f"  to sweep yet. This amplifier's output belongs near 1.12 V, one\n"
                  f"  NMOS load Vgs above VGND, so a reading near 0 V is a rail and not\n"
                  f"  a low-but-working operating point. Either the amplifier is not\n"
                  f"  biased, or the input offset is larger than the common-mode point\n"
                  f"  allows for. Check the bias first: pad {pads['ibias']} should sit\n"
                  f"  near 1.28 V. Pad {pads['ua4']} (ua4) itself is confirmed --\n"
                  f"  examples/diffamp measured its output there on 2026-08-29.")
            Path("build").mkdir(exist_ok=True)
            Path("build/pdiffamp_silicon.json").write_text(json.dumps(record))
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
    out = Path("build/pdiffamp_silicon.json")
    out.write_text(json.dumps(record))
    print(f"\n== written to {out}")
    report(record)


LINEAR_WINDOW = (0.5, 1.8)     # output volts that are safely inside the fan


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

    Both rules below are inherited from tools/ad3/measure_diffamp_ad3.py, where
    each was got wrong first and cost an analysis pass.

    A local slope scatters by around +/-0.8 V/V point to point, so the
    maximum of it is a noise pick rather than a feature, and it drifts
    monotonically across the swept window, so there is no peak in there to
    find. Fitting the whole linear region instead is well conditioned and
    reproducible.

    And the operating point is the peak-gain point, not the input where the
    output sits midway between a coarse sweep's extremes: this amplifier's
    swing is not symmetric about its bias point, so those two differ by tens
    of millivolts, and the +/-N mV gain chords are measured *from* the
    centre, so a misplaced centre makes them spuriously asymmetric.
    """
    good = [b for b in record["by_bias"] if b.get("fine")]
    if not good:
        print("\n  Nothing to compare -- no bias point produced a usable sweep.")
        return

    print("\n  Gain over the linear region, fitted, at each tail current:\n")
    print("    bias        gain      fit residual   ua1 at out=1.1 V")
    print("    ---------   -------   ------------   ----------------")
    fits = []
    for b in good:
        lin = linear_region(b["fine"])
        if len(lin) < 3:
            continue
        slope, rms, worst = _lsq(lin)
        cross = min(lin, key=lambda p: abs(p[1] - 1.1))
        fits.append((b, slope, rms, cross))
        amps = f"{b['amps'] * 1e6:6.1f} uA" if b["amps"] else "     ?   "
        print(f"    {amps}   {slope:5.2f} V/V   {rms * 1000:4.1f} mV rms    "
              f"{cross[0]:.4f} V  ({(cross[0] - record['common_mode']) * 1000:+5.1f} mV)")
    if not fits:
        print("    no sweep put enough points inside "
              f"{LINEAR_WINDOW[0]}-{LINEAR_WINDOW[1]} V of output -- widen "
              "LINEAR_WINDOW or the sweep span")
        return

    print(f"\n  Check the residuals before trusting any of the above: this\n"
          f"  amplifier's whole transition is only about "
          f"{(LINEAR_WINDOW[1] - LINEAR_WINDOW[0]) / SIM_SMALL_SIGNAL * 1000:.0f} mV wide at the\n"
          f"  input, and the sweep resolves it in {record['fine_step'] * 1000:.0f} mV steps. A residual much\n"
          f"  above 10 mV rms means the fit is describing curvature rather than\n"
          f"  a slope, and the window needs narrowing.")

    if len(fits) > 1 and fits[0][0]["amps"] and fits[-1][0]["amps"]:
        lo, hi = fits[0], fits[-1]
        ratio = lo[1] / hi[1]
        expected = (hi[0]["amps"] / lo[0]["amps"]) ** 0.5
        print(f"\n  Gain against bias: {ratio:.3f}x across "
              f"{hi[0]['amps'] / lo[0]['amps']:.1f}x of tail current, where\n"
              f"  strong-inversion square law predicts {expected:.3f}x (gain = gm x Rout,\n"
              f"  gm proportional to sqrt(I) and Rout to 1/I, so gain to 1/sqrt(I)), and\n"
              f"  moderate inversion predicts roughly flat, since there gm goes as I and\n"
              f"  the two dependencies cancel. examples/diffamp measured 1.059x across\n"
              f"  2.6x on the NMOS pair, i.e. the flat answer; whether the PMOS pair\n"
              f"  agrees is one of the things this measurement is for.")

    nominal = min(fits, key=lambda f: abs((f[0]["amps"] or 0) - 100e-6))
    print(f"\n  Against the same circuit simulated, at the nominal bias:\n")
    print("               as drawn   as routed   on silicon")
    print("               --------   ---------   ----------")
    print(f"    gain         {SIM_SMALL_SIGNAL:5.1f}      {SIM['routed']['gain_plus']:5.2f}"
          f"       {nominal[1]:5.2f} V/V")
    print(f"    output base  {SIM['drawn']['base']:5.3f}      {SIM['routed']['base']:5.3f}"
          f"       {nominal[3][1]:5.3f} V   (at out=1.1 V, by construction)")
    print(f"    ua1 centre     1.500      1.500       {nominal[3][0]:.4f} V")

    shortfall = (SIM_SMALL_SIGNAL - nominal[1]) / SIM_SMALL_SIGNAL * 100
    print(f"\n  Silicon is {shortfall:+.0f}% from the as-drawn small-signal gain. Two known\n"
          f"  effects sit between the two before anything else is invoked. The AD3's\n"
          f"  1 MOhm input across this amplifier's output is worth a couple of\n"
          f"  percent, and the simulated numbers are at rprobe=10meg cprobe=10p.\n"
          f"  Much more importantly, **this part is an `ss` corner** -- established\n"
          f"  from the ring oscillator and the inverter (see CLAUDE.md) -- while every\n"
          f"  published number for this example is `tt`, and gain is exactly the kind\n"
          f"  of quantity a corner moves. tools/sweep_corners.sh re-runs a testbench\n"
          f"  at ss without touching the committed schematics.\n"
          f"\n  examples/diffamp came out 18% below its as-drawn gain, and\n"
          f"  examples/otabuf the same direction the same day. If this one lands\n"
          f"  near -18% too, that is three circuits agreeing on the corner rather\n"
          f"  than three separate coincidences.")

    print(f"\n  The input offset -- the last column of the table -- is the one\n"
          f"  quantity the simulated sheet cannot produce at all: it is perfectly\n"
          f"  symmetric by construction and ngspice is noiseless, so the sheet's\n"
          f"  offset is exactly zero and silicon's is device mismatch. Read it as an\n"
          f"  observation at a nominated output level (1.1 V here), not as the pair's\n"
          f"  input offset voltage in the datasheet sense.")


if __name__ == "__main__":
    main()
