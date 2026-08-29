#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Confirm the chip's bias pin before measuring anything that depends on it.

Three of the six examples -- diffamp, currentsource, otabuf -- mirror
`ibias`. The RP2350-controlled bias circuit that would supply it arrived on
later ETR demoboards, and `mosbius program` drives it where it exists; on
an older board there is none, and the bias current has to be made the crude
way instead: the Analog Discovery's V+ rail through a series resistor into
the bias pin. That introduces two things that can be silently wrong before
any circuit is involved -- whether the pad letter is right, and whether the
current is what you think -- so this script settles both on their own.

Run it from the repo root, on the host (it needs USB for the demoboard):

    python3 tools/measure_ibias_clamp_ad3.py --resistor 20000

**What it is actually testing.** `ua[0]` feeds the gate and drain of the
diode-connected NMOS that references every mirror and tail on the chip
(SPEC.md Sec 3.4b). A diode-connected FET sets its own voltage: push 18x
more current through it and its gate rises by a couple of hundred
millivolts, not by volts. So sweeping the rail and watching the pad
separates the three cases that otherwise look alike at a multimeter:

    pad follows the rail 1:1     nothing is connected -- wrong pad letter,
                                 project not selected, or a broken lead
    pad sits at ~0 V             the pad is grounded -- eight of the ETR
                                 header's letters are tied straight to GND
    pad clamps near 0.9 V        the reference is there, and this is the
                                 only outcome that means the bias works

It loads an all-zero bitstream first. That is not a circuit: it opens
every switch in the matrix, so nothing is wired to a live device and what
remains is the bias reference, which is hard-wired to the pin rather than
reached through the matrix. The programming step is still needed, because
the chip's analog pins are muxed and it is `tt.shuttle.get(...).enable()`
that selects this project's slot -- without it the pad reaches no chip at
all, which is exactly the first failure case above.

**The resistor is the safety device.** A pad driven to 4.5 V is above
VAPWR and would conduct through its ESD diode; through 20 kOhm that is
under 200 uA, which the diode takes without complaint. Do not replace it
with a wire to find out whether the rail is reaching the pin.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ad3  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mosbius.pads import format_analog_header, pad_map  # noqa: E402

PROJECT = "tt_um_tnt_mosbius"
SHUTTLE = "ttsky25a"
ALL_SWITCHES_OPEN = "0" * 48

# The sweep window. V+ is settable over 0.5..5.0 V on an AD3 (read off the
# device 2026-08-29), and the scope window is centred to hold 0..4.65 V
# rather than ad3.CHIP_OFFSET's 0..3.3 V chip range, since the rail side of
# the resistor goes above VAPWR by design.
RAIL_MIN, RAIL_MAX, RAIL_STEP = 0.5, 4.5, 0.25
SCOPE_RANGE, SCOPE_OFFSET = 5.0, 2.25
NOMINAL_IBIAS = 100e-6


def wiring_table(pad: str, resistor: float) -> str:
    rows = [
        ("V+ (red)", "one end of R", f"the rail, through your {resistor / 1000:g}k resistor"),
        ("2+ (blue)", "that same end", "the rail measured at the resistor, not"),
        ("", "", "at the instrument -- lead drops are real"),
        ("1+ (orange)", f"pad {pad}", "the other end of R, and the bias pin"),
        ("1-, 2-, GND", "any gnd", "scope reference. The inputs are differential,"),
        ("", "", "so an ungrounded '-' makes every reading wrong"),
    ]
    out = [
        "\n  Wire the Analog Discovery to the demoboard like this:\n",
        "    AD3 lead      where              signal",
        "    -----------   ----------------   -----------------------------------",
    ]
    for lead, where, what in rows:
        out.append(f"    {lead:<13s} {where:<18s} {what}")
    out.append("")
    out.append("  The resistor is in series between V+ and the pad. Nothing else")
    out.append("  connects to the pad -- no wavegen, no second supply.")
    out.append("")
    out.append(format_analog_header({"ibias": pad}))
    return "\n".join(out) + "\n"


def program_chip(port: str | None) -> None:
    """Select this project's analog mux slot, with every switch open.

    `--ibias 0` matters: on a board that *does* have the bias circuit it
    feeds the same node we are about to measure, and any current from it
    would land in our arithmetic as if it had come through the resistor. On
    a board without one, `mosbius program` now says so in as many words
    rather than reporting a clean upload and a bias current it never
    delivered.
    """
    cmd = [sys.executable, "-m", "mosbius.cli", "program", ALL_SWITCHES_OPEN,
           "--project", PROJECT, "--ibias", "0"]
    if port:
        cmd += ["--port", port]
    print("== selecting the project, with every switch open")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    print("  " + (result.stdout.strip() or result.stderr.strip()).replace("\n", "\n  "))
    if result.returncode != 0:
        raise SystemExit("programming failed -- the pad would reach no chip, nothing measured")


def read_point(handle, tag):
    """(rail at the resistor, pad voltage), or None if the capture was flat."""
    try:
        samples = ad3.acquire(handle, nsamples=4000, tag=tag)
    except RuntimeError as exc:
        print(f"  {tag}{exc}".replace("\n", "\n  "))
        return None
    return ad3.mean(samples, 1), ad3.mean(samples, 0)


def sweep(handle, resistor: float) -> list[dict]:
    ad3.scope_setup(handle, rate=1e5, nsamples=4000,
                    rng=SCOPE_RANGE, offset=SCOPE_OFFSET)
    points = []
    level = RAIL_MIN
    while level <= RAIL_MAX + 1e-9:
        ad3.supply(handle, level, "V+", current_limit=0.05, settle=0.15)
        time.sleep(0.05)
        reading = read_point(handle, f"at V+ = {level:.3f} V: ")
        if reading is not None:
            rail, pad = reading
            points.append({
                "set": level, "rail": rail, "pad": pad,
                "amps": (rail - pad) / resistor,
            })
        level += RAIL_STEP
    ad3.supplies_off(handle)
    return points


def report(points: list[dict], resistor: float, pad: str) -> None:
    print(f"\n  V+ set   rail at R    pad {pad}      current")
    print("  ------   ---------    ---------   ----------")
    for p in points:
        print(f"  {p['set']:5.2f} V   {p['rail']:+7.4f} V   {p['pad']:+7.4f} V   "
              f"{p['amps'] * 1e6:+8.2f} uA")

    if len(points) < 3:
        print("\n  Too few points survived to say anything. See the errors above.")
        return

    # The slope is taken over the upper half of the sweep, not end to end.
    # Below the reference's threshold nothing conducts and the pad sits near
    # 0 V, so including those points averages a dead region in with the live
    # one and pushes a real clamp towards the "inconclusive" band.
    first, last = points[0], points[-1]
    live = points[len(points) // 2:]
    slope = ((live[-1]["pad"] - live[0]["pad"])
             / (live[-1]["rail"] - live[0]["rail"]))
    print(f"\n  over the upper half of the sweep, pad moved "
          f"{(live[-1]['pad'] - live[0]['pad']) * 1000:+.1f} mV while the rail moved "
          f"{(live[-1]['rail'] - live[0]['rail']) * 1000:+.0f} mV")
    print(f"  slope d(pad)/d(rail) = {slope:.3f}")

    if first["pad"] > first["rail"] + 0.05:
        print("\n  SOMETHING ELSE IS DRIVING THIS PIN. At the lowest rail setting the\n"
              "  pad sits ABOVE the rail, so current is flowing backwards into the\n"
              "  resistor. The likeliest source is the demoboard's own programmable\n"
              "  current source still being on: this script asks for --ibias 0, so\n"
              "  check what `mosbius program` reported about it above.")
    elif slope > 0.7:
        print("\n  OPEN CIRCUIT -- the pad is following the rail, so no current is\n"
              "  flowing and there is no diode on the other end. In order of\n"
              f"  likelihood: the project's analog mux slot is not selected; pad {pad}\n"
              "  is not this chip's ibias after all; or a lead is off. Note that\n"
              f"  pad {pad} is NOT one of the three confirmed on silicon -- ua1->C,\n"
              "  ua2->J and ua3->D are; this one is composed from the shuttle index\n"
              "  and the carrier wiring and has not been checked at a bench before.")
    elif max(p["pad"] for p in points) < 0.15:
        print("\n  GROUNDED -- the pad is held at 0 V however hard the rail pushes.\n"
              "  Eight of the ETR header's lettered pads (A, B, E, H, L, M, N, P)\n"
              "  are tied straight to ground, so a probe one row or one column off\n"
              "  reads exactly this. Check the header picture above.")
    elif slope < 0.25:
        print("\n  CLAMPED -- this is the bias reference. The pad holds its own\n"
              "  voltage while the rail changes by volts, which is what a\n"
              "  diode-connected FET does and what neither an open nor a short can\n"
              "  fake.")
        target = _rail_for(points, NOMINAL_IBIAS)
        if target is not None:
            print(f"\n  For the nominal 100 uA, set V+ to about {target:.3f} V.")
        else:
            lo = min(p["amps"] for p in points) * 1e6
            hi = max(p["amps"] for p in points) * 1e6
            print(f"\n  100 uA is outside what this sweep reached ({lo:.1f}..{hi:.1f} uA).\n"
                  f"  With {resistor / 1000:g}k the rail cannot get there; use a smaller\n"
                  "  resistor, and re-run this to find the setting.")
    else:
        print("\n  INCONCLUSIVE -- the pad neither follows the rail nor holds still.\n"
              "  Read the table above rather than trusting a verdict: a partly\n"
              "  connected lead and a clamp in series with resistance both land here.")

    print("\n  The current column is arithmetic on two scope channels across a\n"
          f"  resistor you supplied, so it is only as good as that resistor's\n"
          f"  tolerance ({resistor / 1000:g}k assumed exactly). It does not depend on the\n"
          "  supply's own readback, which is why both ends of R are probed.")


def _rail_for(points: list[dict], amps: float) -> float | None:
    """Interpolate the rail setting that gives `amps`, or None if out of range."""
    for a, b in zip(points, points[1:]):
        if min(a["amps"], b["amps"]) <= amps <= max(a["amps"], b["amps"]):
            span = b["amps"] - a["amps"]
            if abs(span) < 1e-12:
                return a["set"]
            return a["set"] + (amps - a["amps"]) / span * (b["set"] - a["set"])
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--resistor", type=float, default=20000.0,
                        help="series resistance in ohms (default: 20k)")
    parser.add_argument("--pad", default=None,
                        help="override the bias pad letter (default: looked up)")
    parser.add_argument("--port", default=None, help="demoboard serial port")
    parser.add_argument("--no-program", action="store_true",
                        help="skip programming; the project must already be selected")
    args = parser.parse_args()

    pad = args.pad or pad_map(SHUTTLE, PROJECT)["ibias"]
    if not args.no_program:
        program_chip(args.port)
    print(wiring_table(pad, args.resistor))
    input("  Press Enter once that is wired and the resistor is in place... ")

    with ad3.device() as handle:
        points = sweep(handle, args.resistor)

    out = Path("build/ibias_clamp.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"resistor": args.resistor, "pad": pad, "points": points}))
    print(f"\n== {len(points)} points written to {out}")
    report(points, args.resistor, pad)


if __name__ == "__main__":
    main()
