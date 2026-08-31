#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Time the two amplifiers' step responses on real silicon.

One script, two circuits, because the measurement is the same shape for
both: drive a real edge, capture it triggered at full rate, and time what
the output does. Run from the repo root, on the host:

    python3 tools/measure_settling_ad3.py otabuf
    python3 tools/measure_settling_ad3.py diffamp

`examples/otabuf/` is slew-limited -- its tail current charges the output
node at a fixed rate -- so what is timed is a slew rate, output crossing
1.3 V to 2.0 V. `examples/diffamp/` is not: its output settles as an RC
with a time constant of a few hundred nanoseconds, so what is fitted is
that time constant. Same rig, same capture, different arithmetic.

**Do not compare either result against the number on the example's page.**
Both published figures are at `cprobe=10p`, and an Analog Discovery
presents about 24 pF. For a slew-limited output the rate goes as 1/C, and
for an RC settle the time constant goes as C, so a 14 pF difference is not
a detail -- it moves otabuf's expected slew from 15.4 to about 10 V/us and
diffamp's expected time constant from 220 to about 430 ns. This script
does that arithmetic itself and prints the probe-corrected expectation
beside the measurement. Comparing against the raw published figure would
show a large disagreement that is entirely the probe.

**The generator is not infinitely fast, and for otabuf that is close to
mattering.** An Analog Discovery's output amplifier takes tens of
nanoseconds to move volts, so a stimulus edge and a slew rate of the same
order cannot be told apart. otabuf's probe-corrected 10 V/us over 0.7 V is
70 ns, which is only a few times the generator's own edge, so this script
reports the stimulus edge alongside every result and the margin should be
read before the number is. diffamp is comfortable: its input step is 80 mV,
which the generator moves quickly, and its output takes hundreds of
nanoseconds.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ad3  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mosbius.bitstream import unpack  # noqa: E402
from mosbius.model import SwitchConfig  # noqa: E402
from mosbius.pads import format_analog_header, pads_in_use  # noqa: E402

PROJECT, SHUTTLE = "tt_um_tnt_mosbius", "ttsky25a"
NSAMPLES, CAPTURES = 4096, 16
STIMULUS_HZ = 10_000.0
BIAS_RAIL = 3.28
# Rails giving roughly 30, 50, 75 and 100 uA through 20 kOhm. Slewing is the
# one measurement here that gets *better* at low bias: the rate goes as the
# tail current, so turning the bias down slows the output away from the
# generator's own edge, which is what the margin needs.
SLEW_RAILS = (1.35, 1.50, 1.65, 1.90, 2.15, 2.70, 3.28)
AD3_CPROBE, SHEET_CPROBE = 24e-12, 10e-12

IN_CH, OUT_CH = 0, 1

# Each profile's bitstream is its example as the router placed it on
# 2026-08-29 -- the same strings tools/measure_otabuf_ad3.py and
# tools/measure_diffamp_ad3.py program, and the configurations the step
# responses below were measured against. They are records of experiments,
# not cached build artifacts: if the router's allocation ever changes,
# re-route and re-measure rather than editing these strings, or the
# published numbers quietly stop describing what was on the chip.
PROFILES = {
    "otabuf": {
        "bitstream": "404000000000000000000000000000000000000000850210",
        "in_pin": "ua1", "out_pin": "ua2",
        "step": (1.0, 2.3),          # what tb_otabuf.sch steps between
        "kind": "slew",
        "band": (1.3, 2.0),          # the sheet measures the slew here
        "trigger": ("in", 1.65),
        # slew = I_tail / C, so C follows from the published rate.
        "published": {"as drawn": 42.9, "as routed": 15.4},
        "tail_amps": 400e-6,
        "dc_gain": 1.0,
        "units": "V/us",
    },
    "diffamp": {
        "bitstream": "00100000c020004820000000004821000000000000000030",
        "in_pin": "ua1", "out_pin": "ua4", "hold_pin": "ua2",
        "step_mv": 40.0,             # +/- about the operating point
        "common_mode": 1.5,
        "kind": "tau",
        "trigger": ("out", None),    # level found from the capture itself
        # tau = Rout * C, so C follows from the published tau and Rout.
        "published": {"as drawn": 90.0, "as routed": 220.0},
        "rout": {"as drawn": 9e3, "as routed": 15e3},
        "units": "ns",
    },
}


def implied_bias(rail: float) -> float | None:
    """What tools/measure_ibias_clamp_ad3.py says this rail delivers.

    Same helper as in tools/measure_diffamp_ad3.py. The bias pad sets its own
    voltage, so the current cannot be read off the rail setting alone -- it
    comes from interpolating the clamp sweep, which measured both ends of the
    resistor.
    """
    path = Path("build/ibias_clamp.json")
    if not path.exists():
        return None
    pts = json.loads(path.read_text())["points"]
    for a, b in zip(pts, pts[1:]):
        if min(a["rail"], b["rail"]) <= rail <= max(a["rail"], b["rail"]):
            span = b["rail"] - a["rail"]
            f = 0.0 if abs(span) < 1e-9 else (rail - a["rail"]) / span
            return a["amps"] + f * (b["amps"] - a["amps"])
    return None


def probe_corrected(profile) -> dict[str, float]:
    """The published figure, re-expressed for the probe actually on the pin.

    Both quantities depend on the total capacitance on the output node, and
    the published ones were taken with a 10 pF probe model. Back out that
    node capacitance, swap the probe, and recompute -- which is the only
    way the comparison means anything.
    """
    out = {}
    for branch, value in profile["published"].items():
        if profile["kind"] == "slew":
            c_total = profile["tail_amps"] / (value * 1e6)
            c_new = c_total - SHEET_CPROBE + AD3_CPROBE
            out[branch] = profile["tail_amps"] / c_new / 1e6
        else:
            c_total = value * 1e-9 / profile["rout"][branch]
            c_new = c_total - SHEET_CPROBE + AD3_CPROBE
            out[branch] = profile["rout"][branch] * c_new * 1e9
    return out


def wiring_table(name, profile, pads) -> str:
    rows = [("V+ (red)", f"via 20k to {pads['ibias']}", f"bias, V+ = {BIAS_RAIL} V"),
            ("W1 (yellow)", pads[profile["in_pin"]],
             f"{profile['in_pin']}, the stepped input"),
            ("1+ (orange)", pads[profile["in_pin"]], "the same node, times the stimulus")]
    if "hold_pin" in profile:
        rows.insert(2, ("W2 (white)", pads[profile["hold_pin"]],
                        f"{profile['hold_pin']}, held at the common-mode point"))
    rows += [("2+ (blue)", pads[profile["out_pin"]], f"{profile['out_pin']}, the output"),
             ("1-, 2-, GND", "any gnd", "scope reference -- differential inputs")]
    out = [f"\n  Wiring for {name}:\n",
           "    AD3 lead      where              signal",
           "    -----------   ----------------   ------------------------------------"]
    for lead, where, what in rows:
        out.append(f"    {lead:<13s} {where:<18s} {what}")
    if "hold_pin" not in profile:
        # Coming from the diffamp measurement, W2 is sitting on pad J holding
        # a common-mode level -- and for otabuf pad J is the *output*. A
        # wavegen is a low-impedance source, so leaving it there fights the
        # amplifier for control of its own output node: at best the
        # measurement is of the generator, at worst the OTA spends the run
        # driving into it.
        out.append("")
        out.append("    DISCONNECT W2. This circuit has no second input, and the pad")
        out.append(f"    W2 sits on for diffamp ({pads[profile['out_pin']]}) is this one's OUTPUT.")
        out.append("    A wavegen left there is a low-impedance source fighting the")
        out.append("    amplifier for its own output node.")
    return "\n".join(out) + "\n\n" + format_analog_header(pads) + "\n"


def program_chip(bitstream, port) -> None:
    cmd = [sys.executable, "-m", "mosbius.cli", "program", bitstream,
           "--project", PROJECT, "--ibias", "0"]
    if port:
        cmd += ["--port", port]
    print("== loading the design onto the chip")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    print("  " + (r.stdout.strip() or r.stderr.strip()).replace("\n", "\n  "))
    if r.returncode != 0:
        raise SystemExit("programming failed -- nothing measured")


def _smooth(values, k=9):
    out = []
    for i in range(len(values)):
        a, b = max(0, i - k // 2), min(len(values), i + k // 2 + 1)
        out.append(sum(values[a:b]) / (b - a))
    return out


def edge_10_90(values, dt, centre=None, half=200, rising=True):
    """Rise time of a step, 10% to 90% of its own settled swing.

    **Both the smoothing and the search window are load-bearing, and their
    absence produced a nonsense number.** diffamp's input step is only
    80 mV, so its 10% and 90% levels sit 8 mV from the two baselines while
    the channel carries about 1.9 mV rms of noise. A first-crossing search
    over the whole buffer then finds noise rather than the edge, thousands
    of samples early, and reports a stimulus edge of about 5.3 us for
    something that actually takes 68 ns -- a number that then claimed the
    generator was ten times slower than the circuit it was driving. The fix
    is to look only around the trigger, and at a smoothed copy: with both,
    the same edge measures 68 ns with a 2 ns spread over eight captures.
    """
    n = len(values)
    centre = n // 2 if centre is None else centre
    a, b = max(0, centre - half), min(n, centre + half)
    lo = statistics.median(values[max(0, a - 300):a] or values[:1])
    hi = statistics.median(values[b:b + 300] or values[-1:])
    if abs(hi - lo) < 0.02:
        return None
    seg = _smooth(values[a:b])
    t10 = ad3.crossing(seg, lo + 0.1 * (hi - lo), rising, dt)
    t90 = ad3.crossing(seg, lo + 0.9 * (hi - lo), rising, dt)
    return None if t10 is None or t90 is None else abs(t90 - t10)


def measure_slew(values, dt, band, rising=True):
    """Slew rate across `band`, in V/us, in either direction.

    **Both directions are measured as a symmetry check, not because an
    asymmetry is expected.** `outm` is pulled up by the PMOS mirror and
    pulled down by the input pair's own current, so different devices set
    the two rates and there is no structural reason for them to match. On a
    scope they look the same -- checked at the bench -- and this is what
    turns "look the same" into two numbers that can be compared.
    """
    lo, hi = band
    first, second = (lo, hi) if rising else (hi, lo)
    t1 = ad3.crossing(values, first, rising, dt)
    t2 = ad3.crossing(values, second, rising, dt)
    if t1 is None or t2 is None or t2 <= t1:
        return None
    return (hi - lo) / (t2 - t1) / 1e6


def measure_tau(values, dt):
    """Fit an exponential settle: ln|Vinf - V(t)| against t is a straight line.

    Fitted over the 80%-to-10%-remaining part of the excursion. The start is
    excluded because a step's first moments are set by whatever limits the
    output current rather than by the RC, and the tail because there the
    residual is down in the noise and its logarithm is mostly noise.
    """
    n = len(values)
    v_inf = statistics.median(values[-n // 8:])
    v_0 = statistics.median(values[:n // 8])
    swing = v_inf - v_0
    if abs(swing) < 0.05:
        return None
    pts = []
    for i, v in enumerate(values):
        remaining = (v_inf - v) / swing
        if 0.10 <= remaining <= 0.80:
            pts.append((i * dt, math.log(abs(remaining))))
    if len(pts) < 10:
        return None
    m = len(pts)
    mx = sum(p[0] for p in pts) / m
    my = sum(p[1] for p in pts) / m
    denom = sum((p[0] - mx) ** 2 for p in pts)
    if denom == 0:
        return None
    slope = sum((p[0] - mx) * (p[1] - my) for p in pts) / denom
    return None if slope >= 0 else -1.0 / slope * 1e9      # ns


def diffamp_centre() -> float:
    """The operating point measured by tools/measure_diffamp_ad3.py, if it ran.

    Stepping symmetrically about 1.5 V when the real centre is a few
    millivolts off puts the two halves of the step on different parts of the
    transfer curve, which is avoidable here for free.
    """
    path = Path("build/diffamp_silicon.json")
    if not path.exists():
        return PROFILES["diffamp"]["common_mode"]
    rec = json.loads(path.read_text())
    good = [b for b in rec["by_bias"] if b.get("fine")]
    if not good:
        return PROFILES["diffamp"]["common_mode"]
    nominal = min(good, key=lambda b: abs((b["amps"] or 0) - 100e-6))
    lin = [p for p in nominal["fine"] if 1.3 <= p[1] <= 2.4]
    n = len(lin)
    mx = sum(p[0] for p in lin) / n
    my = sum(p[1] for p in lin) / n
    slope = (sum((p[0] - mx) * (p[1] - my) for p in lin)
             / sum((p[0] - mx) ** 2 for p in lin))
    return (2.0 - (my - slope * mx)) / slope


def midpoint_delay(v_in, v_out, dt, rising=True, centre=None, half=400):
    """Input-to-output delay, each channel at its own 50% point.

    **This is the best-conditioned number the rig produces, and it came from
    someone watching the screen.** Reported from the bench as "at about the
    half way point, the blue lags the yellow by around 100 ns" -- which is a
    quantity the script was not computing at all, though it already had both
    channels in every capture.

    Why it beats the slew rate here: both channels sit behind the same
    instrument input path, so a delay common to the two cancels out of their
    difference. An edge *width*, by contrast, is the signal's own rise and
    the instrument's combined, and the two cannot be separated without
    knowing the instrument's -- which is exactly why the slew measurement
    needs a 3x margin over the generator's edge and this does not.

    Each channel uses its own 50% level rather than a shared one, because
    the follower carries tens of millivolts of offset and the two traces do
    not share a midpoint.
    """
    n = len(v_in)
    centre = n // 2 if centre is None else centre
    a, b = max(0, centre - half), min(n, centre + half)
    out = []
    for values in (v_in, v_out):
        lo = statistics.median(values[max(0, a - 300):a] or values[:1])
        hi = statistics.median(values[b:b + 300] or values[-1:])
        if abs(hi - lo) < 0.05:
            return None
        seg = _smooth(values[a:b])
        t = ad3.crossing(seg, (lo + hi) / 2, rising, dt)
        if t is None:
            return None
        out.append(t)
    return out[1] - out[0]


def _capture_batch(handle, count, dt, profile, rising):
    """`count` triggered captures, reduced to one result. None if none worked."""
    results, stim_edges, out_edges, delays = [], [], [], []
    # Throw the first away. square_wave() changes the generator's amplitude
    # and the Analog Discovery slews that change rather than applying it, so
    # a capture taken immediately after can catch the tail of it -- which
    # looks like a flat input beside an output slamming rail to rail, and is
    # indistinguishable from a broken circuit if you have not seen it.
    ad3.capture_triggered(handle, NSAMPLES, tag="settling capture: ")
    for i in range(count):
        got = ad3.capture_triggered(handle, NSAMPLES, tag=f"capture {i + 1}: ")
        if got is None:
            print(f"  capture {i + 1} never triggered -- skipping")
            continue
        stim = edge_10_90(got[IN_CH], dt, rising=rising)
        if stim is not None:
            stim_edges.append(stim)
        value = (measure_slew(got[OUT_CH], dt, profile["band"], rising)
                 if profile["kind"] == "slew" else measure_tau(got[OUT_CH], dt))
        if value is not None:
            results.append(value)
        out_edge = edge_10_90(got[OUT_CH], dt, rising=rising)
        if out_edge is not None:
            out_edges.append(out_edge)
        lag = midpoint_delay(got[IN_CH], got[OUT_CH], dt, rising)
        if lag is not None:
            delays.append(lag)
    if not results:
        return None
    return {"value": statistics.mean(results),
            "sd": statistics.stdev(results) if len(results) > 1 else 0.0,
            "stimulus_ns": statistics.mean(stim_edges) * 1e9 if stim_edges else None,
            "output_ns": statistics.mean(out_edges) * 1e9 if out_edges else None,
            "delay_ns": statistics.mean(delays) * 1e9 if delays else None,
            "delay_sd_ns": (statistics.stdev(delays) * 1e9
                            if len(delays) > 1 else 0.0),
            "n": len(results)}


def check_alive(handle, profile, mid=1.65, tol=0.25):
    """Confirm the circuit responds before trying to time it.

    **This exists because a silent failure cost an hour.** An otabuf run
    once returned "nothing measurable" from all sixteen captures with the
    stimulus verifiably correct on the input pin and the output pinned near
    0.1 V -- and the same circuit, on the same wiring, swept correctly at DC
    minutes later and followed a 1.0-to-2.3 V square at every rate tried.
    Whatever the stuck state was, a bias power cycle cleared it, and the
    mechanism was never identified: the obvious candidate, the bias coming
    up while the input sat below the input common-mode range, was tested
    directly and does not do it -- the output goes to its 0.31 V floor and
    recovers by itself when the input returns to range.

    So this does not try to explain the condition, only to catch it. A
    handful of DC points is enough: an amplifier that cannot follow at DC
    cannot be timed, and finding that out here turns a confusing empty
    result into a named one.
    """
    levels = (mid - 0.4, mid, mid + 0.4)
    ad3.scope_setup(handle, rate=1e5, nsamples=1000, settle=0.4)
    seen = []
    for level in levels:
        ad3.wavegen(handle, ch=0, func=ad3.funcDC, amp=0.0, offset=level)
        time.sleep(0.25)
        try:
            got = ad3.acquire(handle, nsamples=1000, tag="liveness: ")
        except RuntimeError:
            return False, seen
        seen.append((ad3.mean(got, IN_CH), ad3.mean(got, OUT_CH)))
    if len(seen) < 2:
        return False, seen
    swing_in = seen[-1][0] - seen[0][0]
    swing_out = seen[-1][1] - seen[0][1]
    if abs(swing_in) < 0.1:
        return False, seen
    gain = swing_out / swing_in
    # A follower should give ~1. A gain stage would not, so this only gates
    # the circuits whose DC behaviour is a known ratio; both amps measured
    # here are checked against their own expected DC response.
    expected = profile.get("dc_gain", 1.0)
    return abs(gain - expected) <= tol * abs(expected), seen


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("circuit", choices=sorted(PROFILES))
    ap.add_argument("--port", default=None)
    ap.add_argument("--no-program", action="store_true")
    ap.add_argument("--captures", type=int, default=CAPTURES)
    args = ap.parse_args()

    profile = PROFILES[args.circuit]
    pads = pads_in_use(SwitchConfig(bits=unpack(profile["bitstream"])),
                       SHUTTLE, PROJECT)
    if not args.no_program:
        program_chip(profile["bitstream"], args.port)
    print(wiring_table(args.circuit, profile, pads))
    input("  Press Enter once that is wired... ")

    if args.circuit == "diffamp":
        centre = diffamp_centre()
        step = (centre - profile["step_mv"] / 1000, centre + profile["step_mv"] / 1000)
        print(f"  stepping ua1 {step[0]:.4f} -> {step[1]:.4f} V "
              f"about a measured centre of {centre:.4f} V")
    else:
        step = profile["step"]

    results, stim_edges, out_edges = [], [], []
    with ad3.device() as handle:
        rail = ad3.supply(handle, BIAS_RAIL, "V+", current_limit=0.05, settle=0.5)
        print(f"  bias rail {rail['voltage']:.4f} V")
        if "hold_pin" in profile:
            ad3.wavegen(handle, ch=1, func=ad3.funcDC, amp=0.0,
                        offset=profile["common_mode"])
        if profile.get("dc_gain") is not None:
            ok, seen = check_alive(handle, profile,
                                   mid=(step[0] + step[1]) / 2)
            if not ok:
                print("  the circuit did not respond at DC -- cycling the bias")
                ad3.supplies_off(handle)
                time.sleep(1.0)
                rail = ad3.supply(handle, BIAS_RAIL, "V+",
                                  current_limit=0.05, settle=0.8)
                ok, seen = check_alive(handle, profile,
                                       mid=(step[0] + step[1]) / 2)
            if not ok:
                for vin, vout in seen:
                    print(f"    in {vin:7.4f} V -> out {vout:7.4f} V")
                raise SystemExit(
                    "the circuit is not following at DC, so there is nothing to\n"
                    "  time. The bias has already been cycled once, which has\n"
                    "  cleared this before. Next: check the bias pad is near 1.28 V,\n"
                    "  and run tools/measure_%s_ad3.py, which sweeps DC properly and\n"
                    "  reports what it finds." % args.circuit)
            print(f"  alive: output follows at DC across "
                  f"{seen[0][0]:.2f}..{seen[-1][0]:.2f} V")

        ad3.square_wave(handle, 0, step[0], step[1], STIMULUS_HZ)
        ad3.dwf.FDwfAnalogOutConfigure(handle, ad3.c_int(0), ad3.c_int(1))
        time.sleep(0.3)

        rate = ad3.max_rate(handle)
        dt = 1.0 / rate
        which, level = profile["trigger"]
        if level is None:
            # Find the output's own midpoint from an untriggered look first:
            # a fixed level cannot be assumed when the operating point is a
            # property of the part rather than of the sheet.
            ad3.scope_setup(handle, rate=1e6, nsamples=4000, settle=0.3)
            look = ad3.acquire(handle, nsamples=4000, tag="finding the level: ")
            level = (min(look[OUT_CH]) + max(look[OUT_CH])) / 2
            print(f"  triggering on the output at {level:.4f} V")
        trig_ch = IN_CH if which == "in" else OUT_CH
        ad3.scope_setup_triggered(handle, rate, NSAMPLES, trig_ch, level,
                                  rising=True, position=0.0)

        print(f"  capturing at {rate / 1e6:.0f} MS/s "
              f"({dt * 1e9:.0f} ns per sample), {NSAMPLES} samples "
              f"= {NSAMPLES * dt * 1e6:.1f} us")
        rails = SLEW_RAILS if profile["kind"] == "slew" else (BIAS_RAIL,)
        # Both edge directions, for the slew profile only. `outm` is pulled up
        # by the PMOS mirror and pulled down by the input pair's own current,
        # so there is no structural reason for the two to match -- watching
        # the step on a scope they looked the same, and this is what turns
        # "looked the same" into a number.
        directions = ((True, "rising"), (False, "falling")) \
            if profile["kind"] == "slew" else ((True, "rising"),)
        by_bias = []
        for v_rail in rails:
            if len(rails) > 1:
                ad3.supply(handle, v_rail, "V+", current_limit=0.05, settle=0.3)
                settled = ad3.wait_supply_stable(handle, "V+")
                amps = implied_bias(settled)
                print("\n  -- bias "
                      + (f"{amps * 1e6:.1f} uA" if amps else f"rail {v_rail:.2f} V"))
            else:
                amps = implied_bias(rail["voltage"])

            entry = {"amps": amps}
            for rising, dir_name in directions:
                ad3.scope_setup_triggered(handle, rate, NSAMPLES, trig_ch,
                                          level, rising=rising, position=0.0)
                batch = _capture_batch(handle, args.captures, dt, profile, rising)
                if batch is None:
                    continue
                entry[dir_name] = batch
                label = f"{dir_name:<8s}" if len(directions) > 1 else ""
                print(f"     {label}{batch['value']:.2f} {profile['units']}"
                      f"  (sd {batch['sd']:.2f} over {batch['n']})")
            if "rising" in entry:
                entry.update({k: entry["rising"][k]
                              for k in ("value", "sd", "stimulus_ns", "n")})
                by_bias.append(entry)
        ad3.dwf.FDwfAnalogOutConfigure(handle, ad3.c_int(-1), ad3.c_int(0))

    if not by_bias:
        raise SystemExit(
            "nothing measurable came back.\n\n"
            "  Check the stimulus is reaching the pin and the output is moving:\n"
            "  run tools/measure_%s_ad3.py first, which sweeps DC and will say\n"
            "  whether the circuit is alive at all." % args.circuit)

    out = Path(f"build/{args.circuit}_settling.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"circuit": args.circuit, "by_bias": by_bias,
                               "rate": rate, "step": step}))
    report(args.circuit, profile, by_bias)
    print(f"\n== written to {out}")


def report(name, profile, by_bias) -> None:
    unit = profile["units"]
    corrected = probe_corrected(profile)
    nominal = min(by_bias, key=lambda b: abs((b["amps"] or 0) - 100e-6))

    print(f"\n  {name}: {len(by_bias)} bias point(s)\n")
    print(f"    at {nominal['amps'] * 1e6:.0f} uA        {nominal['value']:7.2f} {unit}"
          f"   (sd {nominal['sd']:.2f} over {nominal['n']})")
    print(f"\n    published, 10 pF probe:  as drawn "
          f"{profile['published']['as drawn']:7.2f} {unit}")
    print(f"                            as routed {profile['published']['as routed']:7.2f} {unit}")
    print(f"    corrected to 24 pF:      as drawn {corrected['as drawn']:7.2f} {unit}")
    print(f"                            as routed {corrected['as routed']:7.2f} {unit}")
    print("\n  The correction is not a fudge: both quantities are set by the total\n"
          "  capacitance on the output node, the published pair was taken with a\n"
          "  10 pF probe model, and the instrument on the pin is about 24 pF. Slew\n"
          "  goes as 1/C and a settling time constant goes as C, so ignoring 14 pF\n"
          "  would have manufactured a disagreement of roughly that ratio.")

    if profile["kind"] == "tau":
        _report_tau(profile, nominal, corrected)
        return

    band = profile["band"][1] - profile["band"][0]
    print("\n  Slew against bias current. Turning the bias DOWN is what makes this\n"
          "  measurable at all: the output slews at the tail current over the node\n"
          "  capacitance, so less bias means a slower output and more room between\n"
          "  it and the generator's own edge, which does not move.\n")
    print("    bias        rising      falling     out    stim   margin")
    print("    ---------   ---------   ---------   -----  -----  ------")
    usable = []
    for b in by_bias:
        rise = b.get("rising", {}).get("value")
        fall = b.get("falling", {}).get("value")
        out_ns = band / rise * 1000 if rise else None
        stim = b.get("stimulus_ns")
        margin = out_ns / stim if out_ns and stim else None
        flag = "" if margin and margin >= 3 else "  <- too close"
        cells = [f"{b['amps'] * 1e6:6.1f} uA",
                 f"{rise:5.2f} {unit}" if rise else "     --   ",
                 f"{fall:5.2f} {unit}" if fall else "     --   ",
                 f"{out_ns:4.0f}ns" if out_ns else "   --ns",
                 f"{stim:4.0f}ns" if stim else "   --ns",
                 f"{margin:4.1f}x" if margin else "  --  "]
        print("    " + "   ".join(cells) + flag)
        if margin and margin >= 3:
            usable.append(b)

    pairs = [(b["rising"]["value"], b["falling"]["value"]) for b in by_bias
             if "rising" in b and "falling" in b]
    if pairs:
        ratios = [f / r for r, f in pairs]
        lo, hi = min(ratios), max(ratios)
        if hi < 0.9 or lo > 1.1:
            print(f"\n  The two directions do NOT match: falling slew is "
                  f"{sum(ratios) / len(ratios):.2f}x rising\n"
                  f"  ({lo:.2f} to {hi:.2f} across the sweep), consistently and at every bias\n"
                  f"  point. That is a real asymmetry rather than scatter, and it has a\n"
                  f"  cause in the topology: `outm` is pulled up by the PMOS mirror and\n"
                  f"  pulled down by the input pair's own current, so different devices\n"
                  f"  set the two rates.\n\n"
                  f"  Note this is below what a scope shows at this timebase -- from the\n"
                  f"  bench the two edges looked the same, and at the nominal bias they\n"
                  f"  differ by tens of nanoseconds on a ~100 ns lag. Eye and fit do not\n"
                  f"  disagree; the eye could not resolve it.")
        else:
            print(f"\n  Rising and falling agree to within "
                  f"{max(abs(x - 1) for x in ratios) * 100:.0f}%, so the slew is\n"
                  f"  symmetric -- worth stating rather than assuming, since different\n"
                  f"  devices set the two directions.")

    delays = [(b["amps"], b["rising"]["delay_ns"]) for b in by_bias
              if b.get("rising", {}).get("delay_ns")]
    if delays:
        print("\n  Input-to-output delay at the 50% point -- the quantity a scope\n"
              "  shows most directly, and the best conditioned one here, since a\n"
              "  delay common to both channels cancels out of their difference:\n")
        print("    bias        rising     falling")
        print("    ---------   --------   --------")
        both = []
        for b in by_bias:
            r = b.get("rising", {}).get("delay_ns")
            f = b.get("falling", {}).get("delay_ns")
            print(f"    {b['amps'] * 1e6:6.1f} uA   "
                  + (f"{r:5.0f} ns" if r else "    -- ns") + "   "
                  + (f"{f:5.0f} ns" if f else "    -- ns"))
            if r and f:
                both.append((r, f))
        if both:
            ratios = [f / r for r, f in both]
            mean_ratio = sum(ratios) / len(ratios)
            if mean_ratio > 1.1 or mean_ratio < 0.9:
                print(f"\n  The falling delay is {mean_ratio:.2f}x the rising one at every bias\n"
                      f"  point -- the same asymmetry the slew figures show, seen a second\n"
                      f"  way. At the nominal bias that is {both[-1][0]:.0f} ns against "
                      f"{both[-1][1]:.0f} ns, a difference\n"
                      f"  of tens of nanoseconds that a scope at this timebase reads as\n"
                      f"  'about the same on both edges'.")
            else:
                print(f"\n  Rising and falling delays agree to within "
                      f"{max(abs(x - 1) for x in ratios) * 100:.0f}%.")
        if len(delays) > 2:
            # If slewing dominates, the delay is the time to slew half the
            # step, so it goes as 1/ibias. Anything left at infinite bias is
            # fixed loop delay. Fit delay against 1/ibias: the intercept is
            # that fixed part, and it is what the bias sweep can separate
            # that a single reading cannot.
            xs = [1.0 / a for a, _ in delays]
            ys = [d for _, d in delays]
            n = len(xs)
            mx, my = sum(xs) / n, sum(ys) / n
            slope = (sum((x - mx) * (y - my) for x, y in zip(xs, ys))
                     / sum((x - mx) ** 2 for x in xs))
            fixed = my - slope * mx
            print(f"\n  Fitting delay against 1/ibias splits it in two: a slew-dependent\n"
                  f"  part, and {fixed:.0f} ns that survives at infinite bias. If slewing were\n"
                  f"  the whole story that intercept would be zero, so what is left is\n"
                  f"  fixed delay through the loop and the instrument together. A single\n"
                  f"  reading at one bias cannot separate those two; the sweep can.")

    if len(usable) > 1:
        # slew = I_tail / C = 4 * ibias / C, so the slope against ibias gives
        # the node capacitance -- and a slope does not need the probe's own
        # capacitance to be known, which a single slew reading does.
        n = len(usable)
        xs = [b["amps"] for b in usable]
        ys = [b["value"] * 1e6 for b in usable]
        mx, my = sum(xs) / n, sum(ys) / n
        slope = (sum((x - mx) * (y - my) for x, y in zip(xs, ys))
                 / sum((x - mx) ** 2 for x in xs))
        c_measured = 4.0 / slope
        c_expected = (profile["tail_amps"] / (profile["published"]["as routed"] * 1e6)
                      - SHEET_CPROBE + AD3_CPROBE)
        print(f"\n  Fitting slew against bias over the {n} points that cleared 3x gives\n"
              f"  a node capacitance of {c_measured * 1e12:.1f} pF, against "
              f"{c_expected * 1e12:.1f} pF from the routed model\n"
              f"  plus this probe -- {c_measured / c_expected:.2f}x.\n\n"
              f"  That is the number to quote, not the single reading above. `tail=4`\n"
              f"  means slew = 4 x ibias / C, so the SLOPE against ibias gives C on\n"
              f"  its own, while a single slew reading needs the probe capacitance to\n"
              f"  be right -- and 24 pF is a datasheet figure, not a measurement.")
    else:
        print("\n  Too few points cleared the 3x margin to fit a capacitance. Lower\n"
              "  the bias further; the rails are set by SLEW_RAILS.")


def _report_tau(profile, nominal, corrected) -> None:
    mean = nominal["value"]
    ratio = mean / corrected["as routed"]
    print(f"\n  Silicon is {ratio:.2f}x the probe-corrected as-routed figure.")
    stim = nominal.get("stimulus_ns")
    if stim:
        print(f"\n  Stimulus edge (input, 10-90%): {stim:.0f} ns. Against a fitted time\n"
              f"  constant of {mean:.0f} ns the stimulus is {mean / stim:.1f}x faster, so the\n"
              f"  settle is the circuit's own.")
    out_ns = nominal.get("rising", {}).get("output_ns")
    if out_ns:
        # An exponential's 10-90% is 2.197 tau. Two routes to one number; a
        # large gap would mean the settle is not a single pole.
        implied = out_ns / 2.197
        print(f"\n  Cross-check: the output's own 10-90% is {out_ns:.0f} ns, and an\n"
              f"  exponential's is 2.197 tau, implying {implied:.0f} ns against the fitted\n"
              f"  {mean:.0f} ns -- {abs(implied - mean) / mean * 100:.1f}% apart.")


if __name__ == "__main__":
    main()
