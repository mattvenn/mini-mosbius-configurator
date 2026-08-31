#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Time the inverter's output rise on real silicon, driven from a DIO pin.

`tools/ad3/measure_inverter_edge_ad3.py` tried this with W1 (the analog
waveform generator) and ruled it out: W1's own 10%-90% edge measured 74 ns,
only a 1.3x margin over the 95 ns it measured on ua2, so that number was
mostly a measurement of W1's DAC-and-amplifier, not the chip. TODO.md named
the untested alternative -- a DIO pin, which switches through a plain logic
buffer instead -- and this is that experiment. Run from the repo root, on
the host:

    python3 tools/ad3/measure_inverter_digital_edge_ad3.py

**Wiring is different from every other script here.** DIO0 lives on the
Analog Discovery's digital I/O header, a separate physical connector from
the W1/W2/1+/2+/... flying leads the analog scripts use. You need two
jumper wires from that pin: one to the `ua1` pad, and one to the `1+` lead,
so the same "measure what the stimulus actually delivers, not what it was
commanded to do" rule this whole file follows still applies -- if DIO0's
own logic swing turns out to be something other than 0..3.3 V, or its edge
turns out to be no faster than W1's, that will show up on `1+` exactly the
way it did for the analog generator.

**The Digital Out API this drives is new to this codebase and unverified
against real hardware** -- see `ad3.py`'s "Digital output (DIO)" section.
If `digital_out_square()` raises `AttributeError`, a function name in
there is wrong against your SDK version; if it configures without error
but ua1 never moves, check the jumper to `ua1` before suspecting the API.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
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
from mosbius.pads import format_analog_header, pads_in_use  # noqa: E402

# Same configuration as tools/ad3/measure_inverter_ad3.py and
# tools/ad3/measure_inverter_edge_ad3.py: examples/inverter as the router
# placed it on 2026-08-28, ua1 in, ua2 out.
BITSTREAM = "080000004010000001000000000000000040000400000000"
PROJECT = "tt_um_tnt_mosbius"
SHUTTLE = "ttsky25a"
MIDRAIL = 1.65

DIO_CHANNEL = 0
NSAMPLES = 4096
CAPTURES = 20
STIMULUS_HZ = 20_000.0

IN_CH, OUT_CH = 0, 1     # 1+ monitors ua1 (fed from DIO0), 2+ is ua2


def wiring_table() -> str:
    pads = pads_in_use(SwitchConfig(bits=unpack(BITSTREAM)), SHUTTLE, PROJECT)
    rows = [
        (f"DIO{DIO_CHANNEL} (digital header)", pads["ua1"],
         "inverter input, design ua1 -- the edge being driven"),
        (f"DIO{DIO_CHANNEL} (digital header)", "1+ (orange)",
         "the same pin, also jumpered to the scope so the stimulus"),
        ("", "", "is measured where it arrives, not where it was commanded"),
        ("2+ (blue)", pads["ua2"], "inverter output, design ua2 -- the edge being timed"),
        ("1-, 2-, GND", "gnd", "scope reference -- both inputs are differential"),
    ]
    out = ["\n  Wire the Analog Discovery to the demoboard like this. Two jumpers\n"
           "  from DIO%d, not one -- see this script's docstring for why:\n" % DIO_CHANNEL,
           "    AD3 lead                pad/lead   signal",
           "    ---------------------   --------   ------------------------------"]
    for lead, pad, what in rows:
        out.append(f"    {lead:<23s} {pad:<10s} {what}")
    return "\n".join(out) + "\n\n" + format_analog_header(pads) + "\n"


def program_chip(port: str | None) -> None:
    config = SwitchConfig.from_bitstream(BITSTREAM)
    print("== loading the inverter onto the chip")
    try:
        result = program(config, project=PROJECT, port=port)
    except ProgramError as exc:
        raise SystemExit(f"programming failed -- nothing measured\n\n{exc}")
    warning = ibias_warning(result, config)
    if warning:
        print(warning)


def _smooth(values, k=9):
    out = []
    for i in range(len(values)):
        a, b = max(0, i - k // 2), min(len(values), i + k // 2 + 1)
        out.append(sum(values[a:b]) / (b - a))
    return out


def edge_10_90(values, dt, centre=None, half=200, rising=True):
    """10%-90% width of one transition near `centre`, in seconds.

    Same shape as `tools/ad3/measure_inverter_edge_ad3.py`'s `edge_10_90()`.
    """
    n = len(values)
    centre = n // 2 if centre is None else centre
    a, b = max(0, centre - half), min(n, centre + half)
    lo = statistics.median(values[max(0, a - 300):a] or values[:1])
    hi = statistics.median(values[b:b + 300] or values[-1:])
    if abs(hi - lo) < 0.5:
        return None
    seg = _smooth(values[a:b])
    t10 = ad3.crossing(seg, lo + 0.1 * (hi - lo), rising, dt)
    t90 = ad3.crossing(seg, lo + 0.9 * (hi - lo), rising, dt)
    return None if t10 is None or t90 is None else abs(t90 - t10)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", default=None)
    ap.add_argument("--no-program", action="store_true")
    ap.add_argument("--captures", type=int, default=CAPTURES)
    args = ap.parse_args()

    if not args.no_program:
        program_chip(args.port)
    print(wiring_table())
    input("  Press Enter once that is wired... ")

    with ad3.device() as handle:
        ad3.digital_out_square(handle, DIO_CHANNEL, STIMULUS_HZ, symmetry=50.0)
        time.sleep(0.3)

        rate = ad3.max_rate(handle)
        dt = 1.0 / rate
        print(f"  driving ua1 from DIO{DIO_CHANNEL} at {STIMULUS_HZ / 1e3:.0f} kHz, "
              f"capturing at {rate / 1e6:.0f} MS/s ({dt * 1e9:.0f} ns/sample), "
              f"{NSAMPLES} samples, triggered on ua2 rising through {MIDRAIL} V\n")

        ad3.scope_setup_triggered(handle, rate, NSAMPLES, OUT_CH, MIDRAIL,
                                  rising=True, position=0.0)

        stim_edges, out_edges, trace = [], [], None
        try:
            for i in range(args.captures):
                got = ad3.capture_triggered(handle, NSAMPLES, tag=f"capture {i + 1}: ")
                if got is None:
                    print(f"  capture {i + 1} never triggered -- skipping")
                    continue
                trace = trace or got
                stim = edge_10_90(got[IN_CH], dt, rising=False)   # ua1 falls
                out = edge_10_90(got[OUT_CH], dt, rising=True)    # ua2 rises
                if stim is not None:
                    stim_edges.append(stim)
                if out is not None:
                    out_edges.append(out)
        finally:
            ad3.digital_out_stop(handle)   # close() does not do this

    if not out_edges:
        raise SystemExit(
            "no output edge could be timed.\n\n"
            "  Check both DIO0 jumpers (to ua1 and to 1+) and that the chip still\n"
            "  holds the bitstream (re-run without --no-program). If ua1's own edge\n"
            "  is also missing, the DIO wiring or the Digital Out setup is the\n"
            "  problem, not the timing math -- see this script's docstring."
        )

    out_ns = [e * 1e9 for e in out_edges]
    stim_ns = [e * 1e9 for e in stim_edges]
    out_path = Path("build/inverter_silicon_digital_edge.json")
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps({
        "rate": rate, "out_edge_ns": out_ns, "stim_edge_ns": stim_ns,
        "trace": {"in": trace[IN_CH], "out": trace[OUT_CH]} if trace else None,
    }))

    mean_out = statistics.mean(out_ns)
    sd_out = statistics.pstdev(out_ns) if len(out_ns) > 1 else 0.0
    print(f"  ua2, 10%-90% rise    {mean_out:6.2f} ns   "
          f"(sd {sd_out:.2f} ns over {len(out_ns)} captures)")
    if stim_ns:
        mean_stim = statistics.mean(stim_ns)
        margin = mean_out / mean_stim if mean_stim else None
        print(f"  ua1, 10%-90% fall    {mean_stim:6.2f} ns   (DIO{DIO_CHANNEL}'s own edge, as it arrives)")
        if margin:
            if margin >= 3:
                verdict = "comfortably clear of the stimulus -- trust this number"
            elif margin >= 1.5:
                verdict = ("not comfortably clear of the stimulus -- treat this as an "
                           "upper bound, not a clean measurement")
            else:
                verdict = "close to the stimulus's own edge -- this times the DIO driver more than the chip"
            print(f"  margin (output / stimulus)   {margin:.1f}x   -- {verdict}")
        print(f"\n  Against W1's analog generator ({74.41:.2f} ns measured "
              f"2026-08-31 by measure_inverter_edge_ad3.py):")
        if mean_stim < 74.41:
            print(f"  DIO{DIO_CHANNEL} is {74.41 / mean_stim:.1f}x faster -- worth using for this measurement.")
        else:
            print(f"  DIO{DIO_CHANNEL} is not faster ({mean_stim:.1f} vs 74.41 ns) -- this route doesn't"
                  f" help either.")
    print("\n  Sim comparison needs the AD3's own loading, not the sheet's default:\n"
          "  8.16 ns (as drawn) and 24.63 ns (as routed) are both at rprobe=10meg\n"
          "  cprobe=10p, while the AD3 presents rprobe=1meg cprobe=24p on this pin.\n"
          "  Re-run tb_inverter.sch's .tran deck with those params before comparing\n"
          "  this number against either one.")
    print(f"\n== {len(out_edges)} usable captures written to {out_path}")


if __name__ == "__main__":
    main()
