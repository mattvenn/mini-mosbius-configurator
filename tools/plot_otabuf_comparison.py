#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Draw examples/otabuf as drawn, as routed, and on silicon.

Inputs, all produced by other commands so this script only draws:

    build/otabuf_tb.txt            from tb_otabuf.sch, via
                                   tools/ci/check_example_sim.sh otabuf
    build/otabuf_silicon_dc.json   from tools/ad3/measure_otabuf_ad3.py

Writes examples/otabuf/otabuf_comparison.png.

**Two panels, because one cannot show this.** The follower's whole job is
that output equals input, so on a 3 V transfer curve all three traces lie
on the unity line and on each other -- which is the result, and is also
completely uninformative about how well. Everything that distinguishes
drawn from routed from silicon is tens of millivolts, a percent of the
axis. So the top panel establishes that it follows at all, and the bottom
panel plots output *minus* input, where those tens of millivolts fill the
frame.

**The bottom panel's silicon trace carries an unknown constant.** Output
minus input on the bench is the difference of two uncalibrated scope
channel offsets plus the real thing, and on this instrument that difference
is the same tens of millivolts as the signal. So the silicon curve's
vertical *position* is not evidence; its *slope* is, because a slope is a
ratio of differences within each channel and a constant offset cancels out
of it. The legend gives each curve's fitted slope for that reason, and the
panel says so rather than leaving a reader to assume the offsets are
comparable.

The simulated curves come from the ramp segment of the testbench transient
(1 to 11 us), which is slow enough that the follower tracks it, so out
against in over that window is the DC transfer curve by another route.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

RAMP = (1e-6, 11e-6)
OUT = Path("examples/otabuf/otabuf_comparison.png")
FIT_LO, FIT_HI = 1.00, 2.50          # the window the README's table uses
TRACKING, SLOPE_BAND = 0.100, (0.8, 1.2)


def load_sim(path: Path):
    """(in, drawn, routed) over the ramp. wrdata writes t,v per vector, so
    the columns are t, in, t, out_drawn, t, out_routed."""
    rows = [[float(x) for x in line.split()] for line in
            path.read_text().splitlines() if line.strip()]
    ramp = [r for r in rows if RAMP[0] <= r[0] <= RAMP[1]]
    return ([r[1] for r in ramp], [r[3] for r in ramp], [r[5] for r in ramp])


def fit_slope(vin, vout, lo=FIT_LO, hi=FIT_HI):
    pairs = [(x, y) for x, y in zip(vin, vout) if lo <= x <= hi]
    n = len(pairs)
    if n < 2:
        return float("nan")
    mx = sum(p[0] for p in pairs) / n
    my = sum(p[1] for p in pairs) / n
    denom = sum((p[0] - mx) ** 2 for p in pairs)
    return float("nan") if denom == 0 else \
        sum((p[0] - mx) * (p[1] - my) for p in pairs) / denom


def tracking_band(vin, vout):
    """Longest contiguous run that actually follows -- near AND slope ~1.

    Nearness alone is not enough: below the common-mode range the output
    sits pinned at a floor, the input ramps up through it, and the
    difference passes through zero on the way past. See
    tools/ad3/measure_otabuf_ad3.py for the full version of this trap.
    """
    best, run = [], []
    for i, (x, y) in enumerate(zip(vin, vout)):
        a, b = max(0, i - 2), min(len(vin) - 1, i + 2)
        span = vin[b] - vin[a]
        slope = None if abs(span) < 1e-9 else (vout[b] - vout[a]) / span
        if (abs(y - x) < TRACKING and slope is not None
                and SLOPE_BAND[0] <= slope <= SLOPE_BAND[1]):
            run.append(x)
            if len(run) > len(best):
                best = run
        else:
            run = []
    return (best[0], best[-1]) if best else None


def main() -> None:
    sim_path = Path("build/otabuf_tb.txt")
    sil_path = Path("build/otabuf_silicon_dc.json")
    for p in (sim_path, sil_path):
        if not p.exists():
            raise SystemExit(
                f"missing {p}\n\n"
                "  This script only draws. Produce the simulated curves with\n"
                "  tools/ci/check_example_sim.sh otabuf and the measured ones with\n"
                "  tools/ad3/measure_otabuf_ad3.py, then run this again."
            )

    vin_s, drawn, routed = load_sim(sim_path)
    silicon = json.loads(sil_path.read_text())
    vin_m = [p[0] for p in silicon]
    vout_m = [p[1] for p in silicon]

    series = [
        ("as drawn", vin_s, drawn, "#4c72b0", "-", 1.4),
        ("as routed", vin_s, routed, "#dd8452", "-", 1.4),
        ("on silicon", vin_m, vout_m, "#7d5bbe", "o", 3.0),
    ]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 8.5), sharex=True,
                                   gridspec_kw={"height_ratios": [1.15, 1]})

    ax1.plot([0, 3.3], [0, 3.3], color="0.75", lw=1, ls=":", label="out = in (ideal)")
    for name, x, y, colour, style, size in series:
        if style == "o":
            ax1.plot(x, y, style, color=colour, ms=size, label=name)
        else:
            ax1.plot(x, y, style, color=colour, lw=size, label=name)
    ax1.set_ylabel("output on ua2 / pad J  (V)")
    ax1.set_title("examples/otabuf -- OTA unity-gain follower\n"
                  "ibias 100 uA, tail=4", fontsize=11)
    ax1.legend(loc="upper left", fontsize=9)
    ax1.grid(alpha=0.25)
    ax1.set_xlim(0, 3.2)
    ax1.set_ylim(0, 3.2)
    ax1.text(0.98, 0.04,
             "All three lie on the unity line: it follows.\n"
             "Everything that separates them is in the panel below.",
             transform=ax1.transAxes, ha="right", va="bottom", fontsize=8.5,
             color="0.35")
    floor_m = min(vout_m)
    floor_s = min(min(drawn), min(routed))
    ax1.annotate(
        f"below the common-mode range the output is pinned,\n"
        f"and silicon's floor is {floor_m:.2f} V against the decks' ~{floor_s:.2f} V.\n"
        f"The input ramps up THROUGH that floor, which is why the\n"
        f"purple points cross the ideal line here without following it.",
        xy=(0.30, floor_m), xytext=(1.42, 0.86), fontsize=8, color="0.35",
        arrowprops=dict(arrowstyle="->", color="0.55", lw=0.9,
                        connectionstyle="arc3,rad=-0.15"))

    band = tracking_band(vin_m, vout_m)
    if band:
        for ax in (ax1, ax2):
            ax.axvspan(0, band[0], color="0.9", zorder=0)
            ax.axvspan(band[1], 3.2, color="0.9", zorder=0)

    for name, x, y, colour, style, size in series:
        offs = [(b - a) * 1000 for a, b in zip(x, y)]
        label = f"{name}   slope {fit_slope(x, y):.4f}"
        if style == "o":
            ax2.plot(x, offs, style, color=colour, ms=size, label=label)
        else:
            ax2.plot(x, offs, style, color=colour, lw=size, label=label)
    ax2.axhline(0, color="0.75", lw=1, ls=":")
    ax2.set_xlabel("input on ua1 / pad C  (V)")
    ax2.set_ylabel("output minus input  (mV)")
    ax2.set_ylim(-160, 160)
    ax2.legend(loc="lower left", fontsize=9, title=f"slope fitted over "
               f"{FIT_LO:.2f}-{FIT_HI:.2f} V", title_fontsize=8)
    ax2.grid(alpha=0.25)
    if band:
        ax2.text(band[0] + 0.04, 138,
                 f"shaded: outside the measured\ncommon-mode range "
                 f"({band[0]:.2f}-{band[1]:.2f} V)",
                 fontsize=8.5, color="0.35", va="top")
    ax2.text(0.985, 0.96,
             "Silicon's vertical position carries the difference of two\n"
             "uncalibrated channel offsets -- tens of mV. Its SLOPE does\n"
             "not: a constant offset cancels out of a ratio of differences.",
             transform=ax2.transAxes, ha="right", va="top", fontsize=8,
             color="0.35")

    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=140)
    print(f"wrote {OUT}")
    for name, x, y, *_ in series:
        print(f"  {name:<12s} slope {fit_slope(x, y):.4f}")
    if band:
        print(f"  measured common-mode range {band[0]:.2f} .. {band[1]:.2f} V")


if __name__ == "__main__":
    main()
