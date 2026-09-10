# Differential amplifier

Five transistors: an NMOS differential pair (`XM1`/`XM2`) biased by the
chip's tail current bank (`XT1`), loaded by a diode-connected PMOS current
mirror (`XM3`/`XM4`). The pair's gates are the two inputs on `ua1` and
`ua2`, their sources are tied together, and `XT1`'s single drawn pin is
wired to that shared source -- which is how the router is told those two
FETs are a pair rather than two independent FETs. The mirror turns the
pair's differential current into a single-ended output on `ua4`.

![Differential amplifier transfer curve and gain against tail current, as drawn, as routed and on silicon](diffamp_comparison.png)

*Fig. 1. Output on `ua4` against the differential input, and gain against
tail current: as drawn (ideal wires), as routed (through the configured
switch matrix, from `mosbius simulate`), and measured on a ttsky25a chip
with an Analog Discovery 3. Simulated at the `tt` corner with the default
10x probe.*

| | as drawn | as routed | on silicon |
|---|---|---|---|
| small-signal gain | ~19.5 V/V | 19.77 V/V | 16.19 V/V |
| output base | 2.012 V | 2.018 V | ~2.07 V |

## On tt_um_mosbius

| | as drawn | as routed | on silicon |
|---|---|---|---|
| small-signal gain | 19.2 V/V | 19.53 V/V | 17.91 V/V |
| output base | 2.009 V | 2.018 V | 2.007 V |

Silicon is about 7% below as-drawn -- less than tnt's chip, and this part's
corner is not established, so no `ss` conclusion yet.

The as-drawn column moved on 2026-09-10, when the ideal library learned
that this part's NMOS differential pair ties its bulk to its own shared
source rather than to ground ([`../../PARTS.md`](../../PARTS.md)). The shift is small -- 1% of
gain, 4 mV of output -- because that shared source is a virtual ground for
a differential input, so the body effect largely drops out. A source
follower, whose source moves with the signal, shifts about 15%. The
as-routed column is unchanged to the last digit, which is what says the
correction landed on the ideal side only: the routed branch always had
this right, since it comes from the part's own extracted device library.

## Try this

Change the tail current and see how little the gain moves. `XT1`'s `tail`
property takes 2, 4, 6 or 8, in multiples of the chip's reference current,
and each value is a different bitstream, so this is four route-and-measure
runs rather than one sweep. Strong-inversion theory says gain should scale
with the square root of the tail current; check whether these devices
agree, and what that says about which region they are working in.

## Reproducing the numbers

The first line runs in the IIC-OSIC-TOOLS container; the rest run on
the host. [`../README.md`](../README.md#running-each-examples-commands)
has the docker invocation.

```bash
sh tools/sim/check_example_sim.sh diffamp                       # as drawn and as routed, in the container
python3 tools/ad3/measure_ibias_clamp_ad3.py --resistor 20000   # set the bias rail
python3 tools/ad3/measure_diffamp_ad3.py                        # on silicon, on the host
python3 tools/plot_diffamp_comparison.py                        # the figure
```
