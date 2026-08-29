#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check an ngspice batch-mode log of examples/srlatch/tb_srlatch.sch
against the reference measurements in examples/srlatch/README.md ("Load
capacitors in tb_srlatch.sch"), last measured 2026-08-27 at cprobe=10p (with rprobe=10meg):

    qd_after_set   =  3.300V     qr_after_set   =  3.110V
    qd_after_reset = -0.0000V    qr_after_reset = -0.0026V
    treset_drawn   = 18.79ns     treset_routed  = 10.94ns

Run by tools/check_srlatch_sim.sh, which
.github/workflows/spice-regression.yml runs once a month alongside the
inverter, ring, diff amp, OTA follower and current source checks.

What this one guards that the others cannot is *state*. The inverter, the
ring and the diff amp are all memoryless: drive them the same way twice
and they do the same thing. A latch holds a value after the pulse that set
it ends, which depends on the cross-coupled feedback surviving everything
the routed model adds -- so a routing or device-library change that made
the matrix leaky enough to lose the stored state would pass all three of
the others and fail here.

The +-5% band on the two timings matches tools/check_inverter_sim.py and
tools/check_ring_sim.py; see the note there for why it is 5% and not
wider. The two after-reset levels get an absolute band instead: their
references are ~0V and 2.6mV, where a percentage of the reference is
meaningless.

There is deliberately no "routed must be slower than drawn" check here,
unlike the inverter and ring scripts. treset_routed does come out faster
(10.94ns against 18.79ns), and as of 2026-08-29 that is explained rather
than mysterious: XM5 and XM6 are drawn w=1 where the differential-pair
halves they land on are fixed at w=4 in silicon, so the as-drawn deck
resets through write transistors four times too weak. Widen those two and
treset_drawn becomes 1.82ns, faster than the routed 10.94ns, which is the
ordering every other example shows. The check stays absent because the
committed sheet still draws w=1, so the ordering it produces really is
inverted -- asserting the physical ordering against a deck that does not
model the physical device would fail for the right reason and be useless.
See examples/srlatch/README.md, "Timing the reset".
"""

from __future__ import annotations

import re
import sys

# Volts. The stored output level once SET has driven it high.
REFERENCE_HIGH_V = {"qd_after_set": 3.300, "qr_after_set": 3.110}
# Volts. Both references are within a few mV of ground, so this is an
# absolute band, not a fraction of the reference.
REFERENCE_LOW_V = {"qd_after_reset": -0.0000, "qr_after_reset": -0.0026}
LOW_ABS_TOLERANCE_V = 0.05
# Nanoseconds, from RESET crossing 1.65V rising to the output crossing
# 1.65V falling.
REFERENCE_NS = {"treset_drawn": 18.79, "treset_routed": 10.94}
TOLERANCE = 0.05
# Volts. How far apart the set and reset levels must stay for the latch to
# be storing anything at all.
MIN_STATE_SEPARATION_V = 3.0


def _measurement(text: str, name: str, log_path: str) -> float | None:
    m = re.search(rf"^\s*{name}\s*=\s*([0-9.eE+-]+)", text, re.MULTILINE)
    if m:
        return float(m.group(1))
    print(
        f"FAIL: no '{name}' measurement found in {log_path}. Either the "
        f"ngspice run errored before reaching the tran analysis, or the "
        f"measurement reported 'failed' rather than a number -- for the "
        f"treset_* pair there are two known causes, both of which print "
        f"'trig(TARG) : out of interval'.\n\n"
        f"  1. The as-drawn latch never set, so there is no falling edge to "
        f"time. This is the expected failure since 2026-08-29: XM5 and XM6 "
        f"are drawn w=1 where the diff-pair halves they land on are fixed at "
        f"w=4 in silicon (the router says so, as a WARNING), and once the "
        f"model-binning fix stopped over-strengthening every as-drawn device, "
        f"write transistors four times too weak stopped being able to flip "
        f"the cell. Check qd_after_set in the log: near 0 V means this. The "
        f"fix is w=1 -> w=4 on those two devices, which is a decision "
        f"TODO.md carries rather than a regression -- see "
        f"examples/srlatch/README.md, 'The as-drawn branch stopped working'.\n"
        f"  2. A load big enough to stretch the reset edge past the "
        f"measurement window, which is what cprobe=100p used to do.\n\n"
        f"Tail of the log:\n"
        + "\n".join(text.splitlines()[-20:])
    )
    return None


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_srlatch_sim.py <ngspice-log>", file=sys.stderr)
        return 2

    log_path = sys.argv[1]
    text = open(log_path).read()

    names = list(REFERENCE_HIGH_V) + list(REFERENCE_LOW_V) + list(REFERENCE_NS)
    values: dict[str, float] = {}
    for name in names:
        value = _measurement(text, name, log_path)
        if value is None:
            return 1
        values[name] = value
    for name in REFERENCE_NS:
        values[name] *= 1e9  # seconds -> ns

    ok = True

    for name, reference in REFERENCE_HIGH_V.items():
        measured = values[name]
        low, high = reference * (1 - TOLERANCE), reference * (1 + TOLERANCE)
        in_range = low <= measured <= high
        ok = ok and in_range
        print(
            f"{name}: {measured:.3f}V (reference {reference}V, expected "
            f"{low:.3f}-{high:.3f}V) -- {'ok' if in_range else 'OUT OF RANGE'}"
        )

    for name, reference in REFERENCE_LOW_V.items():
        measured = values[name]
        in_range = abs(measured - reference) <= LOW_ABS_TOLERANCE_V
        ok = ok and in_range
        print(
            f"{name}: {measured:.4f}V (reference {reference}V, expected "
            f"within +-{LOW_ABS_TOLERANCE_V}V of it) -- "
            f"{'ok' if in_range else 'OUT OF RANGE'}"
        )

    for name, reference in REFERENCE_NS.items():
        measured = values[name]
        low, high = reference * (1 - TOLERANCE), reference * (1 + TOLERANCE)
        in_range = low <= measured <= high
        ok = ok and in_range
        print(
            f"{name}: {measured:.2f}ns (reference {reference}ns, expected "
            f"{low:.2f}-{high:.2f}ns) -- {'ok' if in_range else 'OUT OF RANGE'}"
        )

    # Structural, and it survives the reference numbers drifting: this is
    # the property that makes the circuit a latch rather than a pair of
    # inverters. Both measurements are taken well after their pulse has
    # ended (110ns and 280ns, against pulses that end at 100ns and 260ns),
    # so a full-swing separation here means the state was still being held,
    # not merely driven.
    for branch, high_name, low_name in (
        ("drawn", "qd_after_set", "qd_after_reset"),
        ("routed", "qr_after_set", "qr_after_reset"),
    ):
        separation = values[high_name] - values[low_name]
        if separation < MIN_STATE_SEPARATION_V:
            print(
                f"FAIL: the as-{branch} latch is not holding a state. After "
                f"SET it reads {values[high_name]:.3f}V and after RESET "
                f"{values[low_name]:.3f}V, only {separation:.3f}V apart -- "
                f"both samples are taken after their pulse has already "
                f"ended, so a latch that stores anything should still be at "
                f"opposite rails, at least "
                f"{MIN_STATE_SEPARATION_V}V apart."
            )
            ok = False

    if not ok:
        print(
            "\nSomething about the SR latch's simulated behavior has "
            "changed. If this is an intentional change (device library "
            "rebuild, routing change, a different circuit in srlatch.sch, "
            "PDK/tool update), update the reference numbers here and in "
            "examples/srlatch/README.md together; otherwise treat this as a "
            "real regression."
        )
        return 1

    print(
        "\nOK -- SR latch as-drawn/as-routed simulation matches the reference "
        "measurements."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
