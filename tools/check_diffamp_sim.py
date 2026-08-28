#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check an ngspice batch-mode log of examples/diffamp/tb_diffamp.sch
against the reference measurements in examples/diffamp/README.md ("Step
response and settling"), last measured 2026-08-28 at cload=10p:

    as drawn   base 1.985V   +40mV -> 2.714V   -40mV -> 1.222V
    as routed  base 2.020V   +40mV -> 2.771V   -40mV -> 1.228V

These moved on 2026-08-28 with the bias-reference correction: the tail
bank now draws the 400 uA that tail=4 means on silicon, where the old
ideal model gave it 200 uA. See that README's "The bias-reference
correction".

Run by tools/check_diffamp_sim.sh, which
.github/workflows/spice-regression.yml runs once a month alongside the
inverter, ring and SR latch checks.

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
"""

from __future__ import annotations

import re
import sys

# Volts, from the README table. The measure names are tb_diffamp.sch's own.
REFERENCE_V = {
    "vout_drawn_base": 1.985,
    "vout_drawn_pos": 2.714,
    "vout_drawn_neg": 1.222,
    "vout_routed_base": 2.020,
    "vout_routed_pos": 2.771,
    "vout_routed_neg": 1.228,
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


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_diffamp_sim.py <ngspice-log>", file=sys.stderr)
        return 2

    log_path = sys.argv[1]
    text = open(log_path).read()

    values: dict[str, float] = {}
    for name in REFERENCE_V:
        m = re.search(rf"^\s*{name}\s*=\s*([0-9.eE+-]+)", text, re.MULTILINE)
        if not m:
            print(
                f"FAIL: no '{name}' measurement found in {log_path} -- the "
                f"ngspice run likely errored before reaching the tran "
                f"analysis, or the measurement reported 'failed' instead of "
                f"a number. Tail of the log:\n"
                + "\n".join(text.splitlines()[-20:])
            )
            return 1
        values[name] = float(m.group(1))

    ok = True
    for name, reference in REFERENCE_V.items():
        measured = values[name]
        low, high = sorted((reference * (1 - TOLERANCE), reference * (1 + TOLERANCE)))
        in_range = low <= measured <= high
        ok = ok and in_range
        status = "ok" if in_range else "OUT OF RANGE"
        print(
            f"{name}: {measured:.3f}V "
            f"(reference {reference}V, expected {low:.3f}-{high:.3f}V) -- {status}"
        )

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

    if not ok:
        print(
            "\nSomething about the differential amplifier's simulated "
            "behavior has changed. If this is an intentional change (device "
            "library rebuild, routing change, a different circuit in "
            "diffamp.sch, PDK/tool update), update the reference numbers "
            "here and in examples/diffamp/README.md together; otherwise treat "
            "this as a real regression."
        )
        return 1

    print(
        "\nOK -- differential amplifier as-drawn/as-routed simulation matches "
        "the reference measurements."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
