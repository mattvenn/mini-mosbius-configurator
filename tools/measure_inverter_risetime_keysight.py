#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Measure the inverter's ua2 rise time with a bench scope instead of the AD3.

This is what closed the inverter's rise-time question in
`examples/inverter/README.md` (38.84 ns, matching the as-routed model): the
AD3's own scope input channels are spec'd at 9 MHz @ -3dB without a BNC
adapter (Digilent's AD3 datasheet, sec. 6.1) -- the same channel
`tools/ad3/measure_inverter_edge_ad3.py` used to measure ua2 at 95.41 ns,
which turned out to be mostly the AD3's own bandwidth, not the inverter's.
A Keysight HD304MSO has far more bandwidth than that, so pointing it at ua2
instead gets the real number.

This script does the whole rig itself now: programs the chip
(`mosbius.program.program()`, same as every other AD3 script here) and
drives ua1 from the AD3's W1 (`ad3.square_wave()`, same as
`tools/ad3/measure_inverter_edge_ad3.py`) while the Keysight does the
observing -- of ua2 on `--out-channel` (default 1), and, if wired, ua1 on
`--in-channel` (default 2), which gets the same "report the stimulus edge
beside the result" treatment every AD3 script in this project follows,
plus the mid-rail input-to-output delay, the best-conditioned quantity this
rig can produce (see `tools/ad3/measure_settling_ad3.py`'s
`midpoint_delay()` for why: a delay common to both channels cancels out of
their difference, where a width does not).

Keysight control follows `shuttle-ttgf26a/simple-signal-generator`'s
`measure_frequency.py` / `test/test_hil.py`: plain SCPI over pyvisa
(LAN/USB/GPIB, whatever the resource string names), `:MEASure:<kind>
CHANnel<n>` to arm a measurement slot and `:MEASure:<kind>? CHANnel<n>` to
read it back, and a `> 1e30` reading as "no valid measurement" -- that
sentinel and the write-then-query shape are both copied from `test_hil.py`,
which has them verified against this exact scope. `:MEASure:DELay
CHANnel<a>,CHANnel<b>` is the same command `test_hil.py`'s
`_measure_delay_cycles()` uses.

**Verify the scope's rise/fall-time definition is 10%-90% before trusting
the result.** Some scopes default a generic "rise time" measurement to
20%-80% (a MIL-STD convention). Check this instrument's threshold setting
(front panel Measure menu, or whatever your firmware's SCPI equivalent is
-- not queried automatically here, since the exact command for this varies
across Keysight firmware and getting it wrong silently would be worse than
not asking) before comparing the number this prints against the figures in
`examples/inverter/README.md`, all of which are 10%-90%.

Run from the repo root, on the host (needs the demoboard's serial port and
the AD3, same as every `tools/ad3/` script):

    python3 tools/measure_inverter_risetime_keysight.py TCPIP0::<scope-ip>::inst0::INSTR
    python3 tools/measure_inverter_risetime_keysight.py --list
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

import pyvisa

sys.path.insert(0, str(Path(__file__).resolve().parent / "ad3"))
import ad3  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mosbius.bitstream import unpack  # noqa: E402
from mosbius.model import SwitchConfig  # noqa: E402
from mosbius.program import (  # noqa: E402
    ProgramError,
    ibias_warning,
    program,
)
from mosbius.pads import format_analog_header, pads_in_use  # noqa: E402

# examples/inverter as the router placed it on 2026-08-28, ua1 in, ua2 out --
# the same string every other inverter measurement script in this project
# programs. It is a record of an experiment, not a cached build artifact: if
# the router's allocation ever changes, re-route and re-measure rather than
# editing this string.
BITSTREAM = "080000004010000001000000000000000040000400000000"
PROJECT, SHUTTLE = "tt_um_tnt_mosbius", "ttsky25a"
VAPWR, MIDRAIL = 3.3, 1.65
STIMULUS_HZ = 20_000.0

INVALID = 1e30  # Keysight's sentinel for "no valid measurement" (test_hil.py)


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


def wiring_table(out_channel: int, in_channel: int | None) -> str:
    pads = pads_in_use(SwitchConfig(bits=unpack(BITSTREAM)), SHUTTLE, PROJECT)
    rows = [("W1 (yellow, AD3)", pads["ua1"], "inverter input, design ua1 -- driven by the AD3")]
    if in_channel:
        rows.append((f"Keysight CH{in_channel}", pads["ua1"],
                     "the same node, so its own edge is measured too"))
    rows.append((f"Keysight CH{out_channel}", pads["ua2"],
                "inverter output, design ua2 -- the edge being timed"))
    rows.append(("grounds", "gnd", "both instruments need a ground reference on this net"))
    out = ["\n  Wiring:\n", "    lead                pad      signal",
           "    -----------------   -----    ------------------------------------------"]
    for lead, pad, what in rows:
        out.append(f"    {lead:<19s} {pad:<8s} {what}")
    return "\n".join(out) + "\n\n" + format_analog_header(pads) + "\n"


def start_ad3_stimulus():
    """Program W1 as ua1's free-running square wave and leave it running."""
    handle = ad3.open_device()
    ad3.square_wave(handle, 0, 0.0, VAPWR, STIMULUS_HZ, symmetry=50.0)
    ad3.dwf.FDwfAnalogOutConfigure(handle, ad3.c_int(0), ad3.c_int(1))
    time.sleep(0.3)
    return handle


def stop_ad3_stimulus(handle) -> None:
    ad3.dwf.FDwfAnalogOutConfigure(handle, ad3.c_int(0), ad3.c_int(0))
    ad3.close(handle)


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


def measure(resource: str, out_channel: int, in_channel: int | None,
           duration: float, interval: float, timebase: float | None) -> dict:
    rm = pyvisa.ResourceManager()
    scope = rm.open_resource(resource)
    scope.timeout = 5000
    print(f"Connected: {scope.query('*IDN?').strip()}")

    if timebase is not None:
        scope.write(f":TIMebase:SCALe {timebase:.3e}")
        scope.write(":RUN")

    scope.write(f":TRIGger:EDGE:SOURce CHANnel{out_channel}")
    scope.write(f":MEASure:RISetime CHANnel{out_channel}")
    if in_channel:
        scope.write(f":MEASure:FALLtime CHANnel{in_channel}")
        scope.write(f":MEASure:DELay CHANnel{in_channel},CHANnel{out_channel}")
    time.sleep(1.0)   # let the measurement slots settle before the first read

    rise, fall, delay = [], [], []
    end_time = time.monotonic() + duration
    while time.monotonic() < end_time:
        r = _read(scope, f":MEASure:RISetime? CHANnel{out_channel}")
        if r is not None:
            rise.append(r)
        if in_channel:
            f = _read(scope, f":MEASure:FALLtime? CHANnel{in_channel}")
            if f is not None:
                fall.append(f)
            d = _read(scope, f":MEASure:DELay? CHANnel{in_channel},CHANnel{out_channel}",
                     require_positive=False)
            if d is not None:
                delay.append(d)
        time.sleep(interval)

    scope.close()
    rm.close()
    return {"rise": rise, "fall": fall, "delay": delay}


def report(results: dict) -> None:
    rise = results["rise"]
    if not rise:
        print("No valid rise-time samples collected -- check the trigger is finding")
        print("the edge on the output channel and that the probe is actually on ua2.")
        return

    mean_rise = statistics.mean(rise)
    sd_rise = statistics.pstdev(rise) if len(rise) > 1 else 0.0
    print(f"\n  ua2, 10%-90% rise   {mean_rise * 1e9:6.2f} ns   "
          f"(sd {sd_rise * 1e9:.2f} ns over {len(rise)} samples)")

    fall = results["fall"]
    if fall:
        mean_fall = statistics.mean(fall)
        sd_fall = statistics.pstdev(fall) if len(fall) > 1 else 0.0
        print(f"  ua1, 10%-90% fall   {mean_fall * 1e9:6.2f} ns   "
              f"(sd {sd_fall * 1e9:.2f} ns over {len(fall)} samples, W1's own edge)")

    delay = results["delay"]
    if delay:
        mean_delay = statistics.mean(delay)
        sd_delay = statistics.pstdev(delay) if len(delay) > 1 else 0.0
        print(f"  ua1->ua2 delay, mid-rail to mid-rail   {mean_delay * 1e9:6.2f} ns   "
              f"(sd {sd_delay * 1e9:.2f} ns over {len(delay)} samples)")
        print("  This is the best-conditioned number here -- a delay common to both\n"
              "  channels cancels out of their difference, the way it did for\n"
              "  examples/srlatch's treset (24.46 ns measured vs 19.89 ns simulated,\n"
              "  a 1.23x agreement far better than this rise time's own history).")

    print("\n  Against examples/inverter/README.md's other numbers (all 10%-90%):")
    print("    as drawn, ideal edge, 10pF probe             8.16 ns")
    print("    as routed, ideal edge, 10pF probe           24.64 ns")
    print("    as routed, real edge (~26ns), 10pF probe    27.51 ns")
    print("    as routed, real edge (~26ns), 24pF probe    42.79 ns  (a real 10x probe's")
    print("                                                          lead/clip usually")
    print("                                                          land between these)")
    print("    measured via the AD3's own scope channel    95.41 ns  (wrong -- its own")
    print("                                                          9 MHz bandwidth, not")
    print("                                                          the inverter's)")
    print(f"    measured here (Keysight)                    {mean_rise * 1e9:.2f} ns")


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
    ap.add_argument("--out-channel", type=int, default=1,
                    help="Keysight channel wired to ua2 / the output (default: 1)")
    ap.add_argument("--in-channel", type=int, default=2,
                    help="Keysight channel wired to ua1 / the input, or 0 to skip it (default: 2)")
    ap.add_argument("--port", default=None, help="demoboard serial port")
    ap.add_argument("--no-program", action="store_true")
    ap.add_argument("--duration", type=float, default=10.0, help="seconds (default: 10)")
    ap.add_argument("--interval", type=float, default=0.2, help="seconds between reads (default: 0.2)")
    ap.add_argument("--timebase", type=float, default=20e-9,
                    help="seconds/div to set before measuring, or 0 to leave the scope's "
                         "current setting alone (default: 20e-9)")
    args = ap.parse_args()

    if args.list:
        list_devices()
        return
    if not args.resource:
        ap.error("resource is required unless --list is specified")

    in_channel = args.in_channel or None

    if not args.no_program:
        program_chip(args.port)
    print(wiring_table(args.out_channel, in_channel))
    input("  Press Enter once that is wired... ")

    print("== starting the AD3's W1 as ua1's stimulus")
    handle = start_ad3_stimulus()
    try:
        results = measure(args.resource, args.out_channel, in_channel,
                          args.duration, args.interval,
                          None if args.timebase == 0 else args.timebase)
    finally:
        stop_ad3_stimulus(handle)

    report(results)


if __name__ == "__main__":
    main()
