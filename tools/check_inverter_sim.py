#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check an ngspice batch-mode log of examples/inverter/tb_inverter.sch
against the reference measurements in examples/inverter/README.md
("What running it shows"): trise_drawn=8.90ns, trise_routed=24.63ns,
last measured 2026-08-27 at cload=10p, on the routing the router produces
today.

Run by tools/check_inverter_sim.sh (the full netlist/route/simulate/ngspice
pipeline), which .github/workflows/spice-regression.yml runs once a month.

The +-5% band is set by what actually varies: reltol=0.01 keeps repeat
runs stable to well under 0.1%, so the noise floor is far below this and
5% is room for a minor ngspice or PDK point release rather than for real
change. It was +-25% until 2026-08-28, which was wide enough to miss a
sizeable error in the pad or parasitic models while still passing; the
matching ring check (tools/check_ring_sim.py) carries the same band and
the same reasoning.
"""

from __future__ import annotations

import re
import sys

REFERENCE_NS = {"trise_drawn": 8.90, "trise_routed": 24.63}
TOLERANCE = 0.05


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_inverter_sim.py <ngspice-log>", file=sys.stderr)
        return 2

    log_path = sys.argv[1]
    text = open(log_path).read()

    values: dict[str, float] = {}
    for name in REFERENCE_NS:
        m = re.search(rf"^\s*{name}\s*=\s*([0-9.eE+-]+)", text, re.MULTILINE)
        if not m:
            print(
                f"FAIL: no '{name}' measurement found in {log_path} -- the "
                f"ngspice run likely errored before reaching the tran "
                f"analysis. Tail of the log:\n"
                + "\n".join(text.splitlines()[-20:])
            )
            return 1
        values[name] = float(m.group(1)) * 1e9  # seconds -> ns

    ok = True
    for name, reference in REFERENCE_NS.items():
        measured = values[name]
        low, high = reference * (1 - TOLERANCE), reference * (1 + TOLERANCE)
        in_range = low <= measured <= high
        ok = ok and in_range
        status = "ok" if in_range else "OUT OF RANGE"
        print(
            f"{name}: {measured:.2f}ns "
            f"(reference {reference}ns, expected {low:.2f}-{high:.2f}ns) -- {status}"
        )

    if values["trise_routed"] <= values["trise_drawn"]:
        print(
            "FAIL: trise_routed should be slower than trise_drawn -- the "
            "routed design adds real switch-matrix and pad parasitics on "
            "top of the as-drawn ideal wires, never less."
        )
        ok = False

    if not ok:
        print(
            "\nSomething about the inverter's simulated behavior has "
            "changed. If this is an intentional change (device library "
            "rebuild, routing change, PDK/tool update), update the "
            "reference numbers here and in examples/inverter/README.md "
            "together; otherwise treat this as a real regression."
        )
        return 1

    print("\nOK -- inverter as-drawn/as-routed simulation matches the reference measurements.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
