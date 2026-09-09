#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Measure examples/inverter on real silicon with an Analog Discovery.

Loads the inverter bitstream onto the chip, then sweeps its input and
records the DC transfer curve, so the same circuit can be compared as
drawn, as routed (`mosbius simulate`) and as measured. Run it from the
repo root, on the host -- not in the container, since it needs USB:

    python3 tools/ad3/measure_inverter_ad3.py
    python3 tools/ad3/measure_inverter_ad3.py --project tt_um_mosbius

Defaults to tnt's part (`tt_um_tnt_mosbius`); `--project tt_um_mosbius`
measures the same schematic routed for Andrew Kang's part instead. Both
routings put the design on ua1 (input)/ua2 (output) with 100 uA of bias,
but land on different physical pads -- the wiring table and pad picture
below are for whichever `--project` is running, not memorised.

**Which pads to clip onto is derived, not written down here.** A design's
`ua[k]` is not a pad letter and the relationship changes with the shuttle,
so `mosbius/pads.py` composes it from the shuttle index and the board's own
pad lettering -- see that module for where each half comes from. What this
script contributes is which pins the *bitstream* uses, since the bench
state is the configuration in the socket.

"""

from __future__ import annotations

import argparse
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
STEP = 0.025

# Each entry is a record of a specific routing, not a cached build artifact:
# if the router's allocation for a part ever changes, re-route and
# re-measure rather than editing the bitstream here, or the published
# numbers quietly stop describing the configuration that was actually on
# the chip.
PROJECTS = {
    # examples/inverter as the router placed it on 2026-08-28: ua1 in, ua2
    # out. Every silicon number in that example's README was measured with
    # this configuration.
    "tt_um_tnt_mosbius": {
        "chip": TNT,
        "bitstream": "080000004010000001000000000000000040000400000000",
        "out_suffix": "",
        "sim": {"drawn": 1.605, "routed": 1.600},
        # Specific to this instrument, recorded because it explains why the
        # absolute threshold is not to be trusted before calibrating: see
        # CLAUDE.md. Not a claim about any other Analog Discovery.
        "calibration_note": (
            "  On this unit calibration moved it 44 mV, from 1.555 to 1.599 V,\n"
            "  and 1.599 V is what the as-routed deck predicts."
        ),
    },
    # examples/inverter routed for tt_um_mosbius on 2026-09-08 -- same
    # allocation (ua1 in, ua2 out), different part. First silicon
    # measurement of this part in this repo.
    "tt_um_mosbius": {
        "chip": KANG,
        "bitstream": "0000008002040000000000000000000000020200000400102",
        "out_suffix": "_kang",
        "sim": {"drawn": 1.605, "routed": 1.600},
        "calibration_note": None,
    },
}


def wiring_table(pads: dict[str, str]) -> str:
    rows = [
        ("W1 (yellow)", pads["ua1"], "inverter input, design ua1"),
        ("1+ (orange)", pads["ua1"], "the same node, monitors the drive"),
        ("2+ (blue)", pads["ua2"], "inverter output, design ua2"),
        ("1-, 2-, GND", "any gnd", "scope reference -- differential inputs,"),
        ("", "", "so these must be grounded or every reading is wrong"),
    ]
    out = ["\n  Wire the Analog Discovery to the demoboard like this:\n",
           "    AD3 lead      pad      signal",
           "    -----------   -----    ------------------------------------------"]
    for lead, pad, what in rows:
        out.append(f"    {lead:<13s} {pad:<8s} {what}")
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
    print(f"== loading the inverter onto the chip ({project})")
    try:
        result = program(config, project=project, port=port)
    except ProgramError as exc:
        raise SystemExit(f"programming failed -- nothing measured\n\n{exc}")
    warning = ibias_warning(result, config)
    if warning:
        print(warning)


def sweep(handle) -> list[tuple[float, float]]:
    ad3.wavegen(handle, ch=0, func=ad3.funcDC, amp=0.0, offset=0.0)
    ad3.scope_setup(handle, rate=1e5, nsamples=4000)
    points, level = [], 0.0
    while level <= VAPWR + 1e-9:
        ad3.wavegen(handle, ch=0, func=ad3.funcDC, amp=0.0, offset=level)
        time.sleep(0.03)
        samples = ad3.acquire(handle, nsamples=4000, tag=f"at {level:.3f} V drive: ")
        points.append((ad3.mean(samples, 0), ad3.mean(samples, 1)))
        level += STEP
    ad3.wavegen(handle, ch=0, func=ad3.funcDC, amp=0.0, offset=0.0)   # park at 0 V
    return points


def report(points: list[tuple[float, float]], sim: dict, calibration_note: str | None) -> None:
    vin = [p[0] for p in points]
    vout = [p[1] for p in points]
    crossing = min(range(len(points)), key=lambda i: abs(vout[i] - vin[i]))
    slopes = [((vout[i + 1] - vout[i - 1]) / (vin[i + 1] - vin[i - 1]), vin[i])
              for i in range(1, len(points) - 1)]
    gain, at = min(slopes)
    print(f"\n  VOH (input {vin[0]:+.3f} V)   {vout[0]:+.4f} V")
    print(f"  VOL (input {vin[-1]:+.3f} V)   {vout[-1]:+.4f} V")
    print(f"  switching threshold      {vin[crossing]:.3f} V   (output = input)")
    print(f"  peak gain                {gain:.1f} V/V at {at:.3f} V")
    print("\n  Against the same circuit simulated:\n")
    print("               as drawn   as routed   on silicon")
    print("               --------   ---------   ----------")
    print(f"    trip point   {sim['drawn']:.3f}      {sim['routed']:.3f}"
          f"       {vin[crossing]:.3f} V")
    print("\n  An uncalibrated Analog Discovery carries tens of mV of offset per\n"
          "  channel, so run WaveForms' calibration (Settings -> Device Manager ->\n"
          "  Calibrate) before trusting any of this. The gain survives it -- it is a\n"
          "  ratio of differences, one per channel, so offsets cancel -- but the\n"
          "  levels and the switching threshold do not: the threshold is where\n"
          "  channel 2 crosses channel 1, so it moves by the *difference* of the two\n"
          "  offsets.")
    if calibration_note:
        print(calibration_note)


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

    with ad3.device() as handle:
        points = sweep(handle)

    out = Path(f"build/inverter{spec['out_suffix']}_silicon_dc.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(points))
    print(f"== {len(points)} points written to {out}")
    report(points, spec["sim"], spec["calibration_note"])


if __name__ == "__main__":
    main()
