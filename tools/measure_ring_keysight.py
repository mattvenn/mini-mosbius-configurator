#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Measure examples/ringosc's ua3 amplitude and frequency with a bench scope
instead of the AD3.

This is the ring-oscillator counterpart to
`tools/measure_inverter_risetime_keysight.py`: the AD3's own scope input
channels are spec'd at 9 MHz @ -3dB without a BNC adapter (Digilent's AD3
datasheet, sec. 6.1), well under the ring's ~40 MHz, so
`tools/ad3/measure_ring_ad3.py` never trusted amplitude from it -- and a
live comparison between the AD3's two (nominally matched) input channels
on the identical node, at the identical moment, still read ~750 mV on one
and ~300 mV on the other, which only demonstrates the instrument is the
limit, not which of the two numbers (if either) is real. A Keysight
HD304MSO has far more bandwidth than 40 MHz needs, so pointing it at ua3
gets a trustworthy number.

Unlike the inverter, the ring needs no stimulus -- it free-runs the
moment it is programmed -- so this script does not touch the AD3 at all,
only `mosbius.program.program()` to load the bitstream and pyvisa/SCPI to
read the scope. Wiring is a single channel to ua3 plus a ground
reference; every other `ua` pad on this design is a loop node and must
stay untouched (see `tools/ad3/measure_ring_ad3.py`'s docstring for what
happened the one time a lead landed on one of those instead).

**Check the channel's bandwidth-limit filter is OFF before trusting the
result.** Many scopes ship a 20 MHz (or 25 MHz) low-pass "BW Limit"
toggle per channel, meant for cleaning up noisy low-speed signals, and it
would attenuate a 40 MHz ring output by a large and completely
unhelpful amount -- the exact same failure shape this script exists to
rule out on the AD3, just moved to a different instrument. This script
queries `:CHANnel<n>:BWLimit?` and warns if it reads back enabled, but
that command's exact name is not verified against this specific
instrument the way the `:MEASure:*` ones below are (see the note in
`tools/measure_inverter_risetime_keysight.py`), so treat the front-panel
Channel menu as the source of truth if the query errors out silently.

Keysight control follows `shuttle-ttgf26a/simple-signal-generator`'s
`measure_frequency.py` / `test/test_hil.py`, the same as
`tools/measure_inverter_risetime_keysight.py`: plain SCPI over pyvisa,
`:MEASure:<kind> CHANnel<n>` to arm a measurement slot and
`:MEASure:<kind>? CHANnel<n>` to read it back, `> 1e30` as "no valid
measurement". `:MEASure:VPP?` and `:MEASure:FREQuency?` are the same
family of command as that script's already-verified `:MEASure:RISetime?`
/ `:MEASure:FALLtime?` / `:MEASure:DELay?`.

Run from the repo root, on the host (needs the demoboard's serial port
and the scope's LAN/USB/GPIB link):

    python3 tools/measure_ring_keysight.py TCPIP0::<scope-ip>::inst0::INSTR
    python3 tools/measure_ring_keysight.py --list
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

import pyvisa

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mosbius.bitstream import unpack  # noqa: E402
from mosbius.model import SwitchConfig  # noqa: E402
from mosbius.program import (  # noqa: E402
    ProgramError,
    ibias_warning,
    program,
)
from mosbius.pads import format_analog_header, pads_in_use  # noqa: E402

# examples/ringosc as the router placed it on 2026-08-28 -- the same string
# tools/ad3/measure_ring_ad3.py programs. It is a record of an experiment,
# not a cached build artifact: if the router's allocation ever changes,
# re-route and re-measure rather than editing this string.
BITSTREAM = "3f008803f004001401000210188406000050040100000019"
PROJECT, SHUTTLE = "tt_um_tnt_mosbius", "ttsky25a"

INVALID = 1e30  # Keysight's sentinel for "no valid measurement" (test_hil.py)


def program_chip(port: str | None) -> None:
    config = SwitchConfig.from_bitstream(BITSTREAM)
    print("== loading the ring oscillator onto the chip")
    try:
        result = program(config, project=PROJECT, port=port)
    except ProgramError as exc:
        raise SystemExit(f"programming failed -- nothing measured\n\n{exc}")
    warning = ibias_warning(result, config)
    if warning:
        print(warning)


def wiring_table(channel: int) -> str:
    pads = pads_in_use(SwitchConfig(bits=unpack(BITSTREAM)), SHUTTLE, PROJECT)
    probe = pads["ua3"]
    loop = ", ".join(f"{pad} ({name})" for name, pad in sorted(pads.items()) if name != "ua3")
    out = [
        "\n  Wiring:\n",
        "    lead                pad      signal",
        "    -----------------   -----    ------------------------------------------",
        f"    Keysight CH{channel}         {probe:<8s} ua3, the buffered output",
        "    ground               gnd      scope reference",
        f"    every other lead     --       KEEP OFF {loop}: those are loop nodes,",
        "                                  and a lead on one stops the oscillator dead",
    ]
    return "\n".join(out) + "\n\n" + format_analog_header(pads) + "\n"


def _read(scope, cmd: str, require_positive: bool = True) -> float | None:
    raw = scope.query(cmd).strip()
    try:
        value = float(raw)
    except ValueError:
        return None
    if abs(value) >= INVALID:
        return None
    if require_positive and value <= 0:
        return None
    return value


def check_bandwidth_limit(scope, channel: int) -> None:
    try:
        raw = scope.query(f":CHANnel{channel}:BWLimit?").strip()
    except Exception:
        print("  (could not query the channel's bandwidth-limit setting -- check the\n"
              "   front-panel Channel menu by hand: it must be OFF/full bandwidth, or a\n"
              "   40 MHz signal reads back attenuated for the same reason the AD3's\n"
              "   9 MHz flywire leads did.)")
        return
    if raw in ("1", "ON"):
        print(f"  WARNING: CHANnel{channel}'s bandwidth-limit filter reads back ON.\n"
              "  That typically means a 20-25 MHz low-pass ahead of the ADC -- it will\n"
              "  attenuate a 40 MHz ring output the same way the AD3's flywire leads\n"
              "  did. Turn it off in the Channel menu before trusting this measurement.")


def measure(resource: str, channel: int, duration: float, interval: float,
           timebase: float | None) -> dict:
    rm = pyvisa.ResourceManager()
    scope = rm.open_resource(resource)
    scope.timeout = 5000
    print(f"Connected: {scope.query('*IDN?').strip()}")

    if timebase is not None:
        scope.write(f":TIMebase:SCALe {timebase:.3e}")
        scope.write(":RUN")

    check_bandwidth_limit(scope, channel)

    scope.write(f":TRIGger:EDGE:SOURce CHANnel{channel}")
    scope.write(f":MEASure:VPP CHANnel{channel}")
    scope.write(f":MEASure:FREQuency CHANnel{channel}")
    time.sleep(1.0)   # let the measurement slots settle before the first read

    vpp, freq = [], []
    end_time = time.monotonic() + duration
    while time.monotonic() < end_time:
        p = _read(scope, f":MEASure:VPP? CHANnel{channel}")
        if p is not None:
            vpp.append(p)
        f = _read(scope, f":MEASure:FREQuency? CHANnel{channel}")
        if f is not None:
            freq.append(f)
        time.sleep(interval)

    scope.close()
    rm.close()
    return {"vpp": vpp, "freq": freq}


def report(results: dict) -> None:
    vpp = results["vpp"]
    if not vpp:
        print("No valid Vpp samples collected -- check the trigger is finding the\n"
              "edge on the channel and that the probe is actually on ua3.")
        return

    mean_vpp = statistics.mean(vpp)
    sd_vpp = statistics.pstdev(vpp) if len(vpp) > 1 else 0.0
    print(f"\n  ua3, Vpp     {mean_vpp * 1e3:7.1f} mV   "
          f"(sd {sd_vpp * 1e3:.1f} mV over {len(vpp)} samples)")

    freq = results["freq"]
    if freq:
        mean_freq = statistics.mean(freq)
        sd_freq = statistics.pstdev(freq) if len(freq) > 1 else 0.0
        print(f"  ua3, frequency   {mean_freq / 1e6:7.3f} MHz   "
              f"(sd {sd_freq / 1e3:.2f} kHz over {len(freq)} samples)")

    print("\n  Against examples/ringosc/README.md's other numbers:")
    print("    as drawn, ideal wires             0.198 Vpp  @ 2.289 GHz")
    print("    as routed, real switch matrix      1.72 Vpp  @ 43.89 MHz")
    print("    AD3, flywire on Input 2 (2+)      ~0.27-0.30 Vpp  @ ~39.5 MHz")
    print("    AD3, flywire on Input 1 (1+)      ~0.75-0.81 Vpp  @ ~39.6 MHz")
    print("      (the AD3 pair disagreeing on the identical node is the reason")
    print("       this script exists -- neither AD3 number was trustworthy)")
    if vpp:
        print(f"    measured here (Keysight)          {mean_vpp:.3f} Vpp"
              + (f"  @ {statistics.mean(freq) / 1e6:.3f} MHz" if freq else ""))


def list_devices() -> None:
    rm = pyvisa.ResourceManager()
    resources = rm.list_resources()
    if not resources:
        print("No VISA devices found.")
        return
    for r in resources:
        try:
            dev = rm.open_resource(r)
            dev.timeout = 2000
            idn = dev.query("*IDN?").strip()
            dev.close()
            print(f"{r}\n  {idn}")
        except Exception:
            print(f"{r}\n  (no IDN response)")
    rm.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("resource", nargs="?",
                    help="Keysight VISA resource string, e.g. TCPIP0::192.168.50.11::inst0::INSTR")
    ap.add_argument("--list", action="store_true", help="List available VISA devices and exit")
    ap.add_argument("--channel", type=int, default=1,
                    help="Keysight channel wired to ua3 (default: 1)")
    ap.add_argument("--port", default=None, help="demoboard serial port")
    ap.add_argument("--no-program", action="store_true")
    ap.add_argument("--duration", type=float, default=10.0, help="seconds (default: 10)")
    ap.add_argument("--interval", type=float, default=0.2, help="seconds between reads (default: 0.2)")
    ap.add_argument("--timebase", type=float, default=5e-9,
                    help="seconds/div to set before measuring, or 0 to leave the scope's "
                         "current setting alone (default: 5e-9, about two ring periods across "
                         "the screen)")
    args = ap.parse_args()

    if args.list:
        list_devices()
        return
    if not args.resource:
        ap.error("resource is required unless --list is specified")

    if not args.no_program:
        program_chip(args.port)
    print(wiring_table(args.channel))
    input("  Press Enter once that is wired... ")

    results = measure(args.resource, args.channel, args.duration, args.interval,
                      None if args.timebase == 0 else args.timebase)
    report(results)


if __name__ == "__main__":
    main()
