#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Measure examples/inverter on real silicon with an Analog Discovery.

Loads the inverter bitstream onto the chip, then sweeps its input and
records the DC transfer curve, so the same circuit can be compared as
drawn, as routed (`mosbius simulate`) and as measured. Run it from the
repo root, on the host -- not in the container, since it needs USB:

    python3 tools/measure_inverter_ad3.py

**Which pads to clip onto is per shuttle, and not guessable.** A design's
`ua[k]` is not the PCB pad letter: the chip's analog pins are muxed, so
which internal analog index a project's `ua[k]` lands on depends on where
that project was placed on that shuttle. The authority is the project
page, e.g. https://tinytapeout.com/chips/ttsky25a/tt_um_tnt_mosbius,
whose Analog pins table gives `ua` -> PCB pin -> internal index. The
machine-readable half of it is the shuttle index --
https://index.tinytapeout.com/ttsky25a.json gives this project
`analog_pins: [5, 0, 4, 1, 3, 2]`, i.e. design `ua[k]` -> internal index
-- and lining that up against the page's pad column gives index -> pad
0=C 1=D 2=F 3=G 4=J 5=K, the carrier's six analog pads in letter order.
That last step is inferred from this one project's table rather than read
from a Tiny Tapeout spec, so PADS below is written out per shuttle and
checked against the page rather than computed.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ad3  # noqa: E402

# examples/inverter as the router places it: ua1 in, ua2 out.
BITSTREAM = "080000004010000001000000000000000040000400000000"
PROJECT = "tt_um_tnt_mosbius"
PADS = {"ua1": "C", "ua2": "J", "ibias": "K"}          # ttsky25a, see docstring
VAPWR = 3.3
STEP = 0.025


def wiring_table() -> str:
    return (
        "\n  Wire the Analog Discovery to the demoboard like this:\n\n"
        "    AD3 lead     demoboard         signal\n"
        "    ---------    --------------    ------------------------------\n"
        f"    W1 (yellow)  pad {PADS['ua1']}             inverter input, design ua1\n"
        f"    1+ (orange)  pad {PADS['ua1']}             the same node, monitors the drive\n"
        f"    2+ (blue)    pad {PADS['ua2']}             inverter output, design ua2\n"
        "    1-, 2-, GND  demoboard GND     scope reference -- the AD3's inputs\n"
        "                                   are differential, so these must be\n"
        "                                   grounded or every reading is wrong\n"
    )


def program_chip(port: str | None) -> None:
    cmd = [sys.executable, "-m", "mosbius.cli", "program", BITSTREAM, "--project", PROJECT]
    if port:
        cmd += ["--port", port]
    print("== loading the inverter onto the chip")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    print("  " + (result.stdout.strip() or result.stderr.strip()))
    if result.returncode != 0:
        raise SystemExit("programming failed -- nothing measured")


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


def report(points: list[tuple[float, float]]) -> None:
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
    print("\n  Levels carry the AD3's own uncalibrated offset, which is tens of mV\n"
          "  per channel; run the WaveForms calibration if you need them absolute.\n"
          "  The threshold and gain are differences on one channel, so they do not\n"
          "  depend on that offset.")


def main() -> None:
    port = None
    args = sys.argv[1:]
    if "--port" in args:
        port = args[args.index("--port") + 1]
    if "--no-program" not in args:
        program_chip(port)
    print(wiring_table())
    handle = ad3.open_device()
    try:
        points = sweep(handle)
    finally:
        ad3.close(handle)
    out = Path("build/inverter_silicon_dc.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(points))
    print(f"== {len(points)} points written to {out}")
    report(points)


if __name__ == "__main__":
    main()
