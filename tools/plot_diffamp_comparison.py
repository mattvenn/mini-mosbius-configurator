#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Draw examples/diffamp three ways: as drawn, as routed, on silicon.

Inputs, all produced by other commands so this script only draws:

    build/diffamp_tb_inp.txt         from tb_diffamp.sch, via
    build/diffamp_tb_out_drawn.txt   tools/check_diffamp_sim.sh
    build/diffamp_tb_out_routed.txt
    build/diffamp_silicon.json       from tools/measure_diffamp_ad3.py

Writes examples/diffamp/diffamp_three_ways.png.

**The simulated side is three points, not a curve, and the figure has to
be honest about that.** tb_diffamp.sch is a step response: it holds the
input at the common-mode point, steps +40 mV, steps -40 mV, and returns.
So the only differential inputs it visits are 0 and +/-40 mV, and its
settled outputs at those three levels are all that can be plotted against
a silicon sweep of 81 points. They are drawn as large markers for exactly
that reason -- a line through three points would imply a measurement that
was never made. Getting a dense simulated curve means a DC sweep of the
testbench, which is a separate run.

**The x axis is differential input referred to each branch's own operating
point.** An absolute input axis would put silicon several millivolts to one
side of the simulated pair for a reason that has nothing to do with gain:
the real pair has an input offset from device mismatch and the simulated
one has none, being perfectly symmetric and noiseless. Referring each to
its own centre puts the comparison where it belongs -- on the slope.

**The bottom panel is the reason for measuring at three bias currents.**
Gain against tail current is a ratio measurement, so it survives both the
resistor tolerance in the hand-made bias and the scope's channel offsets,
and it discriminates strong from moderate inversion: gain proportional to
1/sqrt(I) is the strong-inversion prediction, gain flat with I is what
moderate inversion gives.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

OUT = Path("examples/diffamp/diffamp_three_ways.png")
LINEAR_WINDOW = (1.3, 2.4)
SETTLED_AT = (0.9e-6, 3.4e-6, 5.9e-6)     # ends of the 0 / +40mV / -40mV holds
STEPS_MV = (0.0, +40.0, -40.0)


def load_col(path: Path):
    return [[float(x) for x in line.split()]
            for line in path.read_text().splitlines() if line.strip()]


def settled(rows, when):
    """The value just before a hold ends -- the settled level of that step."""
    best = min(rows, key=lambda r: abs(r[0] - when))
    return best[1]


def lsq(points):
    n = len(points)
    mx = sum(p[0] for p in points) / n
    my = sum(p[1] for p in points) / n
    denom = sum((p[0] - mx) ** 2 for p in points)
    slope = sum((p[0] - mx) * (p[1] - my) for p in points) / denom
    return slope, my - slope * mx


def main() -> None:
    need = {n: Path(f"build/{n}") for n in
            ("diffamp_tb_inp.txt", "diffamp_tb_out_drawn.txt",
             "diffamp_tb_out_routed.txt", "diffamp_silicon.json")}
    missing = [str(p) for p in need.values() if not p.exists()]
    if missing:
        raise SystemExit(
            "missing " + ", ".join(missing) + "\n\n"
            "  This script only draws. Produce the simulated curves with\n"
            "  tools/check_diffamp_sim.sh and the measured ones with\n"
            "  tools/measure_diffamp_ad3.py, then run this again.")

    drawn_rows = load_col(need["diffamp_tb_out_drawn.txt"])
    routed_rows = load_col(need["diffamp_tb_out_routed.txt"])
    sim = {"as drawn": [settled(drawn_rows, t) for t in SETTLED_AT],
           "as routed": [settled(routed_rows, t) for t in SETTLED_AT]}

    record = json.loads(need["diffamp_silicon.json"].read_text())
    good = [b for b in record["by_bias"] if b.get("fine")]
    nominal = min(good, key=lambda b: abs((b["amps"] or 0) - 100e-6))

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 8.8),
                                   gridspec_kw={"height_ratios": [1.3, 1]})

    # -- top: transfer, each branch referred to its own operating point
    for name, outs, colour in (("as drawn", sim["as drawn"], "#4c72b0"),
                               ("as routed", sim["as routed"], "#dd8452")):
        base = outs[0]
        gain = (outs[1] - outs[2]) / 0.080
        ax1.plot(STEPS_MV, [o - base for o in outs], "D", color=colour, ms=8,
                 label=f"{name}   {gain:.2f} V/V over +/-40 mV", zorder=4)

    fine = nominal["fine"]
    lin = [p for p in fine if LINEAR_WINDOW[0] <= p[1] <= LINEAR_WINDOW[1]]
    slope, intercept = lsq(lin)
    centre_in = (2.0 - intercept) / slope       # where the fit crosses 2.0 V
    centre_out = 2.0
    ax1.plot([(p[0] - centre_in) * 1000 for p in fine],
             [p[1] - centre_out for p in fine], "o", color="#55a868", ms=3.2,
             label=f"on silicon   {slope:.2f} V/V fitted", zorder=3)

    xs = [-45, 45]
    ax1.plot(xs, [slope * x / 1000 for x in xs], "-", color="#55a868",
             lw=1, alpha=0.55, zorder=2)
    ax1.axhline(0, color="0.8", lw=0.9, ls=":")
    ax1.axvline(0, color="0.8", lw=0.9, ls=":")
    ax1.set_xlabel("differential input, referred to each branch's own operating point  (mV)")
    ax1.set_ylabel("output change from that point  (V)")
    ax1.set_title("examples/diffamp -- 5-transistor differential amplifier, three ways\n"
                  f"tail=4, bias {nominal['amps'] * 1e6:.0f} uA, "
                  f"{record['fine_step'] * 1000:.0f} mV input steps", fontsize=11)
    ax1.legend(loc="upper left", fontsize=9)
    ax1.grid(alpha=0.25)
    ax1.set_xlim(-48, 48)
    ax1.text(0.985, 0.05,
             "The simulated side is a step response, so it visits only 0 and\n"
             "+/-40 mV -- three settled levels, drawn as markers. A line through\n"
             "them would imply a sweep that was never run.",
             transform=ax1.transAxes, ha="right", va="bottom", fontsize=8,
             color="0.35")

    # -- bottom: gain against tail current
    amps = [b["amps"] * 1e6 for b in good]
    gains = [lsq([p for p in b["fine"]
                  if LINEAR_WINDOW[0] <= p[1] <= LINEAR_WINDOW[1]])[0]
             for b in good]
    ax2.plot(amps, gains, "o-", color="#55a868", ms=7, lw=1.4,
             label="on silicon, fitted")
    ref_i, ref_g = amps[0], gains[0]
    ax2.plot(amps, [ref_g * (ref_i / i) ** 0.5 for i in amps], "--",
             color="0.55", lw=1.2,
             label="strong inversion: gain ~ 1/sqrt(I), scaled to the first point")
    ax2.plot(amps, [ref_g] * len(amps), ":", color="#c44e52", lw=1.2,
             label="moderate inversion: gain flat with I")
    for i, g in zip(amps, gains):
        ax2.annotate(f"{g:.2f}", (i, g), textcoords="offset points",
                     xytext=(0, 9), ha="center", fontsize=8.5, color="#3a6b48")
    ax2.set_xlabel("tail bias current, from the rail and the 20 kOhm resistor  (uA)")
    ax2.set_ylabel("gain over the linear region  (V/V)")
    ax2.legend(loc="lower left", fontsize=8.5)
    ax2.grid(alpha=0.25)
    ax2.set_ylim(9, 19)
    ax2.text(0.985, 0.94,
             "A ratio, so the resistor's tolerance and the channel\n"
             "offsets both drop out of it.",
             transform=ax2.transAxes, ha="right", va="top", fontsize=8,
             color="0.35")

    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=140)
    print(f"wrote {OUT}")
    print(f"  silicon fitted gain {slope:.2f} V/V, centre at ua1 = {centre_in:.4f} V")
    for n, o in sim.items():
        print(f"  {n:<10s} base {o[0]:.3f} V, +40mV {o[1]:.3f}, -40mV {o[2]:.3f}")
    for i, g in zip(amps, gains):
        print(f"  {i:6.1f} uA -> {g:.2f} V/V")


if __name__ == "__main__":
    main()
