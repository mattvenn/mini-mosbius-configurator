#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Draw examples/ringosc's output as drawn, as routed, and as
measured on silicon.

Inputs, all produced by other commands so this script only draws:

    build/ring_tb_out_drawn.txt      from tb_ring.sch's two tran runs
    build/ring_tb_out_routed.txt     (tools/sim/check_example_sim.sh ring runs them)
    build/ring_silicon_trace.json    from tools/ad3/measure_ring_ad3.py

Writes examples/ringosc/ring_comparison.png and prints the table.

**Two panels, on two timebases, like the testbench's two `tran` runs.**
As drawn the ring runs at 2.289 GHz and the other two near 40 MHz, a
factor of 53, so the drawn trace gets its own panel. As routed and on
silicon are 11% apart, which one axis holds comfortably, so they overlay
-- and an 11% period difference is something you can see.

**The measured waveform is reconstructed by folding, not plotted raw.**
The Analog Discovery samples at 100 MS/s, only 2.5 points per period at
40 MHz, so a raw plot is an aliased zigzag. But the oscillation is stable
across all 6474 periods in a capture, so folding every sample back into
one period at the measured frequency fills that period densely -- the same
trick a sampling scope uses. What is drawn is 16384 real samples, each at
its true phase; no interpolation, no averaging.

**Amplitude is not comparable and is not shown as such.** At ~40 MHz the
flywire leads roll off by an unknown factor, so the measured trace is
scaled to the routed one's swing purely so both fit the panel, and the
raw pk-pk is stated on the figure instead.

ngspice writes adaptive time steps, so the simulated traces are
interpolated onto a uniform grid before transforming.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def load_txt(path: Path):
    ts, vs = [], []
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 2:
            ts.append(float(parts[0]))
            vs.append(float(parts[1]))
    return np.array(ts), np.array(vs)


def freq_from_trace(t, v):
    a = v - v.mean()
    sign = np.sign(a)
    crossings = np.where((sign[:-1] < 0) & (sign[1:] >= 0))[0]
    if len(crossings) < 3:
        return float("nan")
    span = t[crossings[-1]] - t[crossings[0]]
    return (len(crossings) - 1) / span


def window(t, v, periods, hz):
    """the last `periods` periods, so any startup transient is off-screen"""
    if not np.isfinite(hz):
        return t, v
    length = periods / hz
    keep = t >= (t[-1] - length)
    return t[keep] - t[keep][0], v[keep]


def main() -> None:
    build = Path("build")
    needed = ["ring_tb_out_drawn.txt", "ring_tb_out_routed.txt", "ring_silicon_trace.json"]
    missing = [f for f in needed if not (build / f).exists()]
    if missing:
        raise SystemExit(
            "missing input: " + ", ".join(f"build/{f}" for f in missing) + "\n\n"
            "  the two .txt files come from tb_ring.sch's wrdata -- run\n"
            "  tools/sim/check_example_sim.sh ring inside the IIC-OSIC-TOOLS container.\n"
            "  build/ring_silicon_trace.json comes from the bench:\n"
            "  python3 tools/ad3/measure_ring_ad3.py"
        )

    dt, dv = load_txt(build / "ring_tb_out_drawn.txt")
    rt, rv = load_txt(build / "ring_tb_out_routed.txt")
    bench = json.loads((build / "ring_silicon_trace.json").read_text())
    bv = np.array(bench["v"])
    bt = np.arange(len(bv)) / bench["rate"]

    # The simulated figures are the testbench's own .meas results, taken on
    # the loop nodes. Do not re-derive them from these traces: out_drawn and
    # out_routed are the *buffered* output, one inversion later, and a
    # frequency read there differs by a few percent -- which would put a
    # second, disagreeing pair of numbers next to the ones CI asserts.
    log = Path("build/ngspice_tb_ring.log")
    meas = {}
    if log.exists():
        for line in log.read_text().splitlines():
            for key in ("freq_drawn", "freq_routed"):
                if line.strip().startswith(key):
                    meas[key] = float(line.split("=")[1].split()[0])
    f_silicon = freq_from_trace(bt, bv)
    f_drawn = meas.get("freq_drawn", float("nan"))
    f_routed = meas.get("freq_routed", float("nan"))
    print(f"{'as drawn':12s} {f_drawn / 1e6:9.1f} MHz   (tb_ring.sch .meas, loop node)")
    print(f"{'as routed':12s} {f_routed / 1e6:9.2f} MHz   (tb_ring.sch .meas, loop node)")
    print(f"{'on silicon':12s} {f_silicon / 1e6:9.3f} MHz   (ua3, zero crossings)"
          f"\n{'':12s} {'':9s}        as routed is {(f_routed / f_silicon - 1) * 100:+.1f}%, "
          f"as drawn is x{f_drawn / f_silicon:.0f}")

    def refine(t, v, hz, span=2e-3, steps=4001):
        """zoom-DFT around `hz`: correlate against a complex exponential on a
        fine frequency grid and keep the strongest. Folding 6000+ periods
        needs the frequency to about 1e-6 relative -- an FFT bin or a
        zero-crossing count is 1e-4, and the leftover phase drift smears the
        folded waveform into a band."""
        a = v - v.mean()
        grid = hz * (1 + np.linspace(-span, span, steps))
        power = [abs(np.sum(a * np.exp(-2j * np.pi * f * t))) for f in grid]
        return float(grid[int(np.argmax(power))])

    FOLD_PERIODS = 300

    def fold(t, v, hz, periods=FOLD_PERIODS):
        """Draw every sample on top of every other, one period wide: take each
        sample's time modulo the period and plot against the remainder. A
        scope with persistence on and a trigger every cycle shows the same
        thing. With 2.5 samples per period but hundreds of periods, each cycle
        lands at a different phase and together they fill the period in.

        Only the first `periods` cycles are folded, and that is a real
        trade-off rather than a detail. More cycles fill the period more
        densely, but a free-running ring has nothing holding its frequency, so
        the longer the window the more of its own wander gets stacked into one
        period: measured on this chip the band at mid-level is 3.1% of a period
        over 5 us, 3.3% over 25 us and 9.0% over 164 us, while the fitted
        frequency stays put to 1e-5. So the width is the oscillator, not the
        estimate -- and 300 periods keeps it thin while still putting ~750
        samples across the period."""
        keep = t <= t[0] + periods / hz
        t, v = t[keep], v[keep]
        period = 1.0 / hz
        phase = np.mod(t, period)
        order = np.argsort(phase)
        return phase[order], v[order]

    def last_periods(t, v, hz, periods=2.2):
        keep = t >= (t[-1] - periods / hz)
        return t[keep] - t[keep][0], v[keep]

    fig, (drawn_ax, routed_ax) = plt.subplots(1, 2, figsize=(11.5, 4.2))

    dtw, dvw = last_periods(dt, dv, f_drawn)
    drawn_ax.plot(dtw * 1e12, dvw, lw=1.4, color="#4C72B0")
    drawn_ax.set_xlabel("time (ps)")
    drawn_ax.set_ylabel("ua3, buffered output (V)")
    drawn_ax.set_title(f"as drawn -- {f_drawn / 1e9:.3f} GHz", fontsize=10)
    drawn_ax.grid(alpha=0.3)

    rtw, rvw = last_periods(rt, rv, f_routed)
    routed_ax.plot(rtw * 1e9, rvw, lw=1.5, color="#DD8452",
                   label=f"as routed -- {f_routed / 1e6:.2f} MHz")

    # fold the bench capture, then scale it into the routed trace's swing:
    # the leads' roll-off makes the captured amplitude meaningless, the
    # period is what is being compared
    # refine on the same window that gets folded, not on the whole capture
    fold_window = bt <= bt[0] + 300 / f_silicon
    f_fold = refine(bt[fold_window], bv[fold_window], f_silicon, span=5e-4)
    print(f"{'':12s} folding at {f_fold / 1e6:.6f} MHz "
          f"({(f_fold / f_silicon - 1) * 1e6:+.0f} ppm from the zero-crossing estimate)")
    ph, pv = fold(bt, bv, f_fold)
    pv = pv - pv.mean()
    pv = pv * ((rvw.max() - rvw.min()) / (pv.max() - pv.min())) + rvw.mean()
    for cycle in (0, 1, 2):
        offset = cycle / f_fold
        keep = (ph + offset) <= rtw[-1]
        routed_ax.plot((ph[keep] + offset) * 1e9, pv[keep], ".", ms=1.6, color="#7D5BBE",
                       label=f"on silicon -- {f_silicon / 1e6:.2f} MHz" if cycle == 0 else None)
    routed_ax.set_xlabel("time (ns)")
    routed_ax.set_ylabel("ua3, buffered output (V)")
    routed_ax.set_title("as routed against silicon -- 11% apart, and it shows", fontsize=10)
    routed_ax.grid(alpha=0.3)
    routed_ax.legend(fontsize=9, loc="upper right")
    routed_ax.text(0.5, -0.28,
                   f"silicon trace folded from 300 periods at {f_fold / 1e6:.4f} MHz, then scaled "
                   f"into the routed swing: the captured\n{bv.max() - bv.min():.2f} V pk-pk is the "
                   "leads' roll-off at 40 MHz, not the chip's output. The band's width is the "
                   "ring's own frequency wander.",
                   transform=routed_ax.transAxes, fontsize=7.5, color="dimgrey",
                   ha="center", va="top")

    out = Path("examples/ringosc/ring_comparison.png")
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(out, dpi=120)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
