#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check an ngspice batch-mode log of examples/diffamp/tb_diffamp.sch
against the reference measurements in examples/diffamp/README.md, last
measured 2026-08-29 at cprobe=10p (with rprobe=10meg):

    as drawn   base 2.012V   +40mV -> 2.744V   -40mV -> 1.237V
    as routed  base 2.018V   +40mV -> 2.769V   -40mV -> 1.227V

The as-drawn column moved on 2026-08-29 with the model-binning fix (see
CLAUDE.md's trap list): the ideal library was handing sky130 a width
expression naming its own `w` parameter, which selected the wrong model
bin. The as-routed column is unchanged to the millivolt, because the
routed decks write literal widths and were never affected.

They moved once before, on 2026-08-28, with the bias-reference correction:
the tail bank now draws the 400 uA that tail=4 means on silicon, where the
old ideal model gave it 200 uA. See that README's "The bias-reference
correction".

Run by `sh tools/check_example_sim.sh diffamp`, which
.github/workflows/spice-regression.yml runs on every push alongside the
inverter, ring, SR latch, OTA follower and current source checks.

Each example guards something the others cannot. The inverter is
pad-and-load dominated and the ring is switch-matrix dominated, but both
are digital edges -- they say nothing about whether the routed model still
gets a *bias point* right. This one does: the diff amp only works at all
if the tail bank and the PMOS mirror are both sitting in saturation, so a
device-library or routing change that quietly shifted an operating point
would show up here as a moved `base` voltage long before it moved an edge
rate.

The gains are computed here rather than read from the log's own
`gain_*` prints, because `vout_*` are plain `meas` results with one value
per line, which is a format worth depending on; a multi-vector `print` is
not.

The +-5% band matches tools/check_inverter_sim.py and
tools/check_ring_sim.py, and the same reasoning applies -- see the note
there. If an upstream image update does shift a result past the band,
re-measure deliberately and update the numbers here and in
examples/diffamp/README.md together, rather than widening the band.

The reading and comparing is tools/simcheck.py; what lives here is the
numbers, the derived gains, and what a missing measurement means for this
circuit.

The four vout_*_pos/neg references are deliberately NOT in the README:
they are the raw endpoints of the +-40mV step, and what the README
publishes is the base voltage and the gain computed from them. Do not go
looking for them in the table.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import simcheck  # noqa: E402

# Volts. The measure names are tb_diffamp.sch's own. Only the two _base
# values appear in the README; the four step endpoints are intermediates
# the gain is computed from (see the note above).
REFERENCE_V = {
    "vout_drawn_base": 2.012,
    "vout_drawn_pos": 2.744,
    "vout_drawn_neg": 1.237,
    "vout_routed_base": 2.018,
    "vout_routed_pos": 2.769,
    "vout_routed_neg": 1.227,
}
# The differential step tb_diffamp.sch applies, in volts: PWL takes ua1 from
# 1.5V to 1.54V and then to 1.46V, against ua2 held at 1.5V.
STEP_V = 0.04
TOLERANCE = 0.05
# How far the as-drawn and as-routed gains may differ from each other before
# this is a real finding rather than rounding. The README measures 3%: the
# two branches share a bias point now, and what is left is the ideal
# tail/mirror models against the routed branch's real diff_n and mirror_p.
BRANCH_AGREEMENT = 0.05


def _v(x: float) -> str:
    return f"{x:.3f}V"


def main() -> int:
    log_path, text = simcheck.read_log("check_diffamp_sim.py")

    values = simcheck.measurements(
        text, REFERENCE_V, log_path,
        hint="The ngspice run likely errored before reaching the tran "
             "analysis, or the measurement reported 'failed' instead of a "
             "number.",
    )
    if values is None:
        return 1

    ok = simcheck.compare_relative(values, REFERENCE_V, TOLERANCE, fmt=_v)

    gains = {}
    for branch in ("drawn", "routed"):
        base = values[f"vout_{branch}_base"]
        gains[f"{branch}_pos"] = (values[f"vout_{branch}_pos"] - base) / STEP_V
        gains[f"{branch}_neg"] = (base - values[f"vout_{branch}_neg"]) / STEP_V
    for name, gain in gains.items():
        print(f"gain_{name}: {gain:.2f} V/V")

    # Structural, and it survives the reference numbers drifting: at DC no
    # current flows into a capacitor, so the pad's and the switch matrix's
    # series resistance drop no voltage. Everything the routed model adds is
    # resistance and capacitance, so a *settled* gain must come out the same
    # either way -- the matrix costs this circuit bandwidth, not gain. Two
    # branches that disagree mean something has changed the routed operating
    # point itself, which is a much bigger deal than a shifted number.
    for side in ("pos", "neg"):
        drawn, routed = gains[f"drawn_{side}"], gains[f"routed_{side}"]
        if abs(routed - drawn) > BRANCH_AGREEMENT * abs(drawn):
            print(
                f"FAIL: the as-drawn and as-routed {side} gains should settle "
                f"to the same value (within {BRANCH_AGREEMENT:.0%}), because a "
                f"settled gain is unaffected by the series resistance and "
                f"capacitance the routed model adds -- got "
                f"{drawn:.2f} V/V drawn against {routed:.2f} V/V routed."
            )
            ok = False

    # Also structural: the whole example depends on the output sitting in the
    # amplifier's linear region, not pinned at a rail. A railed output still
    # produces numbers, and they would look like a collapsed gain rather than
    # like the biasing failure they actually are.
    for branch in ("drawn", "routed"):
        base = values[f"vout_{branch}_base"]
        if not 0.3 <= base <= 3.0:
            print(
                f"FAIL: the as-{branch} output sits at {base:.3f}V with both "
                f"inputs equal, which is at or near a supply rail (VGND=0, "
                f"VAPWR=3.3). The tail bank or the PMOS mirror is no longer "
                f"biased into saturation, so this is not measuring gain at all."
            )
            ok = False

    return simcheck.verdict(
        ok, subject="the differential amplifier", readme="examples/diffamp/README.md",
        causes="device library rebuild, routing change, a different circuit "
               "in diffamp.sch, PDK/tool update",
    )


if __name__ == "__main__":
    raise SystemExit(main())
