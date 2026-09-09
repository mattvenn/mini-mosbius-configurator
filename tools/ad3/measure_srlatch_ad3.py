#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Measure examples/srlatch on real silicon with an Analog Discovery.

Loads the SR latch's bitstream onto the chip, then walks it through the
same sequence `examples/srlatch/tb_srlatch.sch` simulates -- SET, release,
RESET, release -- and reads the stored output at each step. Run from the
repo root, on the host, since it needs USB:

    python3 tools/ad3/measure_srlatch_ad3.py
    python3 tools/ad3/measure_srlatch_ad3.py --project tt_um_mosbius

Defaults to tnt's part (`tt_um_tnt_mosbius`); `--project tt_um_mosbius`
measures the same schematic routed for Andrew Kang's part instead, on
different pads -- the wiring table is derived from whichever `--project`
is running, not memorised.

**What this measures that no other example on this chip can.** The
inverter, the ring, the diff amp, the OTA follower and the current source
are all memoryless: drive them the same way twice and they do the same
thing. A latch keeps a value after the pulse that wrote it has gone, and
it keeps it through the routed switch matrix -- so the two "after release"
readings below are the only evidence on this bench that a crosspoint holds
state rather than merely passing a signal.

**Timing is not measured here, but it is measurable.** This script drives
the inputs by moving a wavegen's DC offset, which the Analog Discovery
slews over milliseconds -- right for settling a level, useless for an
edge. `tools/ad3/measure_srlatch_edge_ad3.py` drives real waveform edges and
triggers on Q's own fall to time the reset; it gets 24.46 ns against a
20 ns stimulus edge, and `tools/run_srlatch_measured_edge.sh` runs both
decks under that same stimulus for the comparison.

**The levels agree, and that is the result -- but it does not separate the
two models, and the reason is worth knowing.** `tb_srlatch.sch` samples
`qr_after_set` at 110 ns, which is 9 ns after SET releases, and the routed
node is still charging its 10 pF probe through the matrix's pass gates at
that moment: it reads 3.110 V there and 3.2998 V by 200 ns, against the
as-drawn 3.2999 V. So the sheet's 190 mV drawn-versus-routed gap is a
settling *time*, not a level, and the two models predict the same steady
state. This script waits 50 ms, so it can only see that steady state --
and confirming it is worth doing (a matrix that dropped a volt would show
here) but a settled level cannot tell the decks apart. The number that
would is `treset`, which this rig cannot resolve.

**Read the low state as the channel's zero.** A held-low output is a
pull-down with no load current on it -- the probe is 10 MOhm -- so the
chip really is at 0.000 V there, and whatever the scope reports instead
is that channel's residual offset. Subtracting it from the high reading
is the only offset correction available on a two-reading measurement, and
it is why both numbers are printed rather than just the swing.

Pad letters are derived from the bitstream and the shuttle index by
`mosbius/pads.py`, never written down here: which pad a design's `ua[k]`
reaches depends on where the project sits on that shuttle.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ad3  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from mosbius.chips import KANG, TNT  # noqa: E402
from mosbius.model import SwitchConfig  # noqa: E402
from mosbius.program import (  # noqa: E402
    ProgramError,
    ibias_warning,
    program,
)
from mosbius.pads import format_analog_header, pads_in_use  # noqa: E402

SHUTTLE = "ttsky25a"
VAPWR = 3.3

# Each entry is a record of a specific routing, not a cached build artifact:
# if the router's allocation for a part ever changes, re-route and
# re-measure rather than editing the bitstream here, or the published
# numbers quietly stop describing the configuration that was actually on
# the chip.
PROJECTS = {
    # examples/srlatch as the router placed it on 2026-08-29: ua1 SET, ua2
    # RESET, ua3 Q -- the configuration this example's silicon numbers were
    # measured with. REFERENCE is the settled levels both decks reach while
    # holding -- see the REFERENCE dict below for exactly where they were read.
    "tt_um_tnt_mosbius": {
        "chip": TNT,
        "bitstream": "0c008000c020008808000000008821000220200800000038",
        "reference": {
            "after_set": {"drawn": 3.2999, "routed": 3.2998},
            "after_reset": {"drawn": 0.0000, "routed": -0.0003},
        },
    },
    # examples/srlatch routed for tt_um_mosbius on 2026-09-09. REFERENCE is
    # from a tb_srlatch.sch run with MOSBIUS_PROJECT=tt_um_mosbius, read the
    # same way as tnt's: v(out_drawn)/v(out_routed) at 200 ns (after_set) and
    # the end of the 300 ns transient (after_reset). Within a millivolt of
    # tnt's own settled levels, as expected for a rail-to-rail digital state
    # held by devices (the write pair, drawn w=4) whose silicon width is
    # fixed regardless of which part this is.
    "tt_um_mosbius": {
        "chip": KANG,
        "bitstream": "0408c08008100000000000004422200003020212220400408",
        "reference": {
            "after_set": {"drawn": 3.2999, "routed": 3.2997},
            "after_reset": {"drawn": 0.0000, "routed": -0.0004},
        },
    },
}

RATE, NSAMPLES = 1e5, 4000        # 40 ms of the held state, per reading
DWELL_S = 0.05                    # settle after each step, before capturing

# (name, SET drive, RESET drive, what the reading means)
SEQUENCE = [
    ("initial", 0.0, 0.0, "before either input is driven -- see FIRST_READING"),
    ("during_set", VAPWR, 0.0, "SET held high"),
    ("after_set", 0.0, 0.0, "SET released -- the latch is holding a 1"),
    ("during_reset", 0.0, VAPWR, "RESET held high"),
    ("after_reset", 0.0, 0.0, "RESET released -- the latch is holding a 0"),
]

# What the first reading actually is depends on whether this run loaded the
# bitstream. Fresh from programming it is the state the latch came up in,
# which is genuinely undefined. Without programming it is whatever the
# latch was left holding, possibly by a previous run minutes ago -- still a
# real measurement, but of retention rather than of power-up.
FIRST_READING = {
    True: "the state the latch came up in, straight after programming",
    False: "whatever the latch was already holding -- this run did not program it",
}

# Each project's "reference" above is the settled levels both decks reach
# while holding, read off build/srlatch_tb_out_{drawn,routed}.txt at 200 ns
# (high) and 300 ns (low). These are NOT tools/sim/check_srlatch_sim.py's
# reference numbers, which are sampled at 110 ns and 280 ns and so catch
# the routed instance mid-settle -- see this file's docstring. A bench
# reading taken 50 ms after the pulse belongs against the settled value.


def wiring_table(project: str, pads: dict[str, str]) -> str:
    rows = [
        ("W1 (yellow)", pads["ua1"], "SET, design ua1"),
        ("W2 (yellow/white)", pads["ua2"], "RESET, design ua2"),
        ("2+ (blue)", pads["ua3"], "Q, design ua3 -- the stored output"),
        ("1+, 1-, 2-, GND", "gnd", "scope reference. 1+/1- go to ground too, not"),
        ("", "", "just left off: this reads Q on 2+ only, but 1+ still"),
        ("", "", "has to land somewhere known, or a floating input can"),
        ("", "", "clip the capture at either edge of the scope range."),
    ]
    out = ["\n  Wire the Analog Discovery to the demoboard like this:\n",
           "    AD3 lead           pad      signal",
           "    ----------------   -----    ------------------------------------------"]
    for lead, pad, what in rows:
        out.append(f"    {lead:<18s} {pad:<8s} {what}")
    # Drawn here rather than left to `mosbius program`'s side effect: with
    # --no-program (re-checking wiring, or re-reading without reuploading)
    # that step never runs, and nothing else would print the picture at all.
    return "\n".join(out) + "\n\n" + format_analog_header(pads) + "\n"


def program_chip(project: str, bitstream: str, chip, port: str | None) -> None:
    """Upload the configuration through mosbius.program.program().

    Not `python3 -m mosbius.cli program` in a subprocess. The result dict
    carries an `ibias_set` field saying whether the board actually
    delivered the bias current, and the CLI renders that as a paragraph of
    English on stderr; reading the field is not merely tidier, because
    string-matching that paragraph fails in the DANGEROUS direction -- a
    reworded warning reads as "this board has a current source", and the
    script would then measure an unbiased chip very carefully.
    tools/ad3/measure_currentsource_ad3.py has always done it this way.
    """
    config = SwitchConfig.from_bitstream(bitstream, chip=chip)
    print(f"== loading the SR latch onto the chip ({project})")
    try:
        result = program(config, project=project, port=port)
    except ProgramError as exc:
        raise SystemExit(f"programming failed -- nothing measured\n\n{exc}")
    warning = ibias_warning(result, config)
    if warning:
        print(warning)


def run_sequence(handle, programmed: bool) -> list[dict]:
    ad3.wavegen(handle, ch=0, func=ad3.funcDC, amp=0.0, offset=0.0)
    ad3.wavegen(handle, ch=1, func=ad3.funcDC, amp=0.0, offset=0.0)
    ad3.scope_setup(handle, rate=RATE, nsamples=NSAMPLES)

    readings = []
    for name, set_v, reset_v, meaning in SEQUENCE:
        ad3.wavegen(handle, ch=0, func=ad3.funcDC, amp=0.0, offset=set_v)
        ad3.wavegen(handle, ch=1, func=ad3.funcDC, amp=0.0, offset=reset_v)
        time.sleep(DWELL_S)
        samples = ad3.acquire(handle, nsamples=NSAMPLES, tag=f"{name}: ")
        q = samples[1]
        if name == "initial":
            meaning = FIRST_READING[programmed]
        readings.append({
            "name": name, "meaning": meaning, "set_v": set_v, "reset_v": reset_v,
            "q_mean": ad3.mean(samples, 1), "q_min": min(q), "q_max": max(q),
            "other_channel_mean": ad3.mean(samples, 0),
            "q": q,
        })
    ad3.wavegen(handle, ch=0, func=ad3.funcDC, amp=0.0, offset=0.0)   # park both
    ad3.wavegen(handle, ch=1, func=ad3.funcDC, amp=0.0, offset=0.0)
    return readings


TRACE_RATE, TRACE_SAMPLES = 2e4, 4000     # one 200 ms window over the sequence
TRACE_PLAN = [                            # (seconds into the window, W1, W2)
    (0.040, VAPWR, 0.0),
    (0.080, 0.0, 0.0),
    (0.120, 0.0, VAPWR),
    (0.160, 0.0, 0.0),
]


def capture_sequence(handle) -> dict:
    """One continuous capture spanning the whole SET/hold/RESET/hold
    sequence, for the figure.

    The stepped readings above are five separate captures with the
    transitions falling in the gaps between them, so they give the levels
    and no waveform. Here the scope is armed first and the inputs are
    driven while it fills, which is the only way this rig gets a trace
    with the edges in it. The edges themselves are still not a measurement
    of the chip -- the drive takes milliseconds to arrive where the chip
    responds in nanoseconds, so what the trace shows at a transition is
    the wavegen moving, not the latch.
    """
    ad3.scope_setup(handle, rate=TRACE_RATE, nsamples=TRACE_SAMPLES)
    ad3.dwf.FDwfAnalogInConfigure(handle, ctypes.c_int(0), ctypes.c_int(1))
    start = time.monotonic()
    for at, set_v, reset_v in TRACE_PLAN:
        while time.monotonic() - start < at:
            time.sleep(0.002)
        ad3.wavegen(handle, ch=0, func=ad3.funcDC, amp=0.0, offset=set_v)
        ad3.wavegen(handle, ch=1, func=ad3.funcDC, amp=0.0, offset=reset_v)

    status = ctypes.c_ubyte()
    while True:
        ad3.dwf.FDwfAnalogInStatus(handle, ctypes.c_int(1), ctypes.byref(status))
        if status.value == 2:
            break
        time.sleep(0.005)
    buf = (ctypes.c_double * TRACE_SAMPLES)()
    ad3.dwf.FDwfAnalogInStatusData(handle, ctypes.c_int(1), buf, ctypes.c_int(TRACE_SAMPLES))
    q = list(buf)
    ad3.check_clipping({1: q}, "trace: ")
    return {"rate": TRACE_RATE, "plan": TRACE_PLAN, "q": q}


def leads_look_swapped(readings: list[dict]) -> bool:
    """Q on 1+ instead of 2+ is the easy mistake, and it looks like a dead
    circuit rather than like a wiring error, so say which it is."""
    spread = lambda key: (max(r[key] for r in readings) - min(r[key] for r in readings))
    return spread("q_mean") < 0.5 and spread("other_channel_mean") > 1.0


def report(readings: list[dict], reference: dict) -> None:
    print("\n  reading        Q          flat to     what it is")
    print("  ------------   --------   ---------   ---------------------------------")
    for r in readings:
        ripple_mv = (r["q_max"] - r["q_min"]) * 1e3
        print(f"  {r['name']:<12s}   {r['q_mean']:+.4f} V   {ripple_mv:6.1f} mV   {r['meaning']}")
    print(f"\n  Each reading is the mean of {NSAMPLES} samples over "
          f"{NSAMPLES / RATE * 1e3:.0f} ms; the 'flat to' column is that\n"
          "  capture's peak-to-peak, so a stored level that decayed while it was\n"
          "  being held would show up there rather than being averaged away.\n")

    by_name = {r["name"]: r for r in readings}
    zero = by_name["after_reset"]["q_mean"]
    for name, refs in reference.items():
        measured = by_name[name]["q_mean"]
        print(f"  {name}: measured {measured:+.4f} V, corrected {measured - zero:+.4f} V; "
              f"as drawn {refs['drawn']:+.4f} V, as routed {refs['routed']:+.4f} V")
    print(f"\n  'Corrected' takes the held-low reading ({zero * 1e3:+.1f} mV) as this\n"
          "  channel's zero, since a pull-down with a 10 MOhm probe on it really is at\n"
          "  ground. The two decks predict the same settled levels within a millivolt of\n"
          "  each other, so this measurement confirms them and separates nothing: the\n"
          "  routed instance's gap in the testbench (sampled at 110 ns) is it still\n"
          "  charging through the matrix, not a level it settles to by 200 ns.")

    print("\n  The first reading has no reference to compare against: an SR latch's state\n"
          "  when it comes up is genuinely undefined, decided by whichever asymmetry the\n"
          "  circuit happens to have, so it is recorded rather than checked.")
    if leads_look_swapped(readings):
        print("\n  WARNING -- channel 2 barely moved while channel 1 did. That is what a\n"
              "  Q lead clipped to 1+ instead of 2+ looks like: the latch is working,\n"
              "  the scope is watching the wrong pad. Move it and re-run.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project", choices=sorted(PROJECTS), default="tt_um_tnt_mosbius")
    ap.add_argument("--port", default=None)
    ap.add_argument("--no-program", action="store_true")
    args = ap.parse_args()

    spec = PROJECTS[args.project]
    pads = pads_in_use(
        SwitchConfig.from_bitstream(spec["bitstream"], chip=spec["chip"]),
        SHUTTLE, args.project,
    )
    programmed = not args.no_program
    if programmed:
        program_chip(args.project, spec["bitstream"], spec["chip"], args.port)
    print(wiring_table(args.project, pads))
    input("  Press Enter once that is wired... ")

    handle = ad3.open_device()
    try:
        readings = run_sequence(handle, programmed)
        trace = capture_sequence(handle)
    finally:
        ad3.close(handle)

    suffix = "_kang" if args.project == "tt_um_mosbius" else ""
    out = Path(f"build/srlatch{suffix}_silicon_trace.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"bitstream": spec["bitstream"], "rate": RATE,
                               "readings": readings, "trace": trace}))
    report(readings, spec["reference"])
    print(f"\n== trace written to {out}")


if __name__ == "__main__":
    main()
