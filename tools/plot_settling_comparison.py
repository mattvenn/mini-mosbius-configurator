#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Draw examples/otabuf's slew and delay against bias current.

Input, produced by another command so this script only draws:

    build/otabuf_settling.json   from tools/measure_settling_ad3.py otabuf

Writes examples/otabuf/otabuf_settling.png.

**Why bias is the x axis and not time.** A single slew reading at the
nominal bias is worthless here: the output crosses its measurement band in
81 ns while the generator's own edge is 74 ns, so the two cannot be told
apart. Slew goes as the tail current, though, and the tail current is
`4 x ibias` -- so turning the bias down slows the output while the
generator's edge stays exactly where it is. The low-bias points are the
measurement; the high-bias ones are shaded out because they are partly the
instrument. That shading is the honest part of this figure.

**The slope is the result, not any single point.** slew = 4 x ibias / C, so
fitting slew against bias gives the output node's capacitance without
needing the probe's own capacitance to be known -- which matters, because
the 24 pF an Analog Discovery presents is a datasheet number rather than
something measured here.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

OUT = Path("examples/otabuf/otabuf_settling.png")
SRC = Path("build/otabuf_settling.json")
MARGIN = 3.0
BAND = 0.7                 # the 1.3-2.0 V window the slew is measured across
TAIL_MULT = 4              # tail=4
C_EXPECTED_PF = 40.0       # routed model's node capacitance plus this probe


def lsq(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    return slope, my - slope * mx


def main() -> None:
    if not SRC.exists():
        raise SystemExit(
            f"missing {SRC}\n\n"
            "  This script only draws. Run\n"
            "  `python3 tools/measure_settling_ad3.py otabuf` first.")
    by_bias = json.loads(SRC.read_text())["by_bias"]
    ua = [b["amps"] * 1e6 for b in by_bias]
    rise = [b["rising"]["value"] for b in by_bias]
    fall = [b.get("falling", {}).get("value") for b in by_bias]
    d_rise = [b["rising"].get("delay_ns") for b in by_bias]
    d_fall = [b.get("falling", {}).get("delay_ns") for b in by_bias]
    stim = [b["rising"].get("stimulus_ns") for b in by_bias]
    margins = [(BAND / r * 1000) / s if r and s else 0 for r, s in zip(rise, stim)]
    clean = [i for i, m in enumerate(margins) if m >= MARGIN]
    cut = max(ua[i] for i in clean) if clean else 0

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 8.6), sharex=True,
                                   gridspec_kw={"height_ratios": [1.15, 1]})

    for ax in (ax1, ax2):
        ax.axvspan(cut + 3, max(ua) * 1.08, color="0.9", zorder=0)

    ax1.plot(ua, rise, "o-", color="#4c72b0", ms=6, lw=1.4, label="rising")
    if all(fall):
        ax1.plot(ua, fall, "s-", color="#c44e52", ms=5.5, lw=1.4, label="falling")
    if len(clean) > 1:
        slope, intercept = lsq([by_bias[i]["amps"] for i in clean],
                               [rise[i] * 1e6 for i in clean])
        c_pf = TAIL_MULT / slope * 1e12
        xs = [0, max(ua) * 1.08]
        ax1.plot(xs, [(slope * (x * 1e-6) + intercept) / 1e6 for x in xs], "--",
                 color="#4c72b0", lw=1.1, alpha=0.6,
                 label=f"fit to the clean points: C = {c_pf:.1f} pF")
        ax1.plot([0, max(ua) * 1.08],
                 [0, TAIL_MULT * max(ua) * 1.08e-6 / (C_EXPECTED_PF * 1e-12) / 1e6],
                 ":", color="0.5", lw=1.2,
                 label=f"routed model + this probe: {C_EXPECTED_PF:.0f} pF")
    ax1.set_ylabel("slew rate  (V/us)")
    ax1.set_title("examples/otabuf -- slew and delay against bias current\n"
                  "tail=4, output on ua2 / pad J, 24 pF probe", fontsize=11)
    ax1.legend(loc="upper left", fontsize=8.5)
    ax1.grid(alpha=0.25)
    ax1.set_xlim(0, max(ua) * 1.08)
    ax1.set_ylim(0, max(rise) * 1.15)

    ax2.plot(ua, d_rise, "o-", color="#4c72b0", ms=6, lw=1.4, label="rising")
    if all(d_fall):
        ax2.plot(ua, d_fall, "s-", color="#c44e52", ms=5.5, lw=1.4, label="falling")
    if stim and stim[0]:
        ax2.axhline(stim[0], color="0.45", ls="-.", lw=1.2,
                    label=f"the generator's own edge, {stim[0]:.0f} ns")
    ax2.set_xlabel("bias current into pad K, from V+ through 20 kOhm  (uA)")
    ax2.set_ylabel("input-to-output delay at 50%  (ns)")
    ax2.legend(loc="upper right", fontsize=8.5)
    ax2.grid(alpha=0.25)
    ax2.set_ylim(0, max(d_fall or d_rise) * 1.12)

    ax2.text(0.985, 0.42,
             "Shaded: the output is within 3x of the generator's edge,\n"
             "so those points time the instrument as much as the chip.\n"
             "Everything quoted comes from the unshaded ones.",
             transform=ax2.transAxes, ha="right", va="top", fontsize=8,
             color="0.35")

    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=140)
    print(f"wrote {OUT}")
    if len(clean) > 1:
        print(f"  clean points: {[round(ua[i], 1) for i in clean]} uA")
        print(f"  fitted C = {c_pf:.1f} pF against {C_EXPECTED_PF:.0f} pF expected "
              f"({c_pf / C_EXPECTED_PF:.2f}x)")


if __name__ == "__main__":
    main()
