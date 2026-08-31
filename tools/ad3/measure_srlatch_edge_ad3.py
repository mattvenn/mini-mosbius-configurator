#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Time the SR latch's reset on real silicon: RESET rising to Q falling.

`tools/ad3/measure_srlatch_ad3.py` measures the levels the latch holds. This
measures the one thing that happens *between* them -- the delay from RESET
crossing mid-rail to Q crossing it, which is `tb_srlatch.sch`'s `treset`.
Run from the repo root, on the host:

    python3 tools/ad3/measure_srlatch_edge_ad3.py

**Triggering is what makes this possible, and its absence is what made it
look impossible.** The event is tens of nanoseconds inside a sequence
milliseconds long, so an untriggered capture at a rate slow enough to span
the sequence puts the whole transition inside one sample. Captured at the
device's full rate with the scope triggered on Q's own falling edge --
which is exactly what you do by hand when you zoom in on a WaveForms
window -- the same transition is hundreds of samples wide.

**It measures a delay, deliberately, and not a rise time.** Both channels
sit behind the same input filter, so a delay common to the two of them
cancels out of the difference, while an edge *width* is the signal's own
rise and the instrument's added in quadrature and cannot be separated
without knowing the instrument's. The crossings are interpolated between
samples and averaged over many triggers, since the latch does the same
thing every time, so the resolution is not the 8 ns sample interval.

**Drive the edge as a waveform, never by moving the DC offset.** This cost
a measurement. `ad3.wavegen()` sets an output's offset, and the Analog
Discovery slews an offset change over *milliseconds* -- so commanding
"RESET goes to 3.3 V" that way produces a ramp thousands of times slower
than the transition being timed, and the latch follows it down gradually
instead of switching. It does not look like a broken stimulus either: the
capture is full of a clean, slow, entirely plausible fall. The tell was
that the stimulus channel never reached a rail anywhere in the buffer, and
that both channels were still moving at both ends of it. Here SET and
RESET are two square waves with a phase offset, so each edge is a real
DAC transition at the generator's full speed.

**What it is not is the sheet's number, and the reason is the generator,
not the scope.** `tb_srlatch.sch` drives RESET as a 1 ns step; an Analog
Discovery's output amplifier takes tens of nanoseconds to move 3.3 V, so
on the bench the latch is partly being paced by its stimulus. That is why
this script reports the stimulus edge alongside the delay, and why
`tools/run_srlatch_measured_edge.sh` re-simulates both decks with the edge
measured here rather than with the sheet's 1 ns one. Compare against that,
not against `treset_drawn`/`treset_routed`.
"""

from __future__ import annotations

import ctypes
import json
import statistics
import sys
import time
from ctypes import byref, c_double, c_int, c_ubyte
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ad3  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from mosbius.bitstream import unpack  # noqa: E402
from mosbius.model import SwitchConfig  # noqa: E402
from mosbius.program import (  # noqa: E402
    ProgramError,
    ibias_warning,
    program,
)
from mosbius.pads import pads_in_use  # noqa: E402

# examples/srlatch as the router placed it on 2026-08-29, the same string
# tools/ad3/measure_srlatch_ad3.py programs; the measured reset edge is against it.
# It is a record of an experiment, not a cached build artifact: if the
# router's allocation ever changes, re-route and re-measure rather than
# editing this string, or the published numbers quietly stop describing
# the configuration that was actually on the chip.
BITSTREAM = "0c008000c020008808000000008821000220200800000038"
PROJECT = "tt_um_tnt_mosbius"
SHUTTLE = "ttsky25a"
VAPWR, MIDRAIL = 3.3, 1.65

NSAMPLES = 4096
CAPTURES = 20
STIMULUS_HZ = 1000.0     # one SET/hold/RESET/hold cycle per millisecond

# From /Library/Frameworks/dwf.framework/Headers/dwf.h.
TRIGSRC_DETECTOR_ANALOG_IN = 2
TRIGTYPE_EDGE = 0
SLOPE_RISE, SLOPE_FALL = 0, 1
STATE_DONE = 2

RESET_CH, Q_CH = 0, 1        # scope channel index, so 0 is 1+ and 1 is 2+


def wiring_table() -> str:
    pads = pads_in_use(SwitchConfig(bits=unpack(BITSTREAM)), SHUTTLE, PROJECT)
    rows = [
        ("W1 (yellow)", pads["ua1"], "SET, design ua1 -- arms the latch high"),
        ("W2 (yellow)", pads["ua2"], "RESET, design ua2 -- the edge being timed"),
        ("1+ (orange)", pads["ua2"], "the same node, so the stimulus is measured"),
        ("", "", "where it arrives rather than where it is commanded"),
        ("2+ (blue)", pads["ua3"], "Q, design ua3"),
        ("1-, 2-, GND", "gnd", "scope reference"),
    ]
    out = ["\n  Wire the Analog Discovery to the demoboard like this:\n",
           "    AD3 lead      pad      signal",
           "    -----------   -----    ------------------------------------------"]
    for lead, pad, what in rows:
        out.append(f"    {lead:<13s} {pad:<8s} {what}")
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
    tools/ad3/measure_currentsource_ad3.py has always done it this way.
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


def max_rate(handle) -> float:
    lo, hi = c_double(), c_double()
    ad3.dwf.FDwfAnalogInFrequencyInfo(handle, byref(lo), byref(hi))
    return hi.value


def arm(handle, rate: float) -> None:
    """Full-rate acquisition, triggered on Q falling through mid-rail, with
    the trigger in the middle of the buffer so the RESET edge that caused
    it is inside the capture too."""
    for ch in (RESET_CH, Q_CH):
        ad3.dwf.FDwfAnalogInChannelEnableSet(handle, c_int(ch), c_int(1))
        ad3.dwf.FDwfAnalogInChannelRangeSet(handle, c_int(ch), c_double(ad3.CHIP_RANGE))
        ad3.dwf.FDwfAnalogInChannelOffsetSet(handle, c_int(ch), c_double(ad3.CHIP_OFFSET))
    ad3.dwf.FDwfAnalogInFrequencySet(handle, c_double(rate))
    ad3.dwf.FDwfAnalogInBufferSizeSet(handle, c_int(NSAMPLES))
    ad3.dwf.FDwfAnalogInTriggerAutoTimeoutSet(handle, c_double(0.0))   # no auto-trigger
    ad3.dwf.FDwfAnalogInTriggerSourceSet(handle, c_ubyte(TRIGSRC_DETECTOR_ANALOG_IN))
    ad3.dwf.FDwfAnalogInTriggerTypeSet(handle, c_int(TRIGTYPE_EDGE))
    ad3.dwf.FDwfAnalogInTriggerChannelSet(handle, c_int(Q_CH))
    ad3.dwf.FDwfAnalogInTriggerLevelSet(handle, c_double(MIDRAIL))
    ad3.dwf.FDwfAnalogInTriggerConditionSet(handle, c_int(SLOPE_FALL))
    ad3.dwf.FDwfAnalogInTriggerPositionSet(handle, c_double(0.0))
    ad3.dwf.FDwfAnalogInConfigure(handle, c_int(1), c_int(1))
    ad3.scope_setup.window = (ad3.CHIP_OFFSET - ad3.CHIP_RANGE / 2,
                              ad3.CHIP_OFFSET + ad3.CHIP_RANGE / 2)


def read_buffers(handle) -> dict[int, list[float]]:
    out = {}
    for ch in (RESET_CH, Q_CH):
        buf = (c_double * NSAMPLES)()
        ad3.dwf.FDwfAnalogInStatusData(handle, c_int(ch), buf, c_int(NSAMPLES))
        out[ch] = list(buf)
    return out


def crossing(values: list[float], level: float, falling: bool) -> float | None:
    """Sample index where the trace crosses `level`, linearly interpolated
    between the two samples that straddle it. Fractional on purpose: the
    whole point is not to be limited to the sample interval."""
    for i in range(1, len(values)):
        a, b = values[i - 1], values[i]
        if (falling and a > level >= b) or (not falling and a < level <= b):
            if b == a:
                return float(i)
            return (i - 1) + (a - level) / (a - b)
    return None


def edge_time(values: list[float], lo_frac=0.1, hi_frac=0.9) -> float | None:
    """10%-90% width of the transition, in samples, for context only."""
    lo, hi = min(values), max(values)
    span = hi - lo
    if span < 1.0:
        return None
    first = crossing(values, lo + hi_frac * span, falling=True)
    last = crossing(values, lo + lo_frac * span, falling=True)
    return None if first is None or last is None else last - first


def start_stimulus(handle, freq: float) -> None:
    """SET and RESET as two non-overlapping square waves.

    One period is: SET high (first quarter), released, RESET high (third
    quarter), released. So the latch is written to a 1, holds it, is
    written to a 0 and holds that, once per period -- the testbench's
    sequence, repeating, with every transition a genuine DAC edge. The
    two channels are started in one call so the phase between them holds.
    """
    for ch, phase in ((0, 0.0), (1, 180.0)):
        ad3.dwf.FDwfAnalogOutNodeEnableSet(handle, c_int(ch), c_int(0), c_int(1))
        ad3.dwf.FDwfAnalogOutNodeFunctionSet(handle, c_int(ch), c_int(0),
                                             c_ubyte(ad3.funcSquare))
        ad3.dwf.FDwfAnalogOutNodeFrequencySet(handle, c_int(ch), c_int(0), c_double(freq))
        ad3.dwf.FDwfAnalogOutNodeAmplitudeSet(handle, c_int(ch), c_int(0),
                                              c_double(VAPWR / 2))
        ad3.dwf.FDwfAnalogOutNodeOffsetSet(handle, c_int(ch), c_int(0), c_double(VAPWR / 2))
        ad3.dwf.FDwfAnalogOutNodeSymmetrySet(handle, c_int(ch), c_int(0), c_double(25.0))
        ad3.dwf.FDwfAnalogOutNodePhaseSet(handle, c_int(ch), c_int(0), c_double(phase))
    ad3.dwf.FDwfAnalogOutConfigure(handle, c_int(-1), c_int(1))   # both, together
    time.sleep(0.2)


def one_capture(handle, rate: float) -> dict | None:
    """Arm and wait for the next RESET edge in the free-running stimulus."""
    arm(handle, rate)
    status = c_ubyte()
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        ad3.dwf.FDwfAnalogInStatus(handle, c_int(1), byref(status))
        if status.value == STATE_DONE:
            break
        time.sleep(0.002)
    else:
        return None

    samples = read_buffers(handle)
    ad3.check_clipping(samples, "edge: ")

    t_reset = crossing(samples[RESET_CH], MIDRAIL, falling=False)
    t_q = crossing(samples[Q_CH], MIDRAIL, falling=True)
    if t_reset is None or t_q is None:
        return None
    stimulus = edge_time([-v for v in samples[RESET_CH]])   # rising edge, so invert
    return {
        "delay_ns": (t_q - t_reset) / rate * 1e9,
        "stimulus_1090_ns": None if stimulus is None else stimulus / rate * 1e9,
        "samples": samples,
    }


def main() -> None:
    args = sys.argv[1:]
    port = args[args.index("--port") + 1] if "--port" in args else None
    if "--no-program" not in args:
        program_chip(port)
    print(wiring_table())

    handle = ad3.open_device()
    try:
        rate = max_rate(handle)
        print(f"  capturing at {rate / 1e6:.0f} MS/s "
              f"({1 / rate * 1e9:.1f} ns per sample), {NSAMPLES} samples, "
              f"triggered on Q falling through {MIDRAIL} V\n")
        start_stimulus(handle, STIMULUS_HZ)
        results, trace = [], None
        for _ in range(CAPTURES):
            got = one_capture(handle, rate)
            if got is None:
                continue
            trace = trace or got["samples"]
            results.append({k: got[k] for k in ("delay_ns", "stimulus_1090_ns")})
    finally:
        ad3.close(handle)

    if not results:
        raise SystemExit(
            "no capture triggered.\n\n"
            "  The scope waits for Q to fall through mid-rail. If Q is not high when\n"
            "  RESET arrives there is no falling edge to trigger on -- check that the\n"
            "  SET lead is on the pad the wiring table names, and that the chip still\n"
            "  holds the bitstream (re-run without --no-program)."
        )

    delays = [r["delay_ns"] for r in results]
    stimulus = [r["stimulus_1090_ns"] for r in results if r["stimulus_1090_ns"]]
    out = Path("build/srlatch_silicon_edge.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"rate": rate, "captures": results,
                               "trace": {"reset": trace[RESET_CH], "q": trace[Q_CH]}}))

    print(f"  RESET to Q, mid-rail to mid-rail   {statistics.mean(delays):6.2f} ns"
          f"   (sd {statistics.pstdev(delays):.2f} ns over {len(delays)} captures)")
    if stimulus:
        print(f"  the RESET edge itself, 10%-90%     {statistics.mean(stimulus):6.2f} ns")
    print(f"\n  The delay is what to compare, and only against a deck driven with that\n"
          "  same stimulus edge -- tb_srlatch.sch's treset uses a 1 ns step, which no\n"
          "  wavegen can make. Run tools/run_srlatch_measured_edge.sh for the\n"
          "  like-for-like pair.")
    print(f"\n== {len(results)} captures written to {out}")


if __name__ == "__main__":
    main()
