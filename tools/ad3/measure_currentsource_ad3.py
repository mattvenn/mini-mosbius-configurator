#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Measure examples/currentsource on silicon with an Analog Discovery.

Three experiments, all on one rig, chosen with --mode:

    compliance   sweep the output pin across the supply and watch where the
                 current stops being constant. This is the one to run
                 first: it lands directly on the curve drawn by
                 tools/plot_currentsource_comparison.py.
    ratio        program ratio=1..4 in turn and check the four currents are
                 evenly spaced. Immune to the bias current's calibration,
                 because a ratio of two measured currents cancels it.
    ibias        step the bias current and measure what comes out, which is
                 what turns program.py's approximate level-to-amps constant
                 into a real number.

Run from the repo root, on the host (it needs USB for the demoboard):

    python3 tools/ad3/measure_currentsource_ad3.py --leg source
    python3 tools/ad3/measure_currentsource_ad3.py --mode ratio \\
        --configs build/currentsource_r1.mosbius.json ... (four of them)
    python3 tools/ad3/measure_currentsource_ad3.py --mode ibias

**Why a current source is an easy thing to measure and a transistor is
not.** Every terminal on this chip reaches its pad through a crosspoint
switch and a pad, together on the order of 150-200 Ohm. Measuring a FET,
that resistance is fatal: it sits between you and the drain, so the Vds
you set is not the Vds the device sees. Measuring a current source it
costs almost nothing, because a current source is indifferent to what is
in series with it -- 200 Ohm at 200 uA moves the pin voltage by 40 mV and
moves the current not at all, until you are close enough to a rail that
those 40 mV are the difference between saturation and not. The simulated
curves say the same thing from the other side: the routed leg tracks the
drawn one within 0.5% until the knee.

**The rig is a sense resistor and two scope channels.** The Analog
Discovery has no ammeter, so current is arithmetic: force the pin voltage
through a resistor with W1, measure the drop across that resistor
differentially on scope 1, and measure the pin itself on scope 2.

    I(out of the pin) = (scope 1) / R_sense

4.7 kOhm is the default: it drops about 0.94 V at the 200 uA this example
makes, which still leaves enough of the 3.3 V supply to walk the pin from
one rail to the other. Resolution is not what picks the value -- the
AD3's 5 V span over 14 bits is 305 uV a step, so even 1 kOhm resolves
under a microamp. What picks it is the other end: the drop comes out of
the sweep. The script prints what your resistor buys and costs, and says
so explicitly if it cannot reach both knees.

**The zero is not optional.** An uncalibrated Analog Discovery channel
carries tens of millivolts of its own offset -- this project has measured
~45 mV on these very channels. Across 4.7 kOhm that is 10 uA, or 5% of
the answer, and it looks exactly like a real current. So the script
programs the all-switches-open bitstream first, which disconnects the leg
from the pad while leaving this project's analog mux slot selected, and
records what each channel reads with no current flowing. Everything after
that is offset-corrected. The pin channel is zeroed the same way but only
to about +/-10 mV, since the reference for it is W1's own idea of 0 V.

**Which way is positive.** Current out of the chip pin. That is the
testbench's convention too (`i(vam_source_drawn)` and friends), so the
source leg reads positive here and the sink leg negative, and the numbers
compare to build/currentsource_tb.txt without a sign flip.

**Two pins, one at a time.** The source leg is on ua2 and the sink leg on
ua3 -- different pads, each needing its own sense resistor and both scope
channels -- so a run measures one leg. Both pads are among the five
confirmed on silicon.

**On a demoboard with no current source of its own, the bias is a second
resistor and it is not optional.** `mosbius program --ibias` can only
deliver a current on boards that have the RP2350 bias circuit; without one
the chip's bias pin is simply unfed, every mirror in the design has no
operating point, and a sweep of the output is a careful measurement of
nothing. So this script feeds it from V+ through a series resistor into
the bias pad, and works out which V+ setting gives the current you asked
for from build/ibias_clamp.json -- because how much current a given rail
delivers is not calculable from the resistor alone. The other end of that
resistor is a diode-connected FET, which sets its own voltage; it has to
have been measured. tools/ad3/measure_ibias_clamp_ad3.py is what measures it.
The resistor there also sets the reachable range: through 20k the bias
tops out around 154 uA.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ad3  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from mosbius.model import SwitchConfig  # noqa: E402
from mosbius.pads import format_analog_header, pad_map  # noqa: E402
from mosbius.program import ProgramError, program  # noqa: E402

PROJECT = "tt_um_tnt_mosbius"
SHUTTLE = "ttsky25a"
ALL_SWITCHES_OPEN = "0" * 48
DEFAULT_CONFIG = Path("build/currentsource.mosbius.json")
CLAMP_FILE = Path("build/ibias_clamp.json")

NSAMPLES = 4000
SAMPLE_RATE = 1e5

# The pin must stay between the rails: past either one the pad's ESD diode
# conducts, and what is measured stops being about the mirror. 3.40 V is
# the abort threshold rather than 3.30 so a few millivolts of scope offset
# cannot stop a legitimate sweep at the top of its range.
#
# The bottom is not symmetric with the top, and the difference is the
# point. The source leg's sweep deliberately puts W1 slightly BELOW
# ground, because its current flows out of the pin and down through the
# sense resistor -- so the pin sits above W1, and a pin voltage of 0 V
# means asking W1 for about -0.3 V. That is safe, and the reason is a
# diode drop: a pad 400 mV below ground is still well short of the ~600 mV
# its ESD diode needs to conduct. Widen this and that stops being true.
VAPWR = 3.3
# Where the sweep gives up. Not "past the rail" -- with a big sense
# resistor the pin is *meant* to sit a little outside the rails at the ends
# of the swing, because the resistor drops the difference. What matters is
# whether the pad's ESD diode is actually conducting, and it is not until
# the pin is a diode drop past a rail. Reaching that means the chip has
# stopped carrying the current and the pin is following W1 instead, which
# is worth stopping for whether or not it is dangerous.
PIN_MAX = 3.3 + 0.6
PIN_MIN = -0.6

# Scope windows, per channel. The shunt sees a few hundred millivolts about
# zero and the pin sees the whole supply, so they get different offsets --
# that is what ad3.scope_setup_channels() is for.
SHUNT_RANGE, SHUNT_OFFSET = 5.0, 0.0
PIN_RANGE, PIN_OFFSET = 5.0, 1.65

# Per leg: which net it comes out on, which hardware device the router
# should have picked, and which way its current flows.
LEGS = {
    "source": {
        "net": "ua2", "role": "psource_a", "ratio_field": "mirp_a_ratio",
        "sign": +1,
        "what": "sources current out of the pin, down from VAPWR",
    },
    "sink": {
        "net": "ua3", "role": "nsink_a", "ratio_field": "mirn_a_ratio",
        "sign": -1,
        "what": "sinks current into the pin, down to VGND",
    },
}

# How far past a rail W1 is allowed to go, worked out from the resistor
# rather than fixed. A pad driven past a rail conducts through its ESD
# diode; the series resistor is what makes that a current rather than a
# fault, which is the same argument measure_ibias_clamp_ad3.py makes for
# its 20k. 200 uA is the budget that script settled on, and a diode takes
# it without complaint.
ESD_DIODE = 0.6
ESD_BUDGET = 200e-6
WAVEGEN_LIMIT = 4.9      # the AD3's generators are +/-5 V


def w1_limits(leg: dict, resistor: float, i_max: float) -> tuple[float, float]:
    """How far W1 has to swing to walk the PIN across the whole supply.

    W1 is not the pin. They differ by the drop across the sense resistor,
    which at 200 uA is 0.3 V through 1.5k but 0.94 V through 4.7k -- so
    these limits cannot be constants, and getting them wrong does not fail
    loudly. It just truncates the sweep somewhere short of the rail, which
    looks like a mirror that stopped early.

    Source leg: current flows OUT of the pin and down through the
    resistor, so the pin sits above W1, and reaching a pin voltage of 0 V
    means asking W1 for the drop, negative. Sink leg: the current flows
    the other way, so the pin sits below W1 and reaching VAPWR means
    asking W1 for rather more than VAPWR.

    Either way the far end of the swing is bounded by what the pad's ESD
    diode would pass if the chip stopped conducting entirely -- a bad
    bitstream, a lead off -- because then the pin follows W1 all the way.
    """
    drop = i_max * resistor
    headroom = ESD_DIODE + ESD_BUDGET * resistor
    if leg["sign"] > 0:
        lo = max(-(drop + 0.05), -headroom, -WAVEGEN_LIMIT)
        return lo, VAPWR
    hi = min(VAPWR + drop + 0.05, VAPWR + headroom, WAVEGEN_LIMIT)
    return 0.0, hi


# ---------------------------------------------------------------------------
# Talking to the board
# ---------------------------------------------------------------------------

def run_program(bitstream: str, ibias: float, port: str | None) -> dict:
    """Upload one configuration. Returns the device's own result dict.

    This calls mosbius.program.program() rather than shelling out to
    `mosbius program`, for one reason: the result dict has an `ibias_set`
    field saying whether the board actually delivered the bias current,
    and the CLI renders that as a paragraph of English on stderr. Reading
    the field is not merely tidier -- string-matching that paragraph fails
    in the DANGEROUS direction, because a reworded warning reads as "this
    board has a current source", and the script would then skip setting up
    the bias rail and measure an unbiased chip very carefully.
    """
    hexbits = bitstream
    path = Path(bitstream)
    if path.exists():
        hexbits = json.loads(path.read_text())["bitstream"]
    config = SwitchConfig.from_bitstream(hexbits, ibias=ibias)
    try:
        return program(config, project=PROJECT, port=port)
    except ProgramError as exc:
        raise SystemExit(
            "programming failed, so nothing downstream means anything:\n\n  "
            + str(exc).replace("\n", "\n  ")
        ) from exc


def board_has_bias_source(result: dict) -> bool | None:
    """Did the board deliver the bias current itself?

    True / False from the device's own `ibias_set`, which is
    `tt.analog_current_source is not None` evaluated on the RP2350. None
    when the field is absent, which is not the same as False and must not
    be treated as either -- see the caller, which stops rather than guess.

    Worth being clear about what this is NOT. It is a statement about what
    ttboard believes this board revision is, not a measurement of anything
    on the PCB: no current is sourced, sensed or checked to produce it. The
    only real evidence that bias is reaching the chip is electrical, and
    confirm_bias_reaches_chip() below is where this script gets it.
    """
    return result.get("ibias_set")


def config_from(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(
            f"there is no routed design at {path}\n\n"
            "  That file is what `mosbius route` writes, and it is what gets\n"
            "  programmed. From the repo root, with xschem's Netlist button\n"
            "  having written build/currentsource.spice:\n\n"
            "    python3 -m mosbius.cli route build/currentsource.spice \\\n"
            f"        --out {path}\n"
        )
    return json.loads(path.read_text())


def leg_ratio(routed: dict, leg: dict) -> tuple[int, str]:
    """(ratio, which hardware device) for this leg, read out of the config.

    Read from the bitstream rather than taken from the schematic or the
    filename, because the bitstream is what the chip will actually run --
    and because the router chooses which of the two mirror slots a
    `mosbius_psource` becomes, so `ratio=2` on the sheet could be either
    mirp_a or mirp_b's bits.
    """
    config = SwitchConfig.from_bitstream(routed["bitstream"])
    settings = config.device_settings()
    roles = routed.get("device_roles", {})
    role = next((r for r in roles.values() if r == leg["role"]), None)
    if role is None:
        # The router put this leg on the other slot of the pair.
        other = leg["role"].replace("_a", "_b")
        role = next((r for r in roles.values() if r == other), None)
    if role is None:
        raise SystemExit(
            f"this configuration has no {leg['role']} in it -- its devices are\n"
            f"  {sorted(set(roles.values())) or '(none)'}.\n\n"
            f"  --leg {'source' if leg['sign'] > 0 else 'sink'} measures the "
            f"{leg['role']} leg, so either the wrong\n"
            "  routed design was given, or the design does not contain that device."
        )
    field = leg["ratio_field"].replace("_a_", f"_{role[-1]}_")
    return getattr(settings, field), role


# ---------------------------------------------------------------------------
# The rig
# ---------------------------------------------------------------------------

def sizing_report(leg: dict, resistor: float, i_nom: float, i_max: float) -> str:
    """What this resistor buys and what it costs, before anything is wired.

    Resolution is never the binding constraint here -- the AD3's 5 V span
    over 14 bits is 305 uV a step, so even 1k resolves under a microamp,
    and averaging 4000 samples puts the noise well below that. What binds
    is the other end: the drop across the resistor comes out of the sweep,
    because W1 has only so much range and the pad's ESD diode limits how
    far past a rail it may be pushed. So the number worth printing is not
    the resolution, it is how much of the supply the pin can still be
    walked across.
    """
    lo, hi = w1_limits(leg, resistor, i_max)
    drop = i_nom * resistor
    lsb = 5.0 / 2 ** 14 / resistor
    if leg["sign"] > 0:
        reach = (lo + drop, VAPWR)
    else:
        reach = (0.0, hi - drop)
    out = [
        f"\n  With {resistor:g} ohms and about {i_nom * 1e6:.0f} uA, the sense resistor drops",
        f"  {drop:.2f} V, and one ADC step is {lsb * 1e6:.3f} uA (4000 of them averaged per",
        f"  point, so the noise is well under that). W1 sweeps {lo:+.2f} to {hi:+.2f} V.",
    ]
    if reach[0] > 0.05 or reach[1] < VAPWR - 0.05:
        out += [
            f"\n  THAT ONLY REACHES {reach[0]:.2f}..{reach[1]:.2f} V AT THE PIN, not the full",
            f"  0..{VAPWR} V. The resistor drops too much of the swing: {drop:.2f} V of it,",
            "  against a 3.3 V supply. The knee this example is about may be outside",
            "  the sweep. A smaller sense resistor reaches further; resolution is not",
            "  what you would be giving up, since it is already far better than needed.",
        ]
    else:
        out.append(f"  That walks the pin across the whole 0..{VAPWR} V, knees included.")
    return "\n".join(out) + "\n"


def wiring_table(pad: str, resistor: float, leg_name: str, leg: dict,
                 bias_pad: str | None, bias_resistor: float) -> str:
    """One table, one row per wire, in the order you would make them.

    Split across two tables this was harder to follow, and the resistors
    were the part that suffered: a probe table can only say where a probe
    went, so a resistor's far end got described in passing rather than
    instructed. Here every row is the same shape -- connect this to that --
    and a resistor is simply the two rows its two legs earn. The legs are
    named A and B so later rows can point at one without ambiguity.
    """
    ohms = f"{resistor:g}R" if resistor < 1000 else f"{resistor / 1000:g}k"
    bias = f"{bias_resistor / 1000:g}k"
    rows = [
        (f"{ohms} leg B", f"pad {pad}", "plug this leg straight into the header"),
        ("AD3 W1 (yellow)", f"{ohms} leg A", "drives the pin through the resistor"),
        ("", "", ""),
        ("AD3 1+ (orange)", f"{ohms} leg B", "channel 1 sits across the resistor;"),
        ("AD3 1- (orange/wh)", f"{ohms} leg A", "that drop divided by "
                                                f"{resistor:g} is the current"),
        ("", "", ""),
        ("AD3 2+ (blue)", f"{ohms} leg B", "channel 2 reads that same node against"),
        ("", "", "ground, which is the pin voltage. Joining"),
        ("", "", "at a breadboard and running one wire to"),
        ("", "", f"pad {pad} is fine: at these currents the"),
        ("", "", "wire is worth microvolts"),
        ("AD3 2- (blue/wh)", "any gnd square", "the scope's reference"),
        ("AD3 GND (black)", "any gnd square", "the instrument's own ground reference"),
    ]
    if bias_pad:
        rows += [
            ("", "", ""),
            ("AD3 V+ (red)", f"{bias} leg A", "makes the bias current -- this board"),
            (f"{bias} leg B", f"pad {bias_pad}", "has no current source of its own"),
        ]

    out = [
        f"\n  The {leg_name} leg ({leg['role']}) {leg['what']}, on {leg['net']}.\n",
        "  Wire it like this. Each row is one connection, and a resistor's two",
        "  legs are called A and B so nothing is left to be guessed at:\n",
        "    connect              to               what for",
        "    ------------------   --------------   -----------------------------------",
    ]
    for frm, to, what in rows:
        out.append(f"    {frm:<20s} {to:<16s} {what}".rstrip())
    # Counted from the rows above rather than written out, because a
    # hand-written tally drifts the moment a row moves -- which it did,
    # twice, before this was derived.
    tally = Counter()
    for frm, to, _ in rows:
        for point in (frm, to):
            if point and "gnd" not in point:
                tally[point] += 1
    busy = [(n, c) for n, c in tally.items() if c > 1]

    out += ["", "  Points with more than one wire on them:", ""]
    for point, count in busy:
        out.append(f"    {point:<20s} {count} wires")
    out += [
        "",
        "  Both are ends of the sense resistor, and both are the measurement",
        "  rather than a mistake. Channel 1 has to straddle the resistor to answer",
        "  HOW MUCH CURRENT, and channel 2 has to reach one end of it to answer AT",
        "  WHAT VOLTAGE; neither answer follows from the other, so neither probe",
        "  can be dropped. Every other point takes a single wire, apart from the",
        "  ground squares, which are all one net anyway.",
        "",
        f"  It makes no measurable difference whether 2+ clips to leg B or to pad {pad}",
        "  itself: they are the same node, and the wire between them drops microvolts",
        f"  at {resistor:g} ohms. Use whichever is easier to get a clip onto.",
        "",
        "  ONLY 2- GOES TO GROUND. 1- belongs on leg A, floating at whatever W1 is",
        "  driving, and that is exactly what makes channel 1 a measurement of the",
        "  resistor rather than of leg A against ground. Grounding it instead would",
        "  short W1 to ground through nothing, and read a current that was never",
        "  there. Both '-' leads do have to be connected to something, though --",
        "  a dangling '-' on a differential input makes that channel meaningless.",
        "",
    ]
    in_use = {leg["net"]: pad}
    if bias_pad:
        in_use["ibias"] = bias_pad
    out.append(format_analog_header(in_use))
    return "\n".join(out) + "\n"


def scope_up(handle) -> None:
    ad3.scope_setup_channels(
        handle,
        {0: (SHUNT_RANGE, SHUNT_OFFSET), 1: (PIN_RANGE, PIN_OFFSET)},
        rate=SAMPLE_RATE, nsamples=NSAMPLES,
    )


def measure_zero(handle, port: str | None, resistor: float) -> dict:
    """Both channels' own offsets, with the leg disconnected from the pad.

    The all-zero bitstream is not a circuit: it opens every switch in the
    matrix, so the mirror leg is not connected to anything, while
    `tt.shuttle.get(...).enable()` still selects this project's analog mux
    slot so the pad reaches the chip. No current can flow, so whatever the
    channels report is theirs.

    `--ibias 0` matters for the same reason it does in
    measure_ibias_clamp_ad3.py: on a board that has a current source, any
    bias it delivered would be feeding a leg we are trying to hold at zero.
    """
    print("== zeroing: programming the all-switches-open bitstream")
    run_program(ALL_SWITCHES_OPEN, 0.0, port)

    # Take the shunt zero at several common-mode voltages, not one. With
    # every switch open no current can flow at any of them, so all five
    # readings are the same quantity -- channel 1's own offset -- and any
    # spread between them is the channel changing its mind depending on
    # where the pair of inputs happens to be sitting. That matters because
    # during a sweep the common mode moves by a volt or more, while the
    # zero can only be taken at one point, so a common-mode-dependent
    # offset would survive the correction and land in the answer as
    # current. Measured on the source and sink legs 2026-08-29, both came
    # out about 17 uA away from simulation IN THE SAME ABSOLUTE DIRECTION
    # -- the signature of an additive error of roughly -81 mV, which is
    # what this check exists to catch.
    probes = []
    for level in (0.4, 1.0, 1.65, 2.3, 2.9):
        ad3.wavegen(handle, ch=0, func=ad3.funcDC, offset=level)
        time.sleep(0.3)
        probes.append((level, ad3.mean(
            ad3.acquire(handle, NSAMPLES, tag="zeroing: ", allow_flat=True), 0)))
    shunt = dict(probes)[1.65]

    ad3.wavegen(handle, ch=0, func=ad3.funcDC, offset=0.0)
    time.sleep(0.3)
    pin = ad3.mean(ad3.acquire(handle, NSAMPLES, tag="zeroing: ", allow_flat=True), 1)

    print("  channel 1 (shunt), with no current flowing, at five common modes:")
    for level, value in probes:
        print(f"    both inputs at {level:.2f} V   {value * 1000:+7.3f} mV"
              f"   ({value / resistor * 1e6:+6.2f} uA equivalent)")
    spread = max(v for _, v in probes) - min(v for _, v in probes)
    print(f"  spread {spread * 1000:.2f} mV = {spread / resistor * 1e6:.2f} uA "
          f"of apparent current")
    if spread > 0.010:
        print("\n  THAT SPREAD IS THE MEASUREMENT'S ERROR BAR, and it is bigger than\n"
              "  it should be. No current can flow with every switch open, so all\n"
              "  five of those are the same number measured five times. If they\n"
              "  disagree, channel 1's offset depends on where its inputs sit --\n"
              "  and during a sweep they move over a volt, while only one of these\n"
              "  points can be subtracted. Expect that much error in the result.")
    print(f"  channel 2 (pin)   reads {pin * 1000:+.2f} mV with W1 at 0 V")
    if abs(shunt) > 0.15:
        print("\n  THAT IS TOO BIG TO BE AN OFFSET. A tenth of a volt across the sense\n"
              "  resistor with every switch open means current is flowing where none\n"
              "  can. In order of likelihood: 1- is on the wrong end of the resistor\n"
              "  or is not connected at all; the demoboard's own bias source is still\n"
              "  on; or a lead has slipped onto a neighbouring pad.")
        raise SystemExit("zeroing failed -- fix the wiring rather than subtracting this")
    return {"shunt": shunt, "pin": pin,
            "common_mode_probes": [{"volts": v, "shunt": z} for v, z in probes]}


def confirm_bias_reaches_chip(handle, args, leg: dict, ratio: int,
                              i_nom: float, zero: dict) -> None:
    """Prove electrically that the leg is biased, before measuring it.

    Everything else in this script about the bias is hearsay: which board
    revision ttboard thinks this is, which pad the shuttle index says the
    bias pin comes out on, what a previous run's clamp sweep measured. All
    three can be wrong, and all three fail the same silent way -- a mirror
    with no operating point passes no current, and a sweep of no current is
    a smooth, plausible, entirely flat curve.

    One reading settles it. Hold the pin at mid-rail and see whether
    roughly ratio x ibias comes out. That is not a calibration -- the
    threshold is deliberately loose, at a quarter of nominal -- it is the
    difference between a circuit that is running and one that is not.
    """
    expected = i_nom                      # already ratio x ibias, from main()
    point = hold_pin_at(handle, args.at, args.resistor, zero, leg,
                        args.i_max, "confirming the bias: ")
    if point is None:
        raise SystemExit("could not read the leg at all -- see the error above")
    got = abs(point["amps"])
    want_sign = leg["sign"]
    print(f"== bias check: {point['amps'] * 1e6:+.2f} uA at "
          f"{point['pin']:.3f} V, against "
          f"{want_sign * expected * 1e6:+.0f} uA expected")
    if got >= 0.25 * expected and point["amps"] * want_sign < 0:
        other = "sink" if want_sign > 0 else "source"
        raise SystemExit(
            f"\n  THE CURRENT IS FLOWING THE WRONG WAY ({point['amps'] * 1e6:+.2f} uA "
            f"where {want_sign * expected * 1e6:+.0f} uA was expected).\n\n"
            f"  A {leg['role']} leg can only push current one way, so the magnitude\n"
            "  being about right while the sign is inverted means the resistor is\n"
            f"  on the wrong pad -- almost certainly the {other} leg's, if you have\n"
            "  just measured that one and moved a lead. The header picture above\n"
            "  has the right pad bracketed."
        )
    if got >= 0.25 * expected:
        print("   The leg is running. Everything from here is a measurement of it.")
        return
    where = ("this board sets its own bias, so `mosbius program --ibias` should\n"
             "  have delivered it -- check what it reported"
             if args.has_bias_source else
             f"the bias comes from V+ through your {args.bias_resistor / 1000:g}k\n"
             f"  resistor into pad {pad_map(SHUTTLE, PROJECT)['ibias']}; check that lead, "
             f"and that {CLAMP_FILE}\n  describes the resistor you actually have in there")
    raise SystemExit(
        f"\n  NO CURRENT IS COMING OUT OF THIS LEG ({got * 1e6:.2f} uA against "
        f"{expected * 1e6:.0f} uA).\n\n"
        "  A mirror with no bias passes nothing, and a sweep of nothing is a\n"
        "  smooth flat curve that looks like a measurement -- so this stops here\n"
        "  rather than producing one. In order of likelihood:\n\n"
        f"  - the bias is not reaching the chip: {where}\n"
        "  - the sense resistor is not between W1 and the output pad, or 1+/1-\n"
        "    are not across it\n"
        "  - the output lead is on the wrong pad; the header picture above has\n"
        "    the right one bracketed, and eight of that header's letters are\n"
        "    tied straight to ground\n"
    )


def read_point(handle, resistor: float, zero: dict, tag: str) -> dict | None:
    """One (pin voltage, current) pair, offset-corrected."""
    try:
        samples = ad3.acquire(handle, NSAMPLES, tag=tag)
    except RuntimeError as exc:
        print(f"  {tag}{exc}".replace("\n", "\n  "))
        return None
    shunt = ad3.mean(samples, 0) - zero["shunt"]
    pin = ad3.mean(samples, 1) - zero["pin"]
    return {"shunt_volts": shunt, "pin": pin, "amps": shunt / resistor}


def set_w1(handle, volts: float) -> None:
    ad3.wavegen(handle, ch=0, func=ad3.funcDC, offset=volts)
    time.sleep(0.05)


def hold_pin_at(handle, target: float, resistor: float, zero: dict,
                leg: dict, i_max: float, tag: str, tries: int = 5,
                start: float | None = None) -> dict | None:
    """Servo W1 until the pin sits at `target`, and return that point.

    W1 is not the pin: they differ by the drop across the sense resistor,
    which is the current, which is the thing being measured -- so the
    setting cannot be computed in advance. Two or three corrections get
    there, because the leg's output resistance is tens of kilohms against
    the sense resistor's few, so each step is very nearly a straight line.
    """
    lo, hi = w1_limits(leg, resistor, i_max)
    w1 = start if start is not None else (
        target - leg["sign"] * i_max * resistor * 0.85)   # first guess
    point = None
    for _ in range(tries):
        w1 = max(lo, min(hi, w1))
        set_w1(handle, w1)
        point = read_point(handle, resistor, zero, tag)
        if point is None:
            return None
        if abs(point["pin"] - target) < 0.005:
            break
        w1 += target - point["pin"]
    if point is not None:
        point["w1"] = w1
    return point


def sweep_compliance(handle, leg: dict, resistor: float, zero: dict,
                     step: float, i_max: float) -> list[dict]:
    """The I-V curve of the leg: sweep the PIN, servoing W1 to each target.

    Stepping W1 open-loop and recording wherever the pin lands does not
    work, and the way it fails is worth keeping. The pin is not W1: they
    differ by the drop across the sense resistor, which IS the current. So
    when a leg runs out of compliance and its current collapses, that drop
    collapses with it and the pin jumps -- measured on the sink leg, a
    50 mV step in W1 moved the pin by 1.03 V, straight over the whole
    region where the leg was losing compliance. The sweep skipped exactly
    the part it existed to measure, and then, with the cap now working off
    a near-zero current, sat at one W1 for every remaining step.

    Servoing fixes both: the pin lands where it was asked to, the points
    are evenly spaced in the variable the curve is plotted against, and a
    collapsing current makes the servo work harder rather than making the
    sweep bolt.
    """
    points = []
    seed = None
    target = 0.0
    while target <= VAPWR + 1e-9:
        point = hold_pin_at(handle, target, resistor, zero, leg, i_max,
                            f"at pin = {target:.3f} V: ", start=seed)
        if point is None:
            break
        if not PIN_MIN <= point["pin"] <= PIN_MAX:
            set_w1(handle, 0.0)
            side = "above VAPWR" if point["pin"] > PIN_MAX else "below ground"
            print(f"\n  STOPPED at a pin voltage of {point['pin']:.3f} V, {side}.\n"
                  "  The switch matrix between the device and the pad is powered from\n"
                  "  the same rails, so outside them nothing measured is about the\n"
                  "  mirror. Everything up to here is kept.")
            break
        points.append(point)
        seed = point["w1"] + step        # the next target is one step further
        target += step
    set_w1(handle, 0.0)
    return points


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def report_compliance(points: list[dict], leg: dict, resistor: float,
                      ratio: int, role: str) -> None:
    if len(points) < 5:
        print("\n  Too few points survived to say anything. See the errors above.")
        return

    print(f"\n  pin voltage    current      (W1)")
    print("  -----------    ---------    -------")
    for p in points:
        print(f"  {p['pin']:+8.4f} V   {p['amps'] * 1e6:+8.2f} uA   {p['w1']:+6.3f} V")

    mid = min(points, key=lambda p: abs(p["pin"] - 1.65))
    print(f"\n  At mid-rail ({mid['pin']:.3f} V): {mid['amps'] * 1e6:+.2f} uA, "
          f"from {role} at ratio={ratio}.")

    # The flat region, and where it stops being flat. "Within 5% of the
    # mid-rail value" is the same window applied to the simulated curve,
    # so the two are directly comparable.
    nominal = mid["amps"]
    inside = [p for p in points if abs(p["amps"] - nominal) <= 0.05 * abs(nominal)]
    if inside:
        lo = min(p["pin"] for p in inside)
        hi = max(p["pin"] for p in inside)
        print(f"  Within 5% of that from {lo:.3f} V to {hi:.3f} V of pin voltage --")
        print("  bounded at BOTH ends, which is the part that surprises people. A")
        print("  mirror leg is not an ideal current source, and one number on a")
        print("  symbol hides a curve.")

    flat = [p for p in points if 0.5 <= p["pin"] <= 2.3]
    if len(flat) >= 3:
        slope = ((flat[-1]["amps"] - flat[0]["amps"])
                 / (flat[-1]["pin"] - flat[0]["pin"]))
        if abs(slope) > 1e-12:
            print(f"\n  Output resistance over 0.5..2.3 V: {abs(1 / slope) / 1000:.1f} kOhm "
                  f"({abs(slope) * 1e6:.1f} uA/V).")
            print("  That slope IS the finite output resistance of the mirror, and it is")
            print("  the whole reason this example sweeps rather than reading one point.")

    print(f"\n  The current column is arithmetic on two scope channels across a\n"
          f"  resistor you supplied, so it is only as good as that resistor's\n"
          f"  tolerance ({resistor:g} ohms assumed exactly), and both channels have\n"
          "  had their measured zero subtracted. It does not depend on any\n"
          "  readback from the instrument's own supply.")


def report_ratio(rows: list[dict]) -> None:
    print("\n  ratio   device       current      per unit ratio")
    print("  -----   ----------   ----------   --------------")
    for r in rows:
        print(f"  {r['ratio']:5d}   {r['role']:<10s}   {r['amps'] * 1e6:+8.2f} uA   "
              f"{r['amps'] / r['ratio'] * 1e6:+8.2f} uA")

    roles = {r["role"] for r in rows}
    if len(roles) > 1:
        print(f"\n  THE ROUTER MOVED THE DEVICE between configurations: {sorted(roles)}.\n"
              "  These four currents come from more than one piece of hardware, so a\n"
              "  difference between them is not necessarily a ratio error -- it can\n"
              "  be mismatch between two mirror slots. Re-route so all four land on\n"
              "  the same slot before reading anything into the spacing.")

    per_unit = [r["amps"] / r["ratio"] for r in rows]
    spread = (max(per_unit) - min(per_unit)) / abs(sum(per_unit) / len(per_unit))
    print(f"\n  The per-unit column is what should be constant: it is spread over "
          f"{spread * 100:.1f}%.")
    print("  This is the measurement that does NOT depend on the bias current being")
    print("  what it says it is -- a ratio of two currents from the same reference")
    print("  cancels that error entirely, which is why it is worth running even on")
    print("  a board whose bias is a resistor and a guess.")
    if spread < 0.05:
        print("\n  EVENLY SPACED. The mirror-ratio bits mean what the bit map says they")
        print("  mean, confirmed against silicon -- which nothing in this project had")
        print("  done before.")
    else:
        print("\n  NOT EVENLY SPACED. Before blaming the bit map: check the ratios in")
        print("  the table are 1,2,3,4 as intended (they are read out of the")
        print("  bitstreams, not the filenames), and that the device column is one")
        print("  device throughout.")


def report_ibias(rows: list[dict], commanded: bool) -> None:
    label = "asked for" if commanded else "through Rbias"
    print(f"\n  bias {label:<13s} current out    gain")
    print("  ------------------   ------------   ------")
    for r in rows:
        gain = r["amps"] / r["ibias"] if r["ibias"] else float("nan")
        print(f"  {r['ibias'] * 1e6:14.2f} uA     {r['amps'] * 1e6:+8.2f} uA   {gain:5.2f}x")

    usable = [r for r in rows if r["ibias"] > 1e-6]
    if len(usable) >= 3:
        first, last = usable[0], usable[-1]
        slope = ((last["amps"] - first["amps"]) / (last["ibias"] - first["ibias"]))
        print(f"\n  Slope over the sweep: {slope:.3f} amps out per amp in.")
        print("  For a ratio=N leg that should be N, and how far it misses by is the")
        print("  mirror's own error plus whatever the bias really was.")
    if commanded:
        print("\n  The left column is what was asked for, and program.py turns amps into")
        print("  a level with a constant its own source marks as approximate ('0 -")
        print("  0xffff, up to ~250 uA'). This sweep is what replaces that guess with")
        print("  a measurement -- and every other analog number on this chip rides on it.")
    else:
        print("\n  The left column is (V+ minus the measured bias pad voltage) / Rbias,")
        print("  interpolated from build/ibias_clamp.json rather than commanded, so it")
        print("  is a measured input against a measured output. That is the better")
        print("  version of this experiment, not the worse one.")


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

def subtract_background(points: list[dict], path: Path) -> list[dict]:
    """Remove what the pad node draws when the leg is disconnected.

    Interpolated against pin voltage rather than subtracted point for
    point, because the two sweeps land on slightly different pin voltages
    -- the servo hits its target to within a few millivolts, not exactly,
    and the leg being connected changes where it lands.
    """
    bg = json.loads(path.read_text())
    if bg.get("mode") != "background":
        raise SystemExit(
            f"{path} is a '{bg.get('mode')}' sweep, not a background one.\n\n"
            "  --background wants a sweep taken with every switch open, which is\n"
            "  what --mode background makes. Subtracting anything else would be\n"
            "  subtracting one measurement of the leg from another."
        )
    curve = sorted((q["pin"], q["amps"]) for q in bg["points"])

    def at(v):
        if v <= curve[0][0]:
            return curve[0][1]
        if v >= curve[-1][0]:
            return curve[-1][1]
        for (x0, y0), (x1, y1) in zip(curve, curve[1:]):
            if x0 <= v <= x1:
                f = (v - x0) / (x1 - x0) if x1 > x0 else 0.0
                return y0 + f * (y1 - y0)
        return 0.0

    out = []
    for q in points:
        b = at(q["pin"])
        out.append({**q, "amps_raw": q["amps"], "background": b,
                    "amps": q["amps"] - b})
    return out


def mode_compliance(handle, args, leg, resistor, zero, routed, ratio, role):
    lo, hi = w1_limits(leg, resistor, args.i_max)
    print(f"\n== sweeping W1 from {lo:+.2f} to {hi:+.2f} V in "
          f"{args.step * 1000:.0f} mV steps, which walks the PIN across 0..{VAPWR} V")
    points = sweep_compliance(handle, leg, resistor, zero, args.step, args.i_max)
    if args.background:
        before = min(points, key=lambda q: abs(q["pin"] - 1.65))["amps"]
        points = subtract_background(points, args.background)
        after = min(points, key=lambda q: abs(q["pin"] - 1.65))["amps"]
        print(f"\n== background from {args.background} subtracted: mid-rail went "
              f"{before * 1e6:+.2f} -> {after * 1e6:+.2f} uA")
    report_compliance(points, leg, resistor, ratio, role)
    return {"points": points, "background_file": str(args.background) if args.background else None}


def mode_ratio(handle, args, leg, resistor, zero, routed, ratio, role):
    rows = []
    for path in args.configs:
        cfg = config_from(Path(path))
        this_ratio, this_role = leg_ratio(cfg, leg)
        print(f"\n== programming {path}: {this_role} at ratio={this_ratio}")
        run_program(str(path), args.ibias, args.port)
        point = hold_pin_at(handle, args.at, resistor, zero, leg,
                            args.i_max, f"at ratio={this_ratio}: ")
        if point is None:
            print("  no usable reading at this ratio, skipping it")
            continue
        print(f"  pin held at {point['pin']:.4f} V, current "
              f"{point['amps'] * 1e6:+.2f} uA")
        rows.append({"ratio": this_ratio, "role": this_role,
                     "config": str(path), **point})
    if len(rows) < 2:
        raise SystemExit("fewer than two ratios measured -- nothing to compare")
    rows.sort(key=lambda r: r["ratio"])
    report_ratio(rows)
    return {"rows": rows, "held_at": args.at}


def _rail_for_amps(curve: list[dict], amps: float) -> float | None:
    """The V+ setting that puts `amps` into the bias pad, or None if the
    clamp sweep never reached it."""
    for a, b in zip(curve, curve[1:]):
        if min(a["amps"], b["amps"]) <= amps <= max(a["amps"], b["amps"]):
            span = b["amps"] - a["amps"]
            if abs(span) < 1e-12:
                return a["set"]
            return a["set"] + (amps - a["amps"]) / span * (b["set"] - a["set"])
    return None


def set_bias(handle, args) -> float | None:
    """Get the requested bias current into the chip, whichever board this is.

    On a demoboard with the RP2350 current source there is nothing to do:
    `mosbius program --ibias` already delivered it, and V+ is not involved.

    On a board without one the bias pin is simply unfed, and every mirror
    and tail in the design has no operating point -- so a sweep of the
    output would be a careful measurement of nothing. The current has to
    come from V+ through the series resistor, and how much current a given
    V+ actually delivers is not calculable from the resistor alone (the
    other end is a diode-connected FET, which sets its own voltage), so it
    is read off the clamp sweep that measured it.

    Returns the bias current now flowing, or None on a board that sets its
    own.
    """
    if args.has_bias_source:
        return None
    curve = _clamp_curve()
    rail = _rail_for_amps(curve, args.ibias)
    if rail is None:
        lo = min(p["amps"] for p in curve) * 1e6
        hi = max(p["amps"] for p in curve) * 1e6
        raise SystemExit(
            f"{args.ibias * 1e6:.1f} uA of bias is outside what "
            f"{CLAMP_FILE} reached ({lo:.1f}..{hi:.1f} uA).\n\n"
            "  That sweep was taken through a particular series resistor, and the\n"
            "  resistor sets the range: a bigger one cannot push as much current.\n"
            "  Either ask for a current inside that range with --ibias, or re-run\n"
            "  the clamp sweep with a smaller resistor:\n\n"
            "    python3 tools/ad3/measure_ibias_clamp_ad3.py --resistor 10000\n"
        )
    ad3.supply(handle, rail, "V+", current_limit=0.05, settle=0.3)
    ad3.wait_supply_stable(handle, "V+")
    print(f"== bias: V+ at {rail:.3f} V, which {CLAMP_FILE} puts at "
          f"{args.ibias * 1e6:.1f} uA into the bias pad")
    print("   This board has no current source of its own, so that rail IS the")
    print("   bias current. Leave it alone for the rest of the run.")
    return args.ibias


def _clamp_curve() -> list[dict]:
    if not CLAMP_FILE.exists():
        raise SystemExit(
            f"this board has no current source of its own, so the bias comes from\n"
            f"  V+ through a resistor -- and to know what current that is, the bias\n"
            f"  pad has to have been characterised first. {CLAMP_FILE} is missing.\n\n"
            "  Run this, which also confirms the pad letter:\n\n"
            "    python3 tools/ad3/measure_ibias_clamp_ad3.py --resistor 20000\n"
        )
    return json.loads(CLAMP_FILE.read_text())["points"]


def _ibias_at_rail(curve: list[dict], rail: float) -> float:
    """Interpolate the bias current the clamp sweep measured at this V+."""
    for a, b in zip(curve, curve[1:]):
        if min(a["set"], b["set"]) <= rail <= max(a["set"], b["set"]):
            span = b["set"] - a["set"]
            if abs(span) < 1e-12:
                return a["amps"]
            f = (rail - a["set"]) / span
            return a["amps"] + f * (b["amps"] - a["amps"])
    return curve[-1]["amps"] if rail > curve[-1]["set"] else curve[0]["amps"]


def mode_ibias(handle, args, leg, resistor, zero, routed, ratio, role):
    rows = []
    if args.has_bias_source:
        levels = [args.ibias * f for f in (0.25, 0.5, 0.75, 1.0, 1.5, 2.0)]
        for amps in levels:
            print(f"\n== programming with --ibias {amps * 1e6:.1f}u")
            run_program(str(args.config), amps, args.port)
            point = hold_pin_at(handle, args.at, resistor, zero, leg,
                                args.i_max, f"at ibias={amps * 1e6:.0f}u: ")
            if point is None:
                continue
            print(f"  pin held at {point['pin']:.4f} V, current "
                  f"{point['amps'] * 1e6:+.2f} uA")
            rows.append({"ibias": amps, "commanded": True, **point})
    else:
        curve = _clamp_curve()
        run_program(str(args.config), 0.0, args.port)
        rail = 1.5
        while rail <= 4.5 + 1e-9:
            ad3.supply(handle, rail, "V+", current_limit=0.05, settle=0.2)
            amps = _ibias_at_rail(curve, rail)
            print(f"\n== V+ at {rail:.2f} V, which the clamp sweep puts at "
                  f"{amps * 1e6:.1f} uA of bias")
            point = hold_pin_at(handle, args.at, resistor, zero, leg,
                                args.i_max, f"at V+={rail:.2f}: ")
            if point is not None:
                print(f"  pin held at {point['pin']:.4f} V, current "
                      f"{point['amps'] * 1e6:+.2f} uA")
                rows.append({"ibias": amps, "rail": rail, "commanded": False, **point})
            rail += 0.5
        ad3.supplies_off(handle)
    if len(rows) < 2:
        raise SystemExit("fewer than two bias settings measured -- nothing to compare")
    report_ibias(rows, commanded=args.has_bias_source)
    return {"rows": rows, "held_at": args.at}


def mode_background(handle, args, leg, resistor, zero, routed, ratio, role):
    """Sweep the pin with every switch open: whatever still flows is not the leg.

    This exists because of a discrepancy the two legs found together. Each
    disagreed with simulation by about the same ABSOLUTE current -- the
    source 18 uA low, the sink 16 uA high -- which is not what a bias error
    does (that would scale both) and not what the channel's common-mode
    error does (measured at -9.7 mV/V, worth about 1 uA, and of opposite
    sign on the two legs). It IS what a parasitic draw on the pad node
    does: current that leaves through the sense resistor without ever
    reaching the leg subtracts from the source and adds to the sink.

    So measure it. The all-zero bitstream opens every crosspoint, which
    disconnects the leg while leaving this project's analog mux slot
    selected, so the pad still reaches the chip and every other thing on
    that node -- the two scope inputs, the pad's own leakage, the
    deselected mux slots -- is still there. Whatever current flows is the
    background, and how it varies with pin voltage says what it is: flat
    means a constant draw, a straight line through the origin means
    something resistive, and its slope is then in every output-resistance
    number this rig has produced.
    """
    print("\n== programming the all-switches-open bitstream: the leg is now"
          " disconnected")
    run_program(ALL_SWITCHES_OPEN, 0.0, args.port)
    points = sweep_compliance(handle, leg, resistor, zero, args.step, args.i_max)
    if len(points) < 5:
        print("\n  Too few points survived to say anything.")
        return {"points": points}

    print(f"\n  pin voltage    background current")
    print("  -----------    -------------------")
    for q in points[::6]:
        print(f"  {q['pin']:+8.4f} V   {q['amps'] * 1e6:+8.3f} uA")

    lo, hi = points[0], points[-1]
    span = hi["pin"] - lo["pin"]
    slope = (hi["amps"] - lo["amps"]) / span if abs(span) > 0.1 else 0.0
    at_mid = min(points, key=lambda q: abs(q["pin"] - 1.65))["amps"]
    print(f"\n  At mid-rail the background is {at_mid * 1e6:+.3f} uA.")
    if abs(slope) > 1e-9:
        print(f"  It changes by {slope * 1e6:+.3f} uA per volt of pin voltage, which is"
              f"\n  {abs(1 / slope) / 1000:.1f} kOhm of effective resistance on that node.")
    print("\n  Subtract this from a compliance sweep with:\n\n"
          f"    python3 {sys.argv[0]} --leg {args.leg} "
          f"--background build/currentsource_background_{args.leg}.json\n")
    return {"points": points}


MODES = {"compliance": mode_compliance, "ratio": mode_ratio, "ibias": mode_ibias,
         "background": mode_background}


# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=sorted(MODES), default="compliance",
                        help="which experiment to run (default: compliance)")
    parser.add_argument("--leg", choices=sorted(LEGS), default="source",
                        help="which mirror leg to measure (default: source)")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG,
                        help=f"routed design to program (default: {DEFAULT_CONFIG})")
    parser.add_argument("--configs", nargs="+", default=[],
                        help="--mode ratio: the routed designs, one per ratio")
    parser.add_argument("--resistor", type=float, default=4700.0,
                        help="sense resistance in ohms (default: 4700)")
    parser.add_argument("--bias-resistor", type=float, default=20000.0,
                        help="series resistance into the bias pad, on a board with "
                             "no current source (default: 20k)")
    parser.add_argument("--ibias", type=float, default=100e-6,
                        help="bias current in amps (default: 100u)")
    parser.add_argument("--background", type=Path, default=None,
                        help="a --mode background sweep to subtract, removing "
                             "whatever the pad node draws that is not the leg")
    parser.add_argument("--i-max", type=float, default=None, dest="i_max",
                        help="largest current to plan the W1 swing around, in amps "
                             "(default: 1.3x what ratio and --ibias imply)")
    parser.add_argument("--at", type=float, default=1.65,
                        help="pin voltage to hold for --mode ratio/ibias (default: 1.65)")
    parser.add_argument("--step", type=float, default=0.05,
                        help="--mode compliance: W1 step in volts (default: 0.05)")
    parser.add_argument("--pad", default=None,
                        help="override the output pad letter (default: looked up)")
    parser.add_argument("--port", default=None, help="demoboard serial port")
    parser.add_argument("--out", type=Path, default=None,
                        help="where to write the JSON "
                             "(default: build/currentsource_<mode>_<leg>.json)")
    args = parser.parse_args()

    if args.mode == "ratio" and len(args.configs) < 2:
        raise SystemExit(
            "--mode ratio needs at least two routed designs to compare, given with\n"
            "  --configs. `ratio=` is a property of the symbol on the schematic, so\n"
            "  each one is its own netlist and its own route -- four runs, not one\n"
            "  bitstream with a knob in it. In the container, from the repo root,\n"
            "  after editing examples/currentsource/currentsource.sch to ratio=N:\n\n"
            "    xschem -n -q examples/currentsource/currentsource.sch\n"
            "    python3 -m mosbius.cli route build/currentsource.spice \\\n"
            "        --out build/currentsource_rN.mosbius.json\n"
        )

    leg = LEGS[args.leg]
    pads = pad_map(SHUTTLE, PROJECT)
    pad = args.pad or pads[leg["net"]]

    routed = config_from(args.config if args.mode != "ratio" else Path(args.configs[0]))
    ratio, role = leg_ratio(routed, leg)

    i_nom = ratio * args.ibias
    if args.i_max is None:
        args.i_max = i_nom * 1.3

    print(f"== {args.mode} on the {args.leg} leg: {role} at ratio={ratio}, "
          f"out on {leg['net']} (pad {pad})")
    print(sizing_report(leg, args.resistor, i_nom, args.i_max))

    # Program once before wiring, to find out what kind of board this is --
    # whether the bias current can be commanded or has to be made with a
    # resistor changes the wiring the user is about to do.
    print("== checking the board")
    first = run_program(str(args.config if args.mode != "ratio" else args.configs[0]),
                        args.ibias, args.port)
    args.has_bias_source = board_has_bias_source(first)
    if args.has_bias_source is None:
        raise SystemExit(
            "the board did not say whether it set the bias current.\n\n"
            "  Its result had no `ibias_set` field, which is neither yes nor no,\n"
            "  and the two need different wiring: a board with the RP2350 current\n"
            "  source needs nothing on the bias pad, and a board without one needs\n"
            "  a supply and a series resistor there or every mirror in the design\n"
            "  has no operating point. Guessing either way produces a measurement\n"
            "  that looks fine and means nothing, so this stops instead.\n\n"
            "  `python3 -m mosbius.cli program ... --ibias 100u` says in plain\n"
            "  words which board it found; run that and use what it reports."
        )
    print(f"  bitstream uploaded; this board "
          + ("delivers the bias current itself"
             if args.has_bias_source else
             "has NO current source, so the bias comes from V+ and a resistor"))
    bias_pad = None if args.has_bias_source else pads["ibias"]

    print(wiring_table(pad, args.resistor, args.leg, leg,
                       bias_pad, args.bias_resistor))
    input("  Press Enter once that is wired and both resistors are in place... ")

    with ad3.device() as handle:
        scope_up(handle)
        zero = measure_zero(handle, args.port, args.resistor)
        if args.mode not in ("ratio", "background"):
            print(f"== programming {args.config}")
            run_program(str(args.config), args.ibias, args.port)
        elif args.mode == "ratio":
            # mode_ratio() below programs each of --configs in turn, but
            # measure_zero() just above left the all-switches-open
            # bitstream on the chip -- the leg is disconnected. Without
            # this, confirm_bias_reaches_chip() ran against that
            # disconnected state and always reported no current, on a
            # circuit that was actually fine (caught on a real bench
            # 2026-09-01: an independent ammeter read 93.6 uA on the same
            # leg this was reporting 0.02 uA for). ratio/i_nom above are
            # already this config's own, so program it here to match.
            print(f"== programming {args.configs[0]}")
            run_program(str(args.configs[0]), args.ibias, args.port)
        # The bias goes on AFTER the zero, so the zero is unambiguously a
        # no-current reading, and before the measurement, because without
        # it this board's mirrors have no operating point and the sweep
        # would be a careful measurement of nothing. --mode ibias steps the
        # bias itself, so it does its own.
        if args.mode not in ("ibias", "background"):
            set_bias(handle, args)
            confirm_bias_reaches_chip(handle, args, leg, ratio, i_nom, zero)
        payload = MODES[args.mode](handle, args, leg, args.resistor, zero,
                                   routed, ratio, role)
        set_w1(handle, 0.0)
        ad3.wavegen(handle, ch=0, enable=False)
        ad3.supplies_off(handle)

    # The leg is in the filename because a run measures one of the two, and
    # a second run must not silently overwrite the first -- the plot script
    # draws whichever of the pair it finds.
    out = args.out or Path(f"build/currentsource_{args.mode}_{args.leg}.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({
        "mode": args.mode, "leg": args.leg, "net": leg["net"], "pad": pad,
        "role": role, "ratio": ratio, "resistor": args.resistor,
        "ibias_commanded": args.ibias, "has_bias_source": args.has_bias_source,
        "zero": zero, **payload,
    }, indent=2) + "\n")
    print(f"\n== written to {out}")
    if args.mode == "compliance":
        print("   Draw it against the two simulated curves with:\n"
              "     python3 tools/plot_currentsource_comparison.py")


if __name__ == "__main__":
    main()
