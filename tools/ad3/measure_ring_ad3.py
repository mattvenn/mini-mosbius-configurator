#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Measure examples/ringosc on real silicon with an Analog Discovery.

Loads the ring oscillator's bitstream onto the chip and measures the
frequency of its buffered output, so it can be compared as drawn, as
routed (`mosbius simulate`) and as measured. Run from the repo root, on
the host, since it needs USB:

    python3 tools/ad3/measure_ring_ad3.py

**Take nothing off a loop node.** The ring's three stages feed each other,
so `ua1` and `ua2` are inside the feedback path and a probe there is a
circuit change, not a measurement. That is why the design has a fourth
inverter buffering `ua1` out to `ua3`: `ua3` is outside the loop, so a
probe on it models a probe. This is not theoretical. With an Analog
Discovery's W1 and 1+ leads left clipped to `ua1`, this chip did not
oscillate at all -- `ua1` sat at 0 V and `ua3` at a steady 2.85 V, which
looks exactly like a circuit that does not work rather than like a
measurement error. Unclipping both leads started a 39.5 MHz oscillator.

**Frequency is the only number worth quoting from this measurement.** At
~40 MHz the amplitude is attenuated by an unknown factor: the Analog
Discovery's flywire leads roll off well before that (the specified
bandwidth is for the BNC adapter), so what reaches the ADC is neither the
chip's swing nor its waveform. A frequency estimate is indifferent to
that roll-off; a level or a rise time taken here would be meaningless.

Pad letters are derived from the bitstream and the shuttle index by
`mosbius/pads.py`, never written down here: which pad a design's `ua[k]`
reaches depends on where the project sits on that shuttle.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

import numpy as np

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

# examples/ringosc as the router placed it on 2026-08-28 -- the exact
# configuration the 39.528 MHz measurement was taken with.
# It is a record of an experiment, not a cached build artifact: if the
# router's allocation ever changes, re-route and re-measure rather than
# editing this string, or the published numbers quietly stop describing
# the configuration that was actually on the chip.
BITSTREAM = "3f008803f004001401000210188406000050040100000019"
PROJECT = "tt_um_tnt_mosbius"
SHUTTLE = "ttsky25a"
RATE, NSAMPLES, CAPTURES = 1e8, 16384, 5


def wiring_table() -> str:
    pads = pads_in_use(SwitchConfig(bits=unpack(BITSTREAM)), SHUTTLE, PROJECT)
    probe = pads.pop("ua3")
    loop = ", ".join(f"{pad} ({name})" for name, pad in sorted(pads.items()))
    return (
        "\n  Wire the Analog Discovery to the demoboard like this:\n\n"
        "    AD3 lead      pad      signal\n"
        "    -----------   -----    ------------------------------------------\n"
        f"    2+ (blue)     {probe:<8s} ua3, the buffered output\n"
        "    2-, GND       GND      scope reference\n"
        f"    every other   --       KEEP OFF {loop}: those are loop\n"
        "    lead                   nodes, and a lead on one stops the\n"
        "                           oscillator dead\n"
    )


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
    print("== loading the ring oscillator onto the chip")
    try:
        result = program(config, project=PROJECT, port=port)
    except ProgramError as exc:
        raise SystemExit(f"programming failed -- nothing measured\n\n{exc}")
    warning = ibias_warning(result, config)
    if warning:
        print(warning)


def frequency(samples: list[float]) -> tuple[float, float]:
    """Two independent estimates: an interpolated FFT peak, and the mean
    spacing of rising zero crossings. They should agree; if they do not,
    the capture is not a clean oscillation."""
    v = np.array(samples)
    a = v - v.mean()
    spectrum = np.abs(np.fft.rfft(a * np.hanning(len(a))))
    k = int(np.argmax(spectrum[3:])) + 3
    left, peak, right = (np.log(spectrum[k - 1]), np.log(spectrum[k]), np.log(spectrum[k + 1]))
    delta = 0.5 * (left - right) / (left - 2 * peak + right)
    fft_hz = (k + delta) * RATE / len(a)

    sign = np.sign(a)
    crossings = np.where((sign[:-1] < 0) & (sign[1:] >= 0))[0]
    if len(crossings) < 3:
        raise SystemExit(
            "no oscillation on this node: fewer than three zero crossings in "
            f"{len(a) / RATE * 1e6:.0f} us.\n\n"
            "  Check that no lead is touching a loop node (see this file's\n"
            "  docstring), and that the bitstream actually loaded."
        )
    zc_hz = RATE * (len(crossings) - 1) / (crossings[-1] - crossings[0])
    return fft_hz, zc_hz


def main() -> None:
    args = sys.argv[1:]
    port = args[args.index("--port") + 1] if "--port" in args else None
    if "--no-program" not in args:
        program_chip(port)
    print(wiring_table())

    handle = ad3.open_device()
    try:
        ad3.scope_setup(handle, rate=RATE, nsamples=NSAMPLES, rng=5.0, offset=1.65)
        ffts, zcs, trace = [], [], None
        for _ in range(CAPTURES):
            samples = ad3.acquire(handle, nsamples=NSAMPLES, tag="ring: ")[1]
            trace = trace or samples
            f, z = frequency(samples)
            ffts.append(f)
            zcs.append(z)
    finally:
        ad3.close(handle)

    out = Path("build/ring_silicon_trace.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"rate": RATE, "v": trace}))

    print(f"\n  FFT peak         {statistics.mean(ffts) / 1e6:.3f} MHz "
          f"(spread {(max(ffts) - min(ffts)) / 1e3:.1f} kHz over {CAPTURES} captures)")
    print(f"  zero crossings   {statistics.mean(zcs) / 1e6:.3f} MHz "
          f"(spread {(max(zcs) - min(zcs)) / 1e3:.1f} kHz)")
    print(f"  captured swing   {max(trace) - min(trace):.3f} V pk-pk -- attenuated by the\n"
          "                   leads' bandwidth, NOT the chip's output swing")
    print(f"\n== trace written to {out}")


if __name__ == "__main__":
    main()
