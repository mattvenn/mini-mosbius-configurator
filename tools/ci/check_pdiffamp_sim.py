#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check an ngspice batch-mode log of examples/pdiffamp/tb_pdiffamp.sch
against the reference measurements in examples/pdiffamp/README.md, last
measured 2026-08-29 at cprobe=10p (with rprobe=10meg):

    as drawn   base 1.112V   +10mV -> 1.328V   -10mV -> 0.904V
    as routed  base 1.121V   +10mV -> 1.339V   -10mV -> 0.910V

This is the polarity mirror of examples/diffamp: a PMOS pair with an NMOS
current-mirror load, where that one is an NMOS pair with a PMOS load. The
quiescent output sits one load Vgs *above* VGND here, where the diff amp's
sits one Vgs below VAPWR, and it is the only example that exercises
mosbius_ptail at all.

The step is +-10mV, not the diff amp's +-40mV, because this amplifier's
output has less room below it: at 1.12V a -40mV step takes it to within
250mV of VGND, where it is compressing rather than amplifying, and the
chord gain would then be measuring the compression.

Run by `sh tools/ci/check_example_sim.sh pdiffamp`, which
.github/workflows/spice-regression.yml runs alongside the inverter, ring,
SR latch, diff amp, OTA follower and current source checks.

What this one guards that the NMOS diff amp does not: the PMOS tail bank
(ctrl_dpp_tail) and the pdiffpair halves used as a real pair. A device
library rebuild that got the PMOS side wrong would leave examples/diffamp
passing.

The gains are computed here rather than read from the log's own `gain_*`
prints, because `vout_*` are plain `meas` results with one value per line,
which is a format worth depending on; a multi-vector `print` is not.

The reading and comparing is tools/ci/simcheck.py; what lives here is the
numbers, the derived gains, and what a missing measurement means for this
circuit.

The four vout_*_pos/neg references are deliberately NOT in the README:
they are the raw endpoints of the +-10mV step, and what the README
publishes is the base voltage and the gain computed from them. Do not go
looking for them in the table.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import simcheck  # noqa: E402

# Volts. The measure names are tb_pdiffamp.sch's own. Only the two _base
# values appear in the README; the four step endpoints are intermediates
# the gain is computed from (see the note above).
REFERENCE_V = {
    "vout_drawn_base": 1.112,
    "vout_drawn_pos": 1.328,
    "vout_drawn_neg": 0.904,
    "vout_routed_base": 1.121,
    "vout_routed_pos": 1.339,
    "vout_routed_neg": 0.910,
}
# The differential step tb_pdiffamp.sch applies, in volts. It is +-10mV
# rather than the NMOS diff amp's +-40mV because this output sits low by
# construction, and a bigger step compresses it against VGND.
STEP_V = 0.01
TOLERANCE = 0.05
# How far the as-drawn and as-routed gains may differ from each other before
# this is a real finding rather than rounding. The README measures ~1%.
BRANCH_AGREEMENT = 0.05


def _v(x: float) -> str:
    return f"{x:.3f}V"


def main() -> int:
    log_path, text = simcheck.read_log("check_pdiffamp_sim.py")

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
    # either way -- the matrix costs this circuit bandwidth, not gain.
    #
    # This check earned its keep on the day the example was written: the two
    # branches came out 21.5 against 14.2 V/V, and the cause was that the
    # ideal library passed the sky130 model a width expression naming its own
    # parameter `w`, which collides with the model subcircuit's own `w` and
    # selected the wrong bin. See CLAUDE.md's trap list.
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
    # like the biasing failure they actually are. The window is tighter below
    # than the diff amp's because this output sits low by construction -- one
    # NMOS load Vgs above VGND.
    for branch in ("drawn", "routed"):
        base = values[f"vout_{branch}_base"]
        if not 0.3 <= base <= 3.0:
            print(
                f"FAIL: the as-{branch} output sits at {base:.3f}V with both "
                f"inputs equal, which is at or near a supply rail (VGND=0, "
                f"VAPWR=3.3). The PMOS tail bank or the NMOS mirror is no "
                f"longer biased into saturation, so this is not measuring "
                f"gain at all."
            )
            ok = False

    return simcheck.verdict(
        ok, subject="the PMOS differential amplifier",
        readme="examples/pdiffamp/README.md",
        causes="device library rebuild, routing change, a different circuit "
               "in pdiffamp.sch, PDK/tool update",
    )


if __name__ == "__main__":
    raise SystemExit(main())
