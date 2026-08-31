#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check an ngspice batch-mode log of examples/inverter/tb_inverter.sch
against the reference measurements in examples/inverter/README.md
(Table 1): trise_drawn=8.16ns, trise_routed=24.63ns,
last re-run 2026-08-29 at the probe defaults rprobe=10meg cprobe=10p
(a 10x passive probe -- the meter is part of the circuit, so it is
modelled in the testbench), on the routing the router produces
today.

Run by `sh tools/sim/check_example_sim.sh inverter` (the full
netlist/route/simulate/ngspice pipeline), which
.github/workflows/spice-regression.yml runs on every push alongside the
ring, diff amp, SR latch, OTA follower and current source checks.

The +-5% band is set by what actually varies: reltol=0.01 keeps repeat
runs stable to well under 0.1%, so the noise floor is far below this and
5% is room for a minor ngspice or PDK point release rather than for real
change. It was +-25% until 2026-08-28, which was wide enough to miss a
sizeable error in the pad or parasitic models while still passing; the
other three checks (tools/sim/check_ring_sim.py, tools/sim/check_diffamp_sim.py
and tools/sim/check_srlatch_sim.py) carry the same band and the same
reasoning.

The reading and comparing is tools/sim/simcheck.py; what lives here is the
numbers, the unit, and what a missing measurement means for this circuit.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import simcheck  # noqa: E402

REFERENCE_NS = {"trise_drawn": 8.16, "trise_routed": 24.63}
TOLERANCE = 0.05


def _ns(v: float) -> str:
    return f"{v:.2f}ns"


def main() -> int:
    log_path, text = simcheck.read_log("check_inverter_sim.py")

    values = simcheck.measurements(
        text, REFERENCE_NS, log_path, scale=1e9,   # seconds -> ns
        hint="The ngspice run likely errored before reaching the tran "
             "analysis.",
    )
    if values is None:
        return 1

    ok = simcheck.compare_relative(values, REFERENCE_NS, TOLERANCE, fmt=_ns)

    # Structural, and it survives the reference numbers drifting: the
    # routed edge carries the real switch matrix and pad on top of the
    # as-drawn ideal wires, so it can only ever be slower.
    if values["trise_routed"] <= values["trise_drawn"]:
        print(
            "FAIL: trise_routed should be slower than trise_drawn -- the "
            "routed design adds real switch-matrix and pad parasitics on "
            "top of the as-drawn ideal wires, never less."
        )
        ok = False

    return simcheck.verdict(
        ok, subject="the inverter", readme="examples/inverter/README.md",
        causes="device library rebuild, routing change, PDK/tool update",
    )


if __name__ == "__main__":
    raise SystemExit(main())
