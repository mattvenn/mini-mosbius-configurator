#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Draw examples/currentsource as drawn, as routed, and on silicon.

Inputs, all produced by other commands so this script only draws:

    build/currentsource_tb.txt                  from tb_currentsource.sch,
                                                via tools/ci/check_example_sim.sh currentsource
    build/currentsource_compliance_source.json  from
    build/currentsource_compliance_sink.json    tools/ad3/measure_currentsource_ad3.py

Either measured file on its own is enough; with both, both legs are drawn.
Writes examples/currentsource/currentsource_comparison.png.

**The top panel is the honest comparison and the bottom panel is the
useful one.** Absolute current on this chip is only as good as the bias
current that sets it, and on a board without the RP2350 current source
that bias is a bench supply through a resistor -- so a measured curve
sitting a few percent above or below the simulated pair says almost
nothing about the mirror. What the two panels do is separate the two
questions. The top asks "how much current", which is mostly a question
about the bias. The bottom refers every curve to its own value at
mid-rail, which cancels the bias entirely and asks the question the
example is actually about: over what range of pin voltage is this thing a
current source at all, and where does it stop being one?

**The +/-5% band is drawn because the answer is bounded at both ends.**
The simulated source leg is within 5% of its mid-rail value only between
about 0.6 V and 2.3 V. The low end surprises people -- the mirror is
expected to fail near its own rail and does, but it is also off by 5% at
the far end of the swing, where nothing has gone wrong at all. That is
finite output resistance, and it is visible as a slope in a panel that
would otherwise look flat.

**Current is positive out of the chip pin,** matching the testbench's
`i(vam_*)` sign convention, so the source leg is drawn above zero and the
sink leg below it.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

OUT = Path("examples/currentsource/currentsource_comparison.png")
TB = Path("build/currentsource_tb.txt")
MEASURED = {"source": Path("build/currentsource_compliance_source.json"),
            "sink": Path("build/currentsource_compliance_sink.json")}

# ngspice's wrdata writes the sweep variable before EVERY vector, so four
# currents come out as eight columns: x, source_drawn, x, source_routed,
# x, sink_drawn, x, sink_routed -- in the order tb_currentsource.sch's
# `wrdata` line names them.
TB_COLUMNS = {("source", "as drawn"): 1, ("source", "as routed"): 3,
              ("sink", "as drawn"): 5, ("sink", "as routed"): 7}

COLOURS = {"as drawn": "#4c72b0", "as routed": "#dd8452", "on silicon": "#7d5bbe"}
# Colour carries the fidelity, matching the other figures in this repo, so
# the leg has to be carried by something else or the two families are
# indistinguishable in the normalised panel where they overlap.
LINESTYLES = {"source": "-", "sink": "--"}
FLAT = (0.5, 2.3)          # where the mirror is meant to be in saturation
MIDRAIL = 1.65


def load_tb(path: Path) -> list[list[float]]:
    return [[float(x) for x in line.split()]
            for line in path.read_text().splitlines() if line.strip()]


def at_midrail(xs: list[float], ys: list[float]) -> float:
    """The current at mid-rail, which every curve is normalised against."""
    return min(zip(xs, ys), key=lambda p: abs(p[0] - MIDRAIL))[1]


def slope_over(xs: list[float], ys: list[float], window: tuple[float, float]):
    """(amps per volt) across `window` by least squares, or None if the
    curve does not span it.

    Least squares rather than the two end points, because the end points
    are where a measured curve is worst: one is next to the knee and both
    carry their own noise, so a two-point slope on the sink leg came out
    10% away from the fit through all 37 points in the window. The
    simulated curves are smooth enough not to care, which is exactly why
    the difference showed up as a measured-versus-simulated discrepancy
    that was really a discrepancy between two ways of taking a slope.
    """
    inside = [(x, y) for x, y in zip(xs, ys) if window[0] <= x <= window[1]]
    if len(inside) < 3 or inside[-1][0] - inside[0][0] < 0.2:
        return None
    n = len(inside)
    sx = sum(x for x, _ in inside)
    sy = sum(y for _, y in inside)
    sxx = sum(x * x for x, _ in inside)
    sxy = sum(x * y for x, y in inside)
    denom = n * sxx - sx * sx
    return (n * sxy - sx * sy) / denom if abs(denom) > 1e-12 else None


def five_percent_span(xs: list[float], ys: list[float], nominal: float):
    """(low, high) pin voltage over which the current stays within 5%."""
    inside = [x for x, y in zip(xs, ys) if abs(y - nominal) <= 0.05 * abs(nominal)]
    return (min(inside), max(inside)) if inside else None


def main() -> None:
    if not TB.exists():
        raise SystemExit(
            f"missing {TB}\n\n"
            "  This script only draws. The simulated curves come from the real\n"
            "  testbench, which needs xschem and ngspice, so run it in the\n"
            "  IIC-OSIC-TOOLS container from the repo root:\n\n"
            "    docker run --rm -v \"$PWD:/work\" -w /work hpretl/iic-osic-tools:latest \\\n"
            "        --skip bash -lc 'sh tools/ci/check_example_sim.sh currentsource'\n")

    have = {leg: path for leg, path in MEASURED.items() if path.exists()}
    if not have:
        raise SystemExit(
            "no measured data: neither " + " nor ".join(str(p) for p in MEASURED.values())
            + " exists.\n\n"
            "  Those come from the bench, on the host, with an Analog Discovery\n"
            "  and a sense resistor wired to the demoboard:\n\n"
            "    python3 tools/ad3/measure_currentsource_ad3.py --leg source\n"
            "    python3 tools/ad3/measure_currentsource_ad3.py --leg sink\n\n"
            "  Either one alone is enough to draw a figure.")

    rows = load_tb(TB)
    curves = {}   # (leg, which) -> (pin volts, amps)
    for (leg, which), col in TB_COLUMNS.items():
        if leg not in have:
            continue
        curves[(leg, which)] = ([r[col - 1] for r in rows], [r[col] for r in rows])
    # If a background sweep exists, subtract it. It is the current that
    # flows on the pad node with every switch open -- two 1 MOhm scope
    # inputs returning to the channel offset, measured at 487 kOhm. That is
    # ~0.03 uA at mid-rail and so invisible there, but +/-3.3 uA at the
    # rails, which is a real part of the slope this figure's lower panel is
    # about. Doing it here rather than only in the measuring script keeps
    # one set of numbers in the figure, its printed table and the README.
    background = None
    for cand in sorted(Path("build").glob("currentsource_background_*.json")):
        background = sorted((q["pin"], q["amps"])
                            for q in json.loads(cand.read_text())["points"])
        print(f"subtracting the background measured in {cand}")
        break

    def minus_background(v, a):
        if not background:
            return a
        if v <= background[0][0]:
            return a - background[0][1]
        if v >= background[-1][0]:
            return a - background[-1][1]
        for (x0, y0), (x1, y1) in zip(background, background[1:]):
            if x0 <= v <= x1:
                f = (v - x0) / (x1 - x0) if x1 > x0 else 0.0
                return a - (y0 + f * (y1 - y0))
        return a

    for leg, path in have.items():
        record = json.loads(path.read_text())
        points = record["points"]
        curves[(leg, "on silicon")] = (
            [p["pin"] for p in points],
            [minus_background(p["pin"], p["amps"]) for p in points])

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 9), sharex=True,
                                   gridspec_kw={"height_ratios": [1.25, 1]})

    summary = []
    for leg in have:
        for which in ("as drawn", "as routed", "on silicon"):
            xs, ys = curves[(leg, which)]
            nominal = at_midrail(xs, ys)
            marker = "." if which == "on silicon" else ""
            ls = LINESTYLES[leg]
            ax1.plot(xs, [y * 1e6 for y in ys], ls, marker=marker, ms=3,
                     color=COLOURS[which], lw=1.6,
                     label=f"{leg}, {which}   {nominal * 1e6:+.1f} uA at mid-rail")
            ax2.plot(xs, [(y / nominal - 1) * 100 for y in ys], ls,
                     marker=marker, ms=3, color=COLOURS[which], lw=1.6)

            slope = slope_over(xs, ys, FLAT)
            span = five_percent_span(xs, ys, nominal)
            summary.append((leg, which, nominal, slope, span))

    ax1.axhline(0, color="#999999", lw=0.8)
    ax1.axvline(MIDRAIL, color="#999999", lw=0.8, ls=":")
    ax1.set_ylabel("current out of the pin (uA)")
    ax1.set_title("mini-MOSbius programmable current source: "
                  "as drawn, as routed, on silicon")
    ax1.grid(alpha=0.25)
    ax1.legend(fontsize=8, loc="center right")

    ax2.axhspan(-5, 5, color="#55a868", alpha=0.10)
    ax2.axhline(0, color="#999999", lw=0.8)
    ax2.axvline(MIDRAIL, color="#999999", lw=0.8, ls=":")
    ax2.set_ylim(-40, 20)
    ax2.set_xlim(0, 3.3)
    ax2.set_xlabel("voltage at the chip pin (V)")
    ax2.set_ylabel("deviation from each curve's own\nmid-rail value (%)")
    ax2.grid(alpha=0.25)
    caption = ("shaded: within 5% of mid-rail. Normalising each curve to itself\n"
               "cancels the bias current, so what is left is the shape -- which is\n"
               "the thing a symbol drawn as an ideal source would not have told you.")
    if len(have) > 1:
        caption += "\nsolid = source leg, dashed = sink leg."
    ax2.text(0.98, 0.97, caption, transform=ax2.transAxes, fontsize=8,
             va="top", ha="right", color="#444444")

    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=140)
    print(f"wrote {OUT}")

    print("\n  leg      curve         at mid-rail   output R over "
          f"{FLAT[0]}..{FLAT[1]} V   within 5% over")
    print("  ------   -----------   -----------   ---------------------   "
          "--------------")
    for leg, which, nominal, slope, span in summary:
        rout = "-" if not slope else f"{abs(1 / slope) / 1000:>10.1f} kOhm"
        window = "-" if not span else f"{span[0]:.2f}..{span[1]:.2f} V"
        print(f"  {leg:<6s}   {which:<11s}   {nominal * 1e6:+8.1f} uA   "
              f"{rout:>21s}   {window}")
    print("\n  Compare the 'within 5%' column across the three rows of a leg, not\n"
          "  the mid-rail column: that one moves with the bias current, which on a\n"
          "  board without the RP2350 source is a resistor and a supply setting.")


if __name__ == "__main__":
    main()
