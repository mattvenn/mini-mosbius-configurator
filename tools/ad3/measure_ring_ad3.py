#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Measure examples/ringosc on real silicon with an Analog Discovery.

Loads the ring oscillator's bitstream onto the chip and measures the
frequency of its buffered output, so it can be compared as drawn, as
routed (`mosbius simulate`) and as measured. Defaults to tnt's part
(`tt_um_tnt_mosbius`); `--project tt_um_mosbius` measures the same
schematic routed for Andrew Kang's part instead. Run from the repo root,
on the host, since it needs USB:

    python3 tools/ad3/measure_ring_ad3.py
    python3 tools/ad3/measure_ring_ad3.py --project tt_um_mosbius

**Take nothing off a loop node.** The ring's three stages feed each other,
so `ua1` and `ua2` are inside the feedback path and a probe there is a
circuit change, not a measurement. That is why the design has a fourth
inverter buffering the loop out to a fourth pin -- `ua4` as of 2026-09-08
on both parts (it was `ua3` on tnt's part before that, until fixing Andrew
Kang's routing needed the loop's own two pins to sit somewhere his chip's
diff-pair-restricted rows leave free -- see CLAUDE.md). `ua4` is outside
the loop either way, so a probe on it models a probe. This is not
theoretical. With an Analog Discovery's W1 and 1+ leads left clipped to a
loop node, this chip did not oscillate at all -- the loop node sat at 0 V
and the buffered output at a steady 2.85 V, which looks exactly like a
circuit that does not work rather than like a measurement error.
Unclipping both leads started a 39.5 MHz oscillator.

**Frequency is the only number worth quoting from this measurement.** At
~40 MHz the amplitude is attenuated by an unknown factor: the Analog
Discovery's flywire leads roll off well before that (the specified
bandwidth is for the BNC adapter), so what reaches the ADC is neither the
chip's swing nor its waveform. A frequency estimate is indifferent to
that roll-off; a level or a rise time taken here would be meaningless --
confirmed 2026-09-02, when its two channels read ~300 mV and ~750 mV on
the identical pad. `tools/measure_ring_keysight.py` gets a trustworthy
amplitude instead.

Pad letters are derived from the bitstream and the shuttle index by
`mosbius/pads.py`, never written down here: which pad a design's `ua[k]`
reaches depends on where the project sits on that shuttle.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

import numpy as np

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
RATE, NSAMPLES, CAPTURES = 1e8, 16384, 5

# Each entry is a record of a specific routing, not a cached build artifact:
# if the router's allocation for a part ever changes, re-route and
# re-measure rather than editing the bitstream here, or the published
# numbers quietly stop describing the configuration that was actually on
# the chip.
PROJECTS = {
    # examples/ringosc as the router placed it on 2026-09-08, after moving
    # the buffered output from ua3 to ua4 so the same schematic also routes
    # on Andrew Kang's part (see the module docstring). ua1/ua2, the loop's
    # own pins, are unchanged from the 39.528 MHz measurement this replaces
    # -- they are permanently bonded to bus_A[1]/bus_A[3] on this part
    # regardless of what else is routed, so the loop itself is the same
    # circuit; only the buffer tap's pin, and the internal net's bus row,
    # moved. SIM is a fresh as-drawn/as-routed run of tb_ring.sch against
    # this bitstream, 2026-09-08 -- pending a bench re-measurement to
    # replace examples/ringosc/README.md's 39.528 MHz, which still
    # describes the pre-2026-09-08 ua3 routing.
    "tt_um_tnt_mosbius": {
        "chip": TNT,
        "bitstream": "3f008803f004001401000110184406000050040100000011",
        "sim": {"drawn_ghz": 2.229, "routed_mhz": 43.92},
    },
    # examples/ringosc routed for tt_um_mosbius on 2026-09-08. First
    # silicon measurement of the ring oscillator on this part. drawn_ghz is
    # within 0.1% of tnt's, matching the near-zero PMOS-finger-count effect
    # this whole branch is about; routed_mhz genuinely differs (his bus rows
    # carry meaningfully different wire capacitance -- see
    # Chip._KANG_BUS_WIRE_CAP in mosbius/chips/__init__.py), which is the
    # real reason to measure this circuit rather than assume it too matches.
    "tt_um_mosbius": {
        "chip": KANG,
        "bitstream": "4142c081828820c08000000048180800010303050a040c144",
        "sim": {"drawn_ghz": 2.227, "routed_mhz": 51.69},
    },
}


def wiring_table(pads: dict[str, str]) -> str:
    pads = dict(pads)
    probe = pads.pop("ua4")
    loop = ", ".join(f"{pad} ({name})" for name, pad in sorted(pads.items()))
    return (
        "\n  Wire the Analog Discovery to the demoboard like this:\n\n"
        "    AD3 lead      pad      signal\n"
        "    -----------   -----    ------------------------------------------\n"
        f"    1+ (orange)   {probe:<8s} ua4, the buffered output\n"
        "    1-, GND       GND      scope reference\n"
        f"    every other   --       KEEP OFF {loop}: those are loop\n"
        "    lead                   nodes, and a lead on one stops the\n"
        "                           oscillator dead\n"
        "\n" + format_analog_header({"ua4": probe}) + "\n"
    )


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
    print(f"== loading the ring oscillator onto the chip ({project})")
    try:
        result = program(config, project=project, port=port)
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
    if not args.no_program:
        program_chip(args.project, spec["bitstream"], spec["chip"], args.port)
    print(wiring_table(pads))
    input("  Press Enter once that is wired... ")

    handle = ad3.open_device()
    try:
        ad3.scope_setup(handle, rate=RATE, nsamples=NSAMPLES, rng=5.0, offset=1.65)
        ffts, zcs, trace = [], [], None
        for _ in range(CAPTURES):
            samples = ad3.acquire(handle, nsamples=NSAMPLES, tag="ring: ")[0]
            trace = trace or samples
            f, z = frequency(samples)
            ffts.append(f)
            zcs.append(z)
    finally:
        ad3.close(handle)

    suffix = "_kang" if args.project == "tt_um_mosbius" else ""
    out = Path(f"build/ring{suffix}_silicon_trace.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"rate": RATE, "v": trace}))

    print(f"\n  FFT peak         {statistics.mean(ffts) / 1e6:.3f} MHz "
          f"(spread {(max(ffts) - min(ffts)) / 1e3:.1f} kHz over {CAPTURES} captures)")
    print(f"  zero crossings   {statistics.mean(zcs) / 1e6:.3f} MHz "
          f"(spread {(max(zcs) - min(zcs)) / 1e3:.1f} kHz)")
    print(f"  captured swing   {max(trace) - min(trace):.3f} V pk-pk -- attenuated by the\n"
          "                   leads' bandwidth, NOT the chip's output swing")
    sim = spec["sim"]
    if sim["routed_mhz"] is not None:
        print(f"\n  as-routed sim    {sim['routed_mhz']:.2f} MHz"
              + (f"   (as drawn: {sim['drawn_ghz']:.3f} GHz)" if sim["drawn_ghz"] else ""))
    print(f"\n== trace written to {out}")


if __name__ == "__main__":
    main()
