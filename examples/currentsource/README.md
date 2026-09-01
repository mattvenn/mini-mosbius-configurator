# Programmable current source and sink

Two devices and one property each: `XI1` sources current out of `ua2` down
from the supply, `XI2` sinks current into `ua3` down to ground. Both are
slaves of the chip's own bias reference, and `ratio` -- 1 to 4, in
multiples of the reference current -- is the only property either has.
Neither has a drawn bias pin: `ibias` reaches them implicitly, the same
way the body ties do, so the sheet has two wires on it. This is the only
example whose subject is the bias current itself, and the only one that
measures a current rather than a voltage.

![Current out of each pin against pin voltage, and deviation from mid-rail, as drawn, as routed and on silicon](currentsource_comparison.png)

*Fig. 1. Current out of each pin against the voltage on that pin, and the
same curves normalised to their own mid-rail value: as drawn (ideal
wires), as routed (through the configured switch matrix, from `mosbius
simulate`), and measured on a ttsky25a chip with an Analog Discovery 3,
both legs at `ratio=2` and about 100 uA of bias.*

| at mid-rail | as drawn | as routed | on silicon |
|---|---|---|---|
| `psource_a` (source) | +209.9 uA | +209.3 uA | +191.3 uA |
| `nsink_a` (sink) | -201.3 uA | -203.9 uA | -220.4 uA |
| output resistance, 0.5-2.3 V (source) | -- | 85.5 kOhm | 120 kOhm |
| output resistance, 0.5-2.3 V (sink) | -- | 79.1 kOhm | 107 kOhm |

*The normalised panel is the honest comparison: it cancels the bias
current, which on a demoboard without a programmable source is a bench
supply through a resistor and is the least trustworthy number in the
measurement.*

## The ratio cycler bits, confirmed on silicon

Checked 2026-09-01: routed the same sheet at `ratio` 1, 2, 3 and 4 (four
bitstreams, via `tools/sweep_ratio_currentsource.sh`, which rewrites the
netlist rather than the schematic -- the committed sheet and every number
above stay at `ratio=2`) and measured one leg at each with
`measure_currentsource_ad3.py --mode ratio`. `psource_a` stayed on `ua2` and
`nsink_a` on `ua3` in all four, so the bitstreams differ only in the ratio
cycler bits.

| ratio | `psource_a` (source) | per unit | `nsink_a` (sink) | per unit |
|---|---|---|---|---|
| 1 | +96.07 uA | +96.07 uA | -110.21 uA | -110.21 uA |
| 2 | +190.41 uA | +95.21 uA | -219.25 uA | -109.62 uA |
| 3 | +285.87 uA | +95.29 uA | -325.81 uA | -108.60 uA |
| 4 | +379.17 uA | +94.79 uA | -433.63 uA | -108.41 uA |

Spread across the four per-unit values: 1.3% (source), 1.6% (sink) -- evenly
spaced. The ratio of two currents from the same bias reference cancels the
demoboard's uncalibrated bias entirely, which is what makes this the one
measurement here an uncalibrated bias can't spoil. The mirror-ratio bits mean
what the bit map says they mean: the first of the chip's 11 device-setting
cycler bit-groups exercised on real silicon (CLAUDE.md, TODO.md).

## Reproducing the numbers

The first line runs in the IIC-OSIC-TOOLS container; the rest run on
the host. [`../README.md`](../README.md#running-each-examples-commands)
has the docker invocation.

```bash
sh tools/sim/check_example_sim.sh currentsource                 # as drawn and as routed, in the container
python3 tools/ad3/measure_ibias_clamp_ad3.py --resistor 20000   # set the bias rail
python3 tools/ad3/measure_currentsource_ad3.py                  # on silicon, on the host
python3 tools/plot_currentsource_comparison.py                  # the figure

sh tools/sweep_ratio_currentsource.sh                            # the four ratio configs
python3 tools/ad3/measure_currentsource_ad3.py --mode ratio --leg source \
    --configs build/currentsource_r1.mosbius.json build/currentsource_r2.mosbius.json \
              build/currentsource_r3.mosbius.json build/currentsource_r4.mosbius.json
python3 tools/ad3/measure_currentsource_ad3.py --mode ratio --leg sink \
    --configs build/currentsource_r1.mosbius.json build/currentsource_r2.mosbius.json \
              build/currentsource_r3.mosbius.json build/currentsource_r4.mosbius.json
```
