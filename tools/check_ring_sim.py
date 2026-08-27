#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check an ngspice batch-mode log of examples/ringosc/tb_ring.sch against
the reference measurements in examples/ringosc/README.md ("What the
committed schematic measures now"): freq_drawn=2.083GHz,
freq_routed=43.89MHz, last measured 2026-08-27.

Run by tools/check_ring_sim.sh, which
.github/workflows/spice-regression.yml runs once a month alongside the
inverter check.

The two examples guard different things, which is why both run. The
inverter is pad-and-load-dominated: at 10pF its result barely moves if the
switch matrix's own parasitics are wrong. The ring is
switch-matrix-dominated -- row coupling (~43fF/switch) and bus-wire
capacitance (~900fF/row) are what set its frequency -- so a device-library
rebuild that got those wrong would sail past the inverter check and fail
here.

The +-5% band is set by what actually varies. With reltol=0.01 repeat runs
agree to well under 0.1%, and two different IIC-OSIC-TOOLS containers gave
identical numbers to four significant figures, so the noise floor is far
below this. 5% leaves room for a minor ngspice or PDK point release
without crying wolf, while still catching the kind of error a wide band
misses -- a wrong entry in BUS_WIRE_CAPACITANCE_F, or row coupling
applied to the wrong number of switches, moves this by tens of percent,
not by multiples.

If an upstream image update does shift the result past this band, that is
the check working: the reference numbers here and in the README have gone
stale and should be re-measured deliberately rather than absorbed by a
tolerance nobody chose.

Frequencies are read from the loop nodes, not the buffered outputs. The
buffer cannot slew its 15pF load at these speeds, so out_drawn spans only
~1.8-2.1V and grazes the 1.5V trigger -- measured there, the same deck
reported 58.3MHz on one run and 44.0MHz on the next. See the README.
"""

from __future__ import annotations

import re
import sys

# Hz. freq_drawn is the ideal-wire loop; freq_routed is the same loop
# through the real switch matrix, and is the one comparable in spirit to
# the ~30MHz silicon measurement (though not directly -- that bitstream is
# the unbuffered, all-pins circuit; see the README).
REFERENCE_HZ = {"freq_drawn": 2.083e9, "freq_routed": 43.89e6}
TOLERANCE = 0.05


def _fmt(hz: float) -> str:
    return f"{hz / 1e9:.3f}GHz" if hz >= 1e9 else f"{hz / 1e6:.2f}MHz"


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_ring_sim.py <ngspice-log>", file=sys.stderr)
        return 2

    log_path = sys.argv[1]
    text = open(log_path).read()

    values: dict[str, float] = {}
    for name in REFERENCE_HZ:
        # `let freq_x = 1/period_x` then `print freq_x`, so the log line is
        # "freq_drawn = 2.082616e+09" rather than a .meas result line.
        m = re.search(rf"^\s*{name}\s*=\s*([0-9.eE+-]+)", text, re.MULTILINE)
        if not m:
            print(
                f"FAIL: no '{name}' value found in {log_path} -- the ngspice "
                f"run likely errored before reaching it, or the ring failed "
                f"to start oscillating (check that Ikickd/Ikickr still "
                f"inject into the loop nodes). Tail of the log:\n"
                + "\n".join(text.splitlines()[-20:])
            )
            return 1
        values[name] = float(m.group(1))

    ok = True
    for name, reference in REFERENCE_HZ.items():
        measured = values[name]
        low, high = reference * (1 - TOLERANCE), reference * (1 + TOLERANCE)
        in_range = low <= measured <= high
        ok = ok and in_range
        status = "ok" if in_range else "OUT OF RANGE"
        print(
            f"{name}: {_fmt(measured)} "
            f"(reference {_fmt(reference)}, expected {_fmt(low)}-{_fmt(high)}) -- {status}"
        )

    # Structural, and it survives the reference numbers drifting: the
    # routed loop carries the real matrix's resistance and capacitance on
    # top of the as-drawn ideal wires, so it can only ever be slower.
    if values["freq_routed"] >= values["freq_drawn"]:
        print(
            "FAIL: freq_routed should be lower than freq_drawn -- the routed "
            "design adds real switch-matrix, coupling and pad parasitics to "
            "the loop, which can only slow it down."
        )
        ok = False

    if not ok:
        print(
            "\nSomething about the ring oscillator's simulated behavior has "
            "changed. If this is an intentional change (device library "
            "rebuild, routing change, a different circuit in ring.sch, "
            "PDK/tool update), update the reference numbers here and in "
            "examples/ringosc/README.md together; otherwise treat this as a "
            "real regression."
        )
        return 1

    print("\nOK -- ring oscillator as-drawn/as-routed simulation matches the reference measurements.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
