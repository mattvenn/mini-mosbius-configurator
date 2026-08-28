#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Ask which PDK corner the chip on the bench behaves like.

Reads what tools/sweep_corners.sh left in build/ (one inverter DC sweep and
one ring frequency per corner) and compares each against the two bench
measurements -- tools/measure_inverter_ad3.py and tools/measure_ring_ad3.py
-- then prints the corners ranked by combined error.

**Why these two circuits answer the question together.** An inverter's trip
point is a pure NMOS-versus-PMOS strength ratio, so it separates the
asymmetric corners (fs, sf) from the symmetric ones (tt, ff, ss) and says
nothing about absolute speed. A ring oscillator's frequency is absolute
speed and barely distinguishes fs from tt, because slowing the PMOS while
speeding the NMOS roughly cancels around a loop. Neither measurement alone
identifies a corner; the pair does.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

CORNERS = ("tt", "fs", "sf", "ff", "ss")
BUILD = Path("build")


def load_dc(path: Path):
    xs, ys = [], []
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 2:
            xs.append(float(parts[0]))
            ys.append(float(parts[1]))
    return xs, ys


def trip(x, y):
    return x[min(range(len(x)), key=lambda i: abs(y[i] - x[i]))]


def gain(x, y, half=0.05):
    centre = trip(x, y)
    w = [(a, b) for a, b in zip(x, y) if abs(a - centre) <= half]
    n = len(w)
    mx = sum(p[0] for p in w) / n
    my = sum(p[1] for p in w) / n
    return (sum((p[0] - mx) * (p[1] - my) for p in w)
            / sum((p[0] - mx) ** 2 for p in w))


def ring_freq(path: Path):
    if not path.exists():
        return None
    m = re.search(r"freq_routed\s*=\s*([0-9.eE+-]+)", path.read_text())
    return float(m.group(1)) if m else None


def main() -> None:
    bench_dc = BUILD / "inverter_silicon_dc.json"
    bench_ring = BUILD / "ring_silicon_trace.json"
    if not bench_dc.exists() or not bench_ring.exists():
        raise SystemExit(
            "need both bench measurements first:\n"
            "  python3 tools/measure_inverter_ad3.py\n"
            "  python3 tools/measure_ring_ad3.py"
        )

    pts = json.loads(bench_dc.read_text())
    mx, my = [p[0] for p in pts], [p[1] for p in pts]
    m_trip, m_gain = trip(mx, my), gain(mx, my)

    bench = json.loads(bench_ring.read_text())
    v = bench["v"]
    rate = bench["rate"]
    mean = sum(v) / len(v)
    signs = [1 if x - mean >= 0 else -1 for x in v]
    crossings = [i for i in range(len(signs) - 1) if signs[i] < 0 <= signs[i + 1]]
    m_freq = rate * (len(crossings) - 1) / (crossings[-1] - crossings[0])

    print(f"measured on silicon: trip {m_trip:.3f} V, gain {m_gain:.2f} V/V, "
          f"ring {m_freq / 1e6:.3f} MHz\n")
    print("corner    trip point        gain             ring frequency      combined")
    rows = []
    for c in CORNERS:
        dc = BUILD / f"inverter_dc_routed_{c}.txt"
        freq = ring_freq(BUILD / f"log_ring_{c}.log")
        if not dc.exists() or freq is None:
            print(f"{c:6s}    (missing -- run tools/sweep_corners.sh)")
            continue
        x, y = load_dc(dc)
        t, g = trip(x, y), gain(x, y)
        # trip point normalised by its own spread across corners (~100 mV),
        # the other two as plain relative errors
        errs = (abs(t - m_trip) / 0.100, abs(g / m_gain - 1), abs(freq / m_freq - 1))
        rows.append((sum(errs), c, t, g, freq))
        print(f"{c:6s}    {t:.3f} V {(t - m_trip) * 1e3:+7.1f} mV   "
              f"{g:6.2f} {(g / m_gain - 1) * 100:+6.1f}%   "
              f"{freq / 1e6:7.3f} MHz {(freq / m_freq - 1) * 100:+6.1f}%   "
              f"{sum(errs):.3f}")
    if rows:
        rows.sort()
        best = rows[0]
        print(f"\nbest match: {best[1]} -- trip {best[2]:.3f} V, gain {best[3]:.2f} V/V, "
              f"ring {best[4] / 1e6:.3f} MHz")
        print("One chip is one sample, and this says nothing about the shuttle as a whole.")


if __name__ == "__main__":
    main()
