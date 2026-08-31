#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Measure examples/srlatch on real silicon with an Analog Discovery.

Loads the SR latch's bitstream onto the chip, then walks it through the
same sequence `examples/srlatch/tb_srlatch.sch` simulates -- SET, release,
RESET, release -- and reads the stored output at each step. Run from the
repo root, on the host, since it needs USB:

    python3 tools/measure_srlatch_ad3.py

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
edge. `tools/measure_srlatch_edge_ad3.py` drives real waveform edges and
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

import ctypes
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ad3  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mosbius.bitstream import unpack  # noqa: E402
from mosbius.model import SwitchConfig  # noqa: E402
from mosbius.program import (  # noqa: E402
    ProgramError,
    ibias_warning,
    program,
)
from mosbius.pads import pads_in_use  # noqa: E402

# examples/srlatch as the router placed it on 2026-08-29: ua1 SET, ua2 RESET,
# ua3 Q -- the configuration this example's silicon numbers were measured with.
# It is a record of an experiment, not a cached build artifact: if the
# router's allocation ever changes, re-route and re-measure rather than
# editing this string, or the published numbers quietly stop describing
# the configuration that was actually on the chip.
BITSTREAM = "0c008000c020008808000000008821000220200800000038"
PROJECT = "tt_um_tnt_mosbius"
SHUTTLE = "ttsky25a"
VAPWR = 3.3

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

# Volts: the settled levels both decks reach while holding, read off
# build/srlatch_tb_out_{drawn,routed}.txt at 200 ns (high) and 300 ns
# (low). These are NOT tools/check_srlatch_sim.py's reference numbers,
# which are sampled at 110 ns and 280 ns and so catch the routed instance
# mid-settle -- see this file's docstring. A bench reading taken 50 ms
# after the pulse belongs against the settled value.
REFERENCE = {
    "after_set": {"drawn": 3.2999, "routed": 3.2998},
    "after_reset": {"drawn": 0.0000, "routed": -0.0003},
}


def wiring_table() -> str:
    pads = pads_in_use(SwitchConfig(bits=unpack(BITSTREAM)), SHUTTLE, PROJECT)
    rows = [
        ("W1 (yellow)", pads["ua1"], "SET, design ua1"),
        ("W2 (yellow)", pads["ua2"], "RESET, design ua2"),
        ("2+ (blue)", pads["ua3"], "Q, design ua3 -- the stored output"),
        ("2-, GND", "gnd", "scope reference -- the input is differential, so"),
        ("", "", "this must be grounded or every reading is wrong"),
    ]
    out = ["\n  Wire the Analog Discovery to the demoboard like this:\n",
           "    AD3 lead      pad      signal",
           "    -----------   -----    ------------------------------------------"]
    for lead, pad, what in rows:
        out.append(f"    {lead:<13s} {pad:<8s} {what}")
    # `mosbius program` has already drawn the ANALOG header above, so this
    # names the leads only rather than printing the same picture twice.
    return "\n".join(out) + "\n"


def program_chip(port: str | None) -> None:
    """Upload the configuration through mosbius.program.program().

    Not `python3 -m mosbius.cli program` in a subprocess. The result dict
    carries an `ibias_set` field saying whether the board actually
    delivered the bias current, and the CLI renders that as a paragraph of
    English on stderr; reading the field is not merely tidier, because
    string-matching that paragraph fails in the DANGEROUS direction -- a
    reworded warning reads as "this board has a current source", and the
    script would then measure an unbiased chip very carefully.
    tools/measure_currentsource_ad3.py has always done it this way.
    """
    config = SwitchConfig.from_bitstream(BITSTREAM)
    print("== loading the SR latch onto the chip")
    try:
        result = program(config, project=PROJECT, port=port)
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


def report(readings: list[dict]) -> None:
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
    for name, refs in REFERENCE.items():
        measured = by_name[name]["q_mean"]
        print(f"  {name}: measured {measured:+.4f} V, corrected {measured - zero:+.4f} V; "
              f"as drawn {refs['drawn']:+.4f} V, as routed {refs['routed']:+.4f} V")
    print(f"\n  'Corrected' takes the held-low reading ({zero * 1e3:+.1f} mV) as this\n"
          "  channel's zero, since a pull-down with a 10 MOhm probe on it really is at\n"
          "  ground. The two decks predict the same settled levels within 0.1 mV of\n"
          "  each other, so this measurement confirms them and separates nothing: the\n"
          "  routed instance's extra 190 mV in the testbench is it still charging 9 ns\n"
          "  after the pulse, not a level it settles to.")

    print("\n  The first reading has no reference to compare against: an SR latch's state\n"
          "  when it comes up is genuinely undefined, decided by whichever asymmetry the\n"
          "  circuit happens to have, so it is recorded rather than checked.")
    if leads_look_swapped(readings):
        print("\n  WARNING -- channel 2 barely moved while channel 1 did. That is what a\n"
              "  Q lead clipped to 1+ instead of 2+ looks like: the latch is working,\n"
              "  the scope is watching the wrong pad. Move it and re-run.")


def main() -> None:
    args = sys.argv[1:]
    port = args[args.index("--port") + 1] if "--port" in args else None
    programmed = "--no-program" not in args
    if programmed:
        program_chip(port)
    print(wiring_table())

    handle = ad3.open_device()
    try:
        readings = run_sequence(handle, programmed)
        trace = capture_sequence(handle)
    finally:
        ad3.close(handle)

    out = Path("build/srlatch_silicon_trace.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"bitstream": BITSTREAM, "rate": RATE,
                               "readings": readings, "trace": trace}))
    report(readings)
    print(f"\n== trace written to {out}")


if __name__ == "__main__":
    main()
