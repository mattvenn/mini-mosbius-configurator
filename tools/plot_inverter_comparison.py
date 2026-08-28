#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Draw examples/inverter's transfer curve three ways: as drawn, as routed,
and as measured on silicon.

Inputs, all produced by other commands so this script only draws:

    build/inverter_dc_drawn.txt      from tb_inverter.sch's dc sweep
    build/inverter_dc_routed.txt     (tools/check_inverter_sim.sh runs it)
    build/inverter_silicon_dc.json   from tools/measure_inverter_ad3.py
    build/inverter_silicon_fine.json optional 4 mV sweep of the transition

Writes examples/inverter/inverter_three_ways.png and prints the table that
goes with it.

**Gain is fitted, not read off the steepest pair of points.** A peak slope
depends on how finely you swept -- the same silicon reads -17.5 V/V at
25 mV steps and -20.0 V/V at 4 mV, because on fine steps the noise on each
point is a larger share of the difference between them, and taking the
maximum then picks the luckiest pair. A least-squares fit over a fixed
+/-50 mV window around the trip point is step-size independent: the same
silicon fits -16.90 and -16.82 V/V from those two sweeps.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

FIT_HALF_WIDTH = 0.05      # volts either side of the trip point


def load_txt(path: Path):
    xs, ys = [], []
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 2:
            xs.append(float(parts[0]))
            ys.append(float(parts[1]))
    return xs, ys


def load_json(path: Path):
    points = json.loads(path.read_text())
    return [p[0] for p in points], [p[1] for p in points]


def trip_point(x, y):
    return x[min(range(len(x)), key=lambda i: abs(y[i] - x[i]))]


def fitted_gain(x, y, half=FIT_HALF_WIDTH):
    centre = trip_point(x, y)
    window = [(a, b) for a, b in zip(x, y) if abs(a - centre) <= half]
    n = len(window)
    mx = sum(p[0] for p in window) / n
    my = sum(p[1] for p in window) / n
    num = sum((p[0] - mx) * (p[1] - my) for p in window)
    den = sum((p[0] - mx) ** 2 for p in window)
    return num / den


def main() -> None:
    build = Path("build")
    missing = [f for f in ("inverter_dc_drawn.txt", "inverter_dc_routed.txt",
                           "inverter_silicon_dc.json") if not (build / f).exists()]
    if missing:
        raise SystemExit(
            "missing input: " + ", ".join(f"build/{f}" for f in missing) + "\n\n"
            "  build/inverter_dc_*.txt come from the dc sweep in tb_inverter.sch --\n"
            "  run tools/check_inverter_sim.sh inside the IIC-OSIC-TOOLS container.\n"
            "  build/inverter_silicon_dc.json comes from the bench:\n"
            "  python3 tools/measure_inverter_ad3.py"
        )

    drawn = load_txt(build / "inverter_dc_drawn.txt")
    routed = load_txt(build / "inverter_dc_routed.txt")
    silicon = load_json(build / "inverter_silicon_dc.json")
    fine_path = build / "inverter_silicon_fine.json"
    fine = load_json(fine_path) if fine_path.exists() else None

    rows = [("as drawn", drawn), ("as routed", routed), ("on silicon", silicon)]
    print(f"{'':12s} {'VOH':>9s} {'VOL':>9s} {'trip point':>12s} {'gain':>10s}")
    for name, (x, y) in rows:
        print(f"{name:12s} {y[0]:8.4f}V {y[-1]:8.4f}V {trip_point(x, y):11.3f}V "
              f"{fitted_gain(x, y):9.2f}")
    if fine:
        print(f"{'  (fine)':12s} {'':9s} {'':9s} {trip_point(*fine):11.3f}V "
              f"{fitted_gain(*fine):9.2f}")

    fig, (full, zoom) = plt.subplots(1, 2, figsize=(11, 4.4))

    full.plot(*drawn, lw=1.4, color="#4C72B0", label="as drawn")
    full.plot(*routed, lw=1.4, color="#DD8452", label="as routed")
    full.plot(*silicon, "o", ms=3.2, color="#55A868", label="on silicon")
    full.set_xlabel("ua1, input (V)")
    full.set_ylabel("ua2, output (V)")
    full.set_title("CMOS inverter transfer curve")
    full.grid(alpha=0.3)
    full.legend(loc="upper right", fontsize=9)

    lo, hi = 1.35, 1.95
    for (x, y), colour, label in ((drawn, "#4C72B0", "as drawn"),
                                  (routed, "#DD8452", "as routed")):
        pts = [(a, b) for a, b in zip(x, y) if lo <= a <= hi]
        zoom.plot([p[0] for p in pts], [p[1] for p in pts], lw=1.4, color=colour, label=label)
    zx, zy = fine if fine else silicon
    pts = [(a, b) for a, b in zip(zx, zy) if lo <= a <= hi]
    zoom.plot([p[0] for p in pts], [p[1] for p in pts], "o", ms=3.2,
              color="#55A868", label="on silicon")
    zoom.plot([lo, hi], [lo, hi], ls="--", lw=0.8, color="grey", label="out = in")
    zoom.set_xlim(lo, hi)
    zoom.set_xlabel("ua1, input (V)")
    zoom.set_ylabel("ua2, output (V)")
    zoom.set_title("the transition, where the switch matrix shows up")
    zoom.grid(alpha=0.3)
    zoom.legend(loc="upper right", fontsize=9)

    out = Path("examples/inverter/inverter_three_ways.png")
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
