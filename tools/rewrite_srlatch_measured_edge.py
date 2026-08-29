#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Rewrite build/tb_srlatch.spice to use the bench's stimulus and probe.

Run by tools/run_srlatch_measured_edge.sh; see that file for why this is a
netlist rewrite rather than an edit to the schematic.

Four changes, and nothing else:

* **The stimulus edge.** `tb_srlatch.sch` uses 1 ns edges. The Analog
  Discovery's generator was measured at 20.2 ns 10%-90% on the RESET pad
  by tools/measure_srlatch_edge_ad3.py. A SPICE PULSE's `tr` is the full
  0-100% transition, so the 10%-90% part of it is 0.8*tr: tr = 25.3 ns
  reproduces the measured 20.2 ns.
* **The timescale.** Edges 25x longer need a longer window, so the pulses
  move out to 100 ns and 600 ns and the run goes to 1.2 us.
* **The probe.** The sheet defaults to a 10x passive probe (10 MOhm,
  10 pF); the bench used the Analog Discovery's flywires directly, which
  its own documentation puts at 1 MOhm and 24 pF.
* **`save`.** `save all` on a routed subcircuit with hundreds of internal
  nodes is what ran the container out of memory on a long run. This one is
  four times longer than the sheet's, so only the four nodes that are
  measured are saved.

An optional fifth change, `--drawn-w4`, widens `XM5` and `XM6` in the
as-drawn block from `w=1` to `w=4`. The router already warns that those
two land on differential-pair halves, whose geometry is fixed in silicon
at `w=4`, so the drawn deck as committed simulates a reset written through
transistors four times weaker than the ones the chip builds -- see
TODO.md's SR latch item. This flag asks what the drawn deck says with that
one discrepancy removed, without touching the schematic that publishes the
committed numbers.

The measurements themselves stay the definition the sheet uses: RESET
crossing mid-rail rising to the output crossing it falling, which is also
what the bench script times between its two channels.
"""

from __future__ import annotations

import sys
from pathlib import Path

# 10%-90% of a SPICE PULSE's tr is 0.8*tr, and the bench measured 20.2 ns.
STIMULUS_TR = "25.3n"
SET_AT, RESET_AT, PULSE_WIDTH, PERIOD = "100n", "600n", "300n", "5u"

# The traces go to a different prefix under --drawn-w4, so the two
# experiments cannot overwrite each other's output: they differ only in a
# device width, and a figure redrawn from the wrong one would look
# entirely reasonable.
ANALYSIS = """.control
  save v(set) v(reset) v(out_drawn) v(out_routed)
  tran 20p 1.2u
  meas tran vhigh_drawn FIND v(out_drawn) AT=550n
  meas tran vhigh_routed FIND v(out_routed) AT=550n
  meas tran vlow_drawn FIND v(out_drawn) AT=1.1u
  meas tran vlow_routed FIND v(out_routed) AT=1.1u
  meas tran treset_drawn TRIG v(reset) VAL=1.65 RISE=1 TARG v(out_drawn) VAL=1.65 FALL=1
  meas tran treset_routed TRIG v(reset) VAL=1.65 RISE=1 TARG v(out_routed) VAL=1.65 FALL=1
  wrdata {prefix}_reset.txt v(reset)
  wrdata {prefix}_out_drawn.txt v(out_drawn)
  wrdata {prefix}_out_routed.txt v(out_routed)
  quit
.endc
"""


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    drawn_w4 = "--drawn-w4" in sys.argv[1:]
    source, target = Path(args[0]), Path(args[1])
    text = source.read_text()

    if drawn_w4:
        for device in ("XM5", "XM6"):
            line = f"{device} "
            hits = [ln for ln in text.splitlines()
                    if ln.startswith(line) and ln.endswith("w=1")]
            if len(hits) != 1:
                raise SystemExit(
                    f"expected exactly one '{device} ... w=1' line in {source}, "
                    f"found {len(hits)}.\n"
                    "  --drawn-w4 rewrites the two write transistors in the as-drawn\n"
                    "  block; if the design has changed, check which devices land on\n"
                    "  the differential-pair halves before widening anything."
                )
            text = text.replace(hits[0], hits[0][:-3] + "w=4")
        print("  XM5 and XM6 widened to w=4 in the as-drawn block")

    text = text.replace(
        "Vset set VGND PULSE(0 3.3 60n 1n 1n 40n 1000n)",
        f"Vset set VGND PULSE(0 3.3 {SET_AT} {STIMULUS_TR} {STIMULUS_TR} "
        f"{PULSE_WIDTH} {PERIOD})")
    text = text.replace(
        "Vreset reset VGND PULSE(0 3.3 220n 1n 1n 40n 1000n)",
        f"Vreset reset VGND PULSE(0 3.3 {RESET_AT} {STIMULUS_TR} {STIMULUS_TR} "
        f"{PULSE_WIDTH} {PERIOD})")
    text = text.replace(".param rprobe=10meg", ".param rprobe=1meg")
    text = text.replace(".param cprobe=10p", ".param cprobe=24p")

    start = text.index(".control")
    end = text.index(".endc") + len(".endc\n")
    prefix = "srlatch_edge_w4" if drawn_w4 else "srlatch_edge"
    text = text[:start] + ANALYSIS.format(prefix=prefix) + text[end:]

    target.write_text(text)
    print(f"  wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
