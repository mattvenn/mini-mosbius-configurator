#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check an ngspice batch-mode log of examples/srlatch/tb_srlatch.sch
against the reference measurements in examples/srlatch/README.md, last
measured 2026-08-29 at cprobe=10p (with rprobe=10meg):

    qd_after_set   =  3.300V     qr_after_set   =  3.110V
    qd_after_reset = -0.0000V    qr_after_reset = -0.0026V
    treset_drawn   =  1.77ns     treset_routed  = 10.94ns

treset_drawn was 18.79ns until 2026-08-29, when XM5/XM6 went from w=1 to
w=4 on the sheet to match the fixed geometry of the diff-pair halves they
land on. The bitstream is unchanged by that -- there were never width bits
behind the request -- so nothing about the chip or its measurements moved.

Run by `sh tools/ci/check_example_sim.sh srlatch`, which
.github/workflows/spice-regression.yml runs on every push alongside the
inverter, ring, both diff amps, OTA follower and current source
checks.

What this one guards that the others cannot is *state*. The inverter, the
ring and the diff amp are all memoryless: drive them the same way twice
and they do the same thing. A latch holds a value after the pulse that set
it ends, which depends on the cross-coupled feedback surviving everything
the routed model adds -- so a routing or device-library change that made
the matrix leaky enough to lose the stored state would pass all three of
the others and fail here.

The +-5% band on the two timings matches tools/ci/check_inverter_sim.py and
tools/ci/check_ring_sim.py; see the note there for why it is 5% and not
wider. The two after-reset levels get an absolute band instead: their
references are ~0V and 2.6mV, where a percentage of the reference is
meaningless.

This script does assert "routed is slower than drawn", and only became
able to on 2026-08-29. Until then the sheet drew XM5 and XM6 at w=1 where
the differential-pair halves they land on are fixed at w=4 in silicon, so
the as-drawn deck reset through write transistors four times too weak and
came out *slower* than the routed one (18.79ns against 10.94ns) -- an
inverted ordering that was a property of the drawing, not of the matrix.
Asserting the physical ordering against a deck that does not model the
physical device would have failed for the right reason and been useless.
The sheet draws w=4 now, treset_drawn is 1.77ns, and the ordering is the
one every other example shows, so the check is worth having: it is what
would catch the routed matrix quietly getting faster than ideal wiring.
See examples/srlatch/README.md for the reset timing measured on silicon.

The reading and comparing is tools/ci/simcheck.py; what lives here is the
numbers, the units, and what a missing measurement means for this circuit
-- which for the treset_* pair is the longest such explanation in the
repo, and the reason `hint` is per-example rather than generic.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import simcheck  # noqa: E402

REFERENCE_HIGH_V = {"qd_after_set": 3.300, "qr_after_set": 3.110}
# Volts. Both references are within a few mV of ground, so this is an
# absolute band, not a fraction of the reference.
REFERENCE_LOW_V = {"qd_after_reset": -0.0000, "qr_after_reset": -0.0026}
LOW_ABS_TOLERANCE_V = 0.05
# Nanoseconds, from RESET crossing 1.65V rising to the output crossing
# 1.65V falling.
REFERENCE_NS = {"treset_drawn": 1.77, "treset_routed": 10.94}
TOLERANCE = 0.05
# Volts. How far apart the set and reset levels must stay for the latch to
# be storing anything at all.
MIN_STATE_SEPARATION_V = 3.0

# What a missing measurement means here. This is long because the two known
# causes are both specific and both expensive to rediscover; a generic
# "the run errored" would be worth almost nothing on this circuit.
MISSING_HINT = (
    "Either the ngspice run errored before reaching the tran analysis, or "
    "the measurement reported 'failed' rather than a number -- for the "
    "treset_* pair there are two known causes, both of which print "
    "'trig(TARG) : out of interval'.\n\n"
    "  1. The as-drawn latch never set, so there is no falling edge to "
    "time. Check qd_after_set in the log: near 0 V means this. It is what "
    "happened on 2026-08-29 with XM5/XM6 still drawn w=1 against diff-pair "
    "halves fixed at w=4 in silicon -- write transistors four times too "
    "weak, which the wrong model bin had been masking by over-strengthening "
    "every as-drawn device. The sheet draws them w=4 now, so seeing this "
    "again means something has reopened that gap: check the router's "
    "warnings, which should be silent.\n"
    "  2. A load big enough to stretch the reset edge past the measurement "
    "window, which is what cprobe=100p used to do."
)


def _v(x: float) -> str:
    return f"{x:.3f}V"


def _v4(x: float) -> str:
    return f"{x:.4f}V"


def _ns(x: float) -> str:
    return f"{x:.2f}ns"


def main() -> int:
    log_path, text = simcheck.read_log("check_srlatch_sim.py")

    names = list(REFERENCE_HIGH_V) + list(REFERENCE_LOW_V) + list(REFERENCE_NS)
    values = simcheck.measurements(text, names, log_path, hint=MISSING_HINT)
    if values is None:
        return 1
    for name in REFERENCE_NS:
        values[name] *= 1e9  # seconds -> ns

    ok = simcheck.compare_relative(values, REFERENCE_HIGH_V, TOLERANCE, fmt=_v)
    ok = simcheck.compare_absolute(
        values, REFERENCE_LOW_V, LOW_ABS_TOLERANCE_V, fmt=_v4) and ok
    ok = simcheck.compare_relative(values, REFERENCE_NS, TOLERANCE, fmt=_ns) and ok

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

    # Structural: ideal wiring cannot be slower than the same circuit with
    # the switch matrix's series resistance and capacitance added to it.
    # This check was impossible while the sheet drew XM5/XM6 at w=1 -- see
    # the note at the top -- and it is the one that would catch that gap
    # reopening, or a routed model that has stopped adding anything.
    if values["treset_drawn"] >= values["treset_routed"]:
        print(
            f"FAIL: the as-drawn reset ({values['treset_drawn']:.2f}ns) is "
            f"not faster than the as-routed one "
            f"({values['treset_routed']:.2f}ns). Ideal wiring should be the "
            f"quicker of the two, since the routed branch adds series "
            f"resistance and pad capacitance and nothing else. The known "
            f"cause of an inversion here is the as-drawn deck simulating "
            f"weaker devices than the chip builds: check the router's "
            f"warnings for a dropped w= on XM5/XM6."
        )
        ok = False

    return simcheck.verdict(
        ok, subject="the SR latch", readme="examples/srlatch/README.md",
        causes="device library rebuild, routing change, a different circuit "
               "in srlatch.sch, PDK/tool update",
    )


if __name__ == "__main__":
    raise SystemExit(main())
