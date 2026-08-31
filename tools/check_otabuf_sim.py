#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check an ngspice batch-mode log of examples/otabuf/tb_otabuf.sch against
the reference measurements in examples/otabuf/README.md, last measured 2026-08-28 at cprobe=10p (with rprobe=10meg),
ibias_amps=100u, tail=4:

    offsets (output minus input, on the ramp)
        1.00 V input   +30.2 mV drawn   +25.0 mV routed
        1.65 V input    +8.6 mV drawn    +5.9 mV routed
        2.50 V input   -31.7 mV drawn   -33.1 mV routed

    slew rate (1.0 V -> 2.3 V step, measured between 1.3 V and 2.0 V)
        42.9 V/us drawn    15.4 V/us routed

Run by tools/check_otabuf_sim.sh, which
.github/workflows/spice-regression.yml runs on every push alongside the
inverter, ring, diff amp, SR latch and current source checks.

What this one guards that the others cannot. It is the only example that
uses `mosbius_ota` at all -- five transistors and a tail bank in one
block, including the `ctrl_otan_mode[0]` bit that ties the PMOS mirror
gates to `outp`. That bit went unset once already, leaving the routed OTA
with a floating mirror gate and the two branches of this testbench not
the same circuit (both fixed 2026-08-28; git log has the write-up). It is
also the only example that closes a *feedback loop*
through the switch matrix, so it is the only one that would notice the
routed model turning a stable follower into something that rings or
latches.

The offsets and slew rates are computed here rather than read from the
log's own `off_*` and `slew_rate_*` prints, because `vin_*`, `vout_*` and
`t1_*`/`t2_*` are plain `meas` results with one value per line, which is
a format worth depending on; a multi-vector `print` is not. Same reasoning
as tools/check_diffamp_sim.py.

The offsets get an absolute band rather than the +-5% the other checks
use, because they are millivolt differences between volt-sized numbers:
5% of the +8.6 mV mid-rail offset is 0.4 mV, which would fail on rounding
alone. The slew rates are well-conditioned and keep the usual +-5%.

If an upstream image update does shift a result past a band, re-measure
deliberately and update the numbers here and in examples/otabuf/README.md
together, rather than widening the band.
"""

from __future__ import annotations

import re
import sys

# Input voltages the ramp is sampled at, and the `meas` name suffix
# tb_otabuf.sch uses for each. The sample times in the deck (3.76us, 6us,
# 8.93us) were chosen to land on these round volts.
SAMPLES = {"lo": 1.00, "mid": 1.65, "hi": 2.50}

# Volts, from the README table: output minus input at each sample.
REFERENCE_OFFSET_V = {
    "drawn_lo": +0.0302,
    "drawn_mid": +0.0086,
    "drawn_hi": -0.0317,
    "routed_lo": +0.0250,
    "routed_mid": +0.0059,
    "routed_hi": -0.0331,
}
# V/us, from the README.
REFERENCE_SLEW_V_PER_US = {"drawn": 42.9, "routed": 15.4}

# The step tb_otabuf.sch measures the slew rate over: 1.3 V to 2.0 V.
SLEW_SPAN_V = 0.7

# Absolute band on an offset, in volts. Wide against the numbers above --
# but a follower that has stopped following misses by hundreds of mV, not
# by five.
OFFSET_TOLERANCE_V = 0.005
# Fractional band on a slew rate, matching the other checks in tools/.
SLEW_TOLERANCE = 0.05
# How far apart the as-drawn and as-routed offsets may sit before this is a
# real finding. The README measures ~5 mV.
BRANCH_AGREEMENT_V = 0.010
# An offset this large means the loop is not following at all.
FOLLOWING_LIMIT_V = 0.100


def find(text: str, name: str, log_path: str) -> float | None:
    m = re.search(rf"^\s*{name}\s*=\s*([0-9.eE+-]+)", text, re.MULTILINE)
    if not m:
        print(
            f"FAIL: no '{name}' measurement found in {log_path} -- the "
            f"ngspice run likely errored before reaching the tran analysis, "
            f"or the measurement reported 'failed' instead of a number. Tail "
            f"of the log:\n" + "\n".join(text.splitlines()[-20:])
        )
        return None
    return float(m.group(1))


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_otabuf_sim.py <ngspice-log>", file=sys.stderr)
        return 2

    log_path = sys.argv[1]
    text = open(log_path).read()

    names = [f"vin_{s}" for s in SAMPLES]
    names += [f"vout_{b}_{s}" for b in ("drawn", "routed") for s in SAMPLES]
    names += [f"t{n}_{b}" for b in ("drawn", "routed") for n in (1, 2)]

    values: dict[str, float] = {}
    for name in names:
        value = find(text, name, log_path)
        if value is None:
            return 1
        values[name] = value

    ok = True

    # The ramp is slow enough (0.29 V/us against a 42.9 V/us slew rate) that
    # the output is never rate-limited, so output minus input here is the
    # loop's static error and nothing else.
    offsets: dict[str, float] = {}
    for branch in ("drawn", "routed"):
        for sample in SAMPLES:
            offsets[f"{branch}_{sample}"] = (
                values[f"vout_{branch}_{sample}"] - values[f"vin_{sample}"]
            )

    for key, reference in REFERENCE_OFFSET_V.items():
        measured = offsets[key]
        low, high = reference - OFFSET_TOLERANCE_V, reference + OFFSET_TOLERANCE_V
        in_range = low <= measured <= high
        ok = ok and in_range
        branch, sample = key.split("_")
        status = "ok" if in_range else "OUT OF RANGE"
        print(
            f"offset_{key}: {measured * 1e3:+.1f}mV at {SAMPLES[sample]:.2f}V in "
            f"(reference {reference * 1e3:+.1f}mV, expected "
            f"{low * 1e3:+.1f} to {high * 1e3:+.1f}mV) -- {status}"
        )

    slew: dict[str, float] = {}
    for branch in ("drawn", "routed"):
        rise_s = values[f"t2_{branch}"] - values[f"t1_{branch}"]
        if rise_s <= 0:
            print(
                f"FAIL: the as-{branch} output crossed 2.0V at or before it "
                f"crossed 1.3V (t1={values[f't1_{branch}']:.4g}s, "
                f"t2={values[f't2_{branch}']:.4g}s), so there is no rising "
                f"edge to measure a slew rate on."
            )
            ok = False
            slew[branch] = float("nan")
            continue
        slew[branch] = SLEW_SPAN_V / rise_s / 1e6  # V/us

    for branch, reference in REFERENCE_SLEW_V_PER_US.items():
        measured = slew[branch]
        if measured != measured:  # NaN, already reported
            continue
        low, high = reference * (1 - SLEW_TOLERANCE), reference * (1 + SLEW_TOLERANCE)
        in_range = low <= measured <= high
        ok = ok and in_range
        status = "ok" if in_range else "OUT OF RANGE"
        print(
            f"slew_rate_{branch}: {measured:.1f}V/us "
            f"(reference {reference}V/us, expected {low:.1f}-{high:.1f}V/us) "
            f"-- {status}"
        )

    # Structural, and it survives the reference numbers drifting: this is a
    # unity-gain follower, so if it is working at all the output sits within
    # a few tens of mV of the input across the ramp. A number in the hundreds
    # of mV is the loop having given up -- positive feedback, a lost bias
    # point, or an input outside the common-mode range -- which is a bigger
    # deal than a shifted offset and would otherwise read as one.
    for key, offset in offsets.items():
        if abs(offset) > FOLLOWING_LIMIT_V:
            branch, sample = key.split("_")
            print(
                f"FAIL: as {branch}, the output is {offset * 1e3:+.0f}mV from "
                f"the input at {SAMPLES[sample]:.2f}V in. This is a "
                f"unity-gain follower; an error that size means it is not "
                f"following -- check that inm is fed back from outm and not "
                f"from outp (that is positive feedback, a latch), and that "
                f"the tail bank is still biased."
            )
            ok = False

    # Also structural: at DC nothing flows into a capacitor, so the pad's and
    # the switch matrix's series resistance drop no voltage and a settled
    # offset must come out the same either way. Two branches that disagree
    # mean something has moved the routed operating point itself.
    for sample in SAMPLES:
        drawn, routed = offsets[f"drawn_{sample}"], offsets[f"routed_{sample}"]
        if abs(routed - drawn) > BRANCH_AGREEMENT_V:
            print(
                f"FAIL: at {SAMPLES[sample]:.2f}V in, the as-drawn and "
                f"as-routed offsets should settle to the same value (within "
                f"{BRANCH_AGREEMENT_V * 1e3:.0f}mV), because a settled DC "
                f"level is unaffected by the series resistance the routed "
                f"model adds -- got {drawn * 1e3:+.1f}mV drawn against "
                f"{routed * 1e3:+.1f}mV routed."
            )
            ok = False

    # And the counterpart for the transient half: the capacitance the routed
    # model adds is real, so the routed branch must slew *slower*. If it ever
    # comes out faster, the routed deck has lost its pad or mux loading.
    if slew["drawn"] == slew["drawn"] and slew["routed"] == slew["routed"]:
        if slew["routed"] >= slew["drawn"]:
            print(
                f"FAIL: the as-routed branch slews at {slew['routed']:.1f}V/us "
                f"against {slew['drawn']:.1f}V/us as drawn. The routed model "
                f"adds the bond pad, the analog mux and the switch matrix to "
                f"the output node, so it can only be slower -- this says the "
                f"routed deck is missing that loading."
            )
            ok = False

    if not ok:
        print(
            "\nSomething about the OTA follower's simulated behavior has "
            "changed. If this is an intentional change (device library "
            "rebuild, routing change, a different circuit in otabuf.sch, "
            "PDK/tool update), update the reference numbers here and in "
            "examples/otabuf/README.md together; otherwise treat this as a "
            "real regression."
        )
        return 1

    print(
        "\nOK -- OTA follower as-drawn/as-routed simulation matches the "
        "reference measurements."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
