#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Draw examples/srlatch as drawn, as routed, and as measured on silicon.

Inputs, all produced by other commands so this script only draws:

    build/srlatch_tb_out_drawn.txt    from tb_srlatch.sch, via
    build/srlatch_tb_out_routed.txt   tools/check_example_sim.sh srlatch
    build/srlatch_silicon_trace.json  from tools/measure_srlatch_ad3.py

Writes two figures:

    examples/srlatch/srlatch_comparison.png   the whole sequence, levels
    build/srlatch_reset_edge.png              the reset transition, zoomed

The second one needs build/srlatch_silicon_edge.json from
tools/measure_srlatch_edge_ad3.py and the matched-stimulus simulation from
tools/run_srlatch_measured_edge.sh; it is skipped if either is absent.

**The two panels cannot share a time axis, and that is the honest way to
draw it.** The sheet pulses SET and RESET nanoseconds apart because
nothing in simulation costs anything to wait for; the bench drives them
milliseconds apart because that is a comfortable rate for a wavegen and
the levels being read are static. Six orders of magnitude separate the
axes, so putting both on one would either hide the silicon trace in a
single pixel or stretch the simulation into a flat line. What the two
panels are actually being compared on is the *levels* -- the held
voltages, which is all this bench can measure -- so they share the
voltage axis and label the time axes separately.

**The shaded windows are the point of the figure.** A trace of Q alone
cannot show a latch: high while something drives it high is what any gate
does. What makes it a latch is Q staying put *after* the drive is
released, so both panels shade the intervals when SET and then RESET are
actually held, and the flat stretches to the right of each shaded band are
the stored state. On the silicon panel the shading is the commanded
window; the trace's own edges lag it by a few milliseconds of host
scheduling, which is visible and does not matter to a level measurement.

**The first figure measures no edge, and the second one does.** In the
left panel of `srlatch_comparison.png` the transitions are the
generator's DC offset slewing over milliseconds -- that is how
`tools/measure_srlatch_ad3.py` drives the levels, and it is the wrong
instrument for an edge. `build/srlatch_reset_edge.png` is the other measurement:
real waveform edges, the scope triggered on Q's own fall at 100 MS/s, and
both decks re-run under the same stimulus by
`tools/run_srlatch_measured_edge.sh`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

DRAWN = Path("build/srlatch_tb_out_drawn.txt")
ROUTED = Path("build/srlatch_tb_out_routed.txt")
SILICON = Path("build/srlatch_silicon_trace.json")
OUT = Path("examples/srlatch/srlatch_comparison.png")

EDGE_SILICON = Path("build/srlatch_silicon_edge.json")
EDGE_RESET = Path("build/srlatch_edge_reset.txt")
EDGE_DRAWN = Path("build/srlatch_edge_out_drawn.txt")
EDGE_ROUTED = Path("build/srlatch_edge_out_routed.txt")
EDGE_OUT = Path("build/srlatch_reset_edge.png")
MIDRAIL = 1.65

# The repo-wide fidelity palette: colour says which of the three a trace is,
# and nothing else, so a reader who has looked at any other example's figure
# already knows how to read this one. Purple rather than green for silicon
# because green against this orange is not separable for a protanope.
COLOURS = {"as drawn": "#4c72b0", "as routed": "#dd8452", "on silicon": "#7d5bbe"}
STIMULUS = "#888888"        # a driven input, not one of the three


def load_txt(path: Path) -> tuple[list[float], list[float]]:
    xs, ys = [], []
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 2:
            xs.append(float(parts[0]))
            ys.append(float(parts[1]))
    return xs, ys


def missing(path: Path, how: str) -> None:
    raise SystemExit(
        f"can't find {path}\n\n"
        f"  {how}\n"
        "  This script only draws; it does not run anything itself."
    )


def cross_time(ts: list[float], vs: list[float], level: float, falling: bool):
    """Time at which a trace crosses `level`, interpolated between samples."""
    for i in range(1, len(vs)):
        a, b = vs[i - 1], vs[i]
        if (falling and a > level >= b) or (not falling and a < level <= b):
            if a == b:
                return ts[i]
            return ts[i - 1] + (ts[i] - ts[i - 1]) * (a - level) / (a - b)
    return None


def draw_edge_figure() -> None:
    """The reset transition, silicon and simulation on one nanosecond axis.

    Both are aligned on RESET's own mid-rail crossing rather than on a
    stimulus start, because that is what the delay is measured from at
    both ends -- and the two stimuli, though matched in 10%-90% edge rate,
    do not start at the same instant or have the same shape.
    """
    if not all(p.exists() for p in (EDGE_SILICON, EDGE_RESET, EDGE_DRAWN, EDGE_ROUTED)):
        print("  (skipping the edge figure: run tools/measure_srlatch_edge_ad3.py and\n"
              "   tools/run_srlatch_measured_edge.sh first)")
        return

    edge = json.loads(EDGE_SILICON.read_text())
    rate = edge["rate"]
    ts = [i / rate * 1e9 for i in range(len(edge["trace"]["q"]))]
    si_reset, si_q = edge["trace"]["reset"], edge["trace"]["q"]
    t0 = cross_time(ts, si_reset, MIDRAIL, falling=False)

    tr, vr = load_txt(EDGE_RESET)
    td, vd = load_txt(EDGE_DRAWN)
    _, vro = load_txt(EDGE_ROUTED)
    tr_ns = [t * 1e9 for t in tr]
    sim_t0 = cross_time(tr_ns, vr, MIDRAIL, falling=False)

    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    ax.plot([t - t0 for t in ts], si_reset, color=STIMULUS, lw=1.0,
            label="RESET, on silicon")
    ax.plot([t - t0 for t in ts], si_q, color=COLOURS["on silicon"], lw=1.6,
            label="Q, on silicon")
    ax.plot([t - sim_t0 for t in tr_ns], vd, color=COLOURS["as drawn"], lw=1.2, ls="--",
            label="Q, as drawn (ss)")
    ax.plot([t - sim_t0 for t in tr_ns], vro, color=COLOURS["as routed"], lw=1.2, ls="-.",
            label="Q, as routed (ss)")
    ax.axhline(MIDRAIL, color="#bbbbbb", lw=0.8)
    ax.axvline(0, color="#bbbbbb", lw=0.8)
    ax.set_xlim(-30, 90)
    ax.set_ylim(-0.3, 3.6)
    ax.set_xlabel("ns, from RESET crossing mid-rail")
    ax.set_ylabel("V")
    ax.set_title("SR latch reset: measured on silicon, and both decks driven with "
                 "the same 20 ns edge", fontsize=10)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, loc="center right")
    fig.tight_layout()
    fig.savefig(EDGE_OUT, dpi=130)
    print(f"== written to {EDGE_OUT}")


def main() -> None:
    for path, how in [
        (DRAWN, "Run `sh tools/check_example_sim.sh srlatch` in the IIC-OSIC-TOOLS container "
                "to\n  simulate tb_srlatch.sch and write it."),
        (ROUTED, "Run `sh tools/check_example_sim.sh srlatch` in the IIC-OSIC-TOOLS container "
                 "to\n  simulate tb_srlatch.sch and write it."),
        (SILICON, "Run `python3 tools/measure_srlatch_ad3.py` on the host, with the "
                  "chip\n  in the socket and an Analog Discovery on pads C, J and D."),
    ]:
        if not path.exists():
            missing(path, how)

    td, vd = load_txt(DRAWN)
    tr, vr = load_txt(ROUTED)
    trace = json.loads(SILICON.read_text())["trace"]
    rate = trace["rate"]
    ts = [i / rate * 1e3 for i in range(len(trace["q"]))]

    fig, (left, right) = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)

    def shade(axis, start, stop, label):
        axis.axvspan(start, stop, color="#999999", alpha=0.18)
        axis.text((start + stop) / 2, 3.45, label, ha="center", va="top", fontsize=8,
                  color="#555555")

    plan = trace["plan"]
    shade(left, plan[0][0] * 1e3, plan[1][0] * 1e3, "SET")
    shade(left, plan[2][0] * 1e3, plan[3][0] * 1e3, "RESET")
    shade(right, 60, 101, "SET")       # tb_srlatch.sch's two PULSE sources
    shade(right, 220, 261, "RESET")

    left.plot(ts, trace["q"], color=COLOURS["on silicon"], lw=1.2, label="Q on silicon")
    left.set_xlabel("time (ms) -- inputs driven milliseconds apart")
    left.set_ylabel("Q (V)")
    left.set_title("on silicon")
    left.legend(loc="center right", fontsize=8)

    right.plot([t * 1e9 for t in td], vd, color=COLOURS["as drawn"], lw=1.2,
               label="as drawn")
    right.plot([t * 1e9 for t in tr], vr, color=COLOURS["as routed"], lw=1.2, ls="--",
               label="as routed")
    right.set_xlabel("time (ns) -- inputs pulsed nanoseconds apart")
    right.set_title("simulated")
    right.legend(loc="center right", fontsize=8)

    for axis in (left, right):
        axis.grid(alpha=0.3)
        axis.set_ylim(-0.3, 3.6)

    fig.suptitle("SR latch: SET, hold, RESET, hold -- the held levels are what "
                 "the bench can compare", fontsize=10)
    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=130)
    print(f"== written to {OUT}")
    print("  Shaded: the input actually held high. Q holding its level to the right\n"
          "  of each band, with nothing driving it, is the measurement.")
    draw_edge_figure()
    print("  Note the time axes differ by six orders of magnitude: the transitions in\n"
          "  the silicon panel are the generator's DC offset slewing, not the latch\n"
          "  switching, so that figure compares the flat parts. The latch's own edge\n"
          "  is the second figure.")


if __name__ == "__main__":
    sys.exit(main())
