#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check an ngspice batch-mode log of
examples/currentsource/tb_currentsource.sch against the reference
measurements in examples/currentsource/README.md, last measured 2026-08-28 at Vsweep=1.65V, ratio=2,
ibias_amps=100u:

    psource_a (source)   +209.9 uA drawn   +209.3 uA routed   (+200 uA ideal)
    nsink_a   (sink)     -201.3 uA drawn   -203.9 uA routed   (-200 uA ideal)

Run by `sh tools/sim/check_example_sim.sh currentsource`, which
.github/workflows/spice-regression.yml runs on every push alongside the
inverter, ring, diff amp, SR latch and OTA follower checks.

What this one guards that the others cannot. It is the only example that
measures a *current* rather than a voltage, and the only one whose answer
is set entirely by the chip's single bias reference. That reference is
easy to break quietly in both directions, and has been: before
2026-08-28 every mirror symbol carried its own private reference diode,
so N devices split the one reference current N ways (two
`mosbius_nsink ratio=2` measured -99 uA each where -200 uA was right),
while `mosbius_psource`'s PMOS diode sitting on the NMOS-referenced node
formed a conducting chain across the supply and read +501/-707 uA. Every
one of those faults produces a perfectly plausible-looking simulation of
some other circuit. This check is the one that says the number is wrong.

It also guards the "two bias sources, one per instance" rule: feeding
both instances from a single source puts two chips in parallel on one
reference and the routed leg reads 482 uA instead of 209.

The currents are read from the log's `meas` results, one value per line,
rather than from the `print i_source_drawn i_source_routed d_source`
line, because a multi-vector `print` is not a format worth depending on.
Same reasoning as tools/sim/check_diffamp_sim.py.

The +-5% band matches the other checks in tools/. If an upstream image
update does shift a result past it, re-measure deliberately and update
the numbers here and in examples/currentsource/README.md together, rather
than widening the band.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import simcheck  # noqa: E402

# Amps, from the README table. The measure names are
# tb_currentsource.sch's own; the signs are the ammeters' own, and are
# what the deck actually prints (a source pushes current out of the pin, a
# sink pulls it in).
REFERENCE_A = {
    "i_source_drawn": +209.9e-6,
    "i_source_routed": +209.3e-6,
    "i_sink_drawn": -201.3e-6,
    "i_sink_routed": -203.9e-6,
}
TOLERANCE = 0.05

# What the hardware's encoding promises: ratio=2 against ibias_amps=100u.
# The band here is wide on purpose -- this is not a precision check, it is
# the "is the bias reference intact at all" check, and every fault it
# exists to catch missed by 2x or more.
IDEAL_A = 200e-6
IDEAL_TOLERANCE = 0.25

# How far the as-drawn and as-routed legs may differ from each other. The
# README measures 1.3%.
BRANCH_AGREEMENT = 0.05


def _ua(a: float) -> str:
    return f"{a * 1e6:+.1f}uA"


def main() -> int:
    log_path, text = simcheck.read_log("check_currentsource_sim.py")

    values = simcheck.measurements(
        text, REFERENCE_A, log_path,
        hint="The ngspice run likely errored before reaching the dc sweep, "
             "or the measurement reported 'failed' instead of a number.",
    )
    if values is None:
        return 1

    ok = simcheck.compare_relative(values, REFERENCE_A, TOLERANCE, fmt=_ua)

    # Structural, and it survives the reference numbers drifting: `ratio=2`
    # means two times the reference current, on silicon and in the ideal
    # model alike. A leg that is off by a factor rather than by a percent is
    # the bias reference being split, shorted or absent -- see the module
    # docstring for the three ways that has actually happened here.
    for name, measured in values.items():
        if not (1 - IDEAL_TOLERANCE) <= abs(measured) / IDEAL_A <= (1 + IDEAL_TOLERANCE):
            print(
                f"FAIL: {name} is {measured * 1e6:+.1f}uA, which is "
                f"{abs(measured) / IDEAL_A:.2f}x the {IDEAL_A * 1e6:.0f}uA that "
                f"ratio=2 at ibias_amps=100u means. That is a broken bias "
                f"reference, not a shifted operating point: check that the "
                f"sheet has exactly one mosbius_bias, and that each instance "
                f"has its own Ibias source."
            )
            ok = False

    # A source that sinks, or a sink that sources, is a mirror wired to the
    # wrong rail -- and the magnitude can still look right while it happens.
    for name, measured in values.items():
        expected_sign = 1 if "source" in name else -1
        if measured * expected_sign <= 0:
            direction = "out of" if expected_sign > 0 else "into"
            print(
                f"FAIL: {name} is {measured * 1e6:+.1f}uA. A "
                f"{'psource' if expected_sign > 0 else 'nsink'} leg must push "
                f"current {direction} the pin, so this sign is backwards."
            )
            ok = False

    # Also structural: a current mirror's output current is set by its gate
    # voltage, and the switch matrix's series resistance changes the voltage
    # at the pin, not the current through it. So the two branches must agree
    # -- the matrix costs this circuit speed, not accuracy, the same result
    # the diff amp gives for gain and the OTA follower for offset.
    for leg in ("source", "sink"):
        drawn, routed = values[f"i_{leg}_drawn"], values[f"i_{leg}_routed"]
        if abs(routed - drawn) > BRANCH_AGREEMENT * abs(drawn):
            print(
                f"FAIL: the as-drawn and as-routed {leg} legs should deliver "
                f"the same current (within {BRANCH_AGREEMENT:.0%}), because a "
                f"mirror's output current is set by its gate voltage and the "
                f"routed model only adds series resistance -- got "
                f"{drawn * 1e6:+.1f}uA drawn against {routed * 1e6:+.1f}uA "
                f"routed."
            )
            ok = False

    return simcheck.verdict(
        ok, subject="the current source",
        readme="examples/currentsource/README.md",
        causes="device library rebuild, routing change, a different circuit "
               "in currentsource.sch, PDK/tool update",
    )


if __name__ == "__main__":
    raise SystemExit(main())
