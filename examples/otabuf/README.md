# OTA unity-gain follower

One device: the chip's operational transconductance amplifier, five
transistors and a tail bank in a single block, wired as a follower. The
input is on `ua1`, the output on `ua2`, and the inverting input is tied to
that same `ua2` -- the feedback that makes the output follow the input.
The mirror node is brought out on `ua3` so the bias can be seen. Feedback
has to come from the inverting output: the other output is the
low-impedance mirror node, and feeding that back builds a latch instead,
which routes just as cleanly and looks almost identical on the sheet.

![OTA follower output and offset as drawn, as routed and on silicon](otabuf_comparison.png)

*Fig. 1. Output against input, and output minus input, as drawn (ideal
wires), as routed (through the configured switch matrix, from `mosbius
simulate`), and measured on a ttsky25a chip with an Analog Discovery 3, at
`tail=4` and about 100 uA of bias.*

| | as drawn | as routed | on silicon |
|---|---|---|---|
| closed-loop slope, 1.00-2.50 V | 0.9599 | 0.9615 | 0.9476 |
| offset at 1.00 V | +30.2 mV | +25.0 mV | +36.2 mV |
| offset at 1.65 V | +8.6 mV | +5.9 mV | +9.3 mV |
| offset at 2.50 V | -31.7 mV | -33.1 mV | -44.2 mV |
| input common-mode range | 0.85-2.90 V | 0.85-2.90 V | 0.57-2.90 V |
| slew rate, 1.3-2.0 V rising | 42.9 V/us | 15.4 V/us | not published |

*Read the slope rather than the offsets: output minus input on a bench
carries the difference between two scope channel offsets, which on this
instrument is the same tens of millivolts as the offsets being measured. A
slope is a ratio of differences within each channel, so it survives that.*

## On tt_um_mosbius

| | as drawn | as routed | on silicon |
|---|---|---|---|
| closed-loop slope, 1.00-2.50 V | 0.9569 | 0.9587 | 0.9538 |
| offset at 1.00 V | +30.0 mV | +26.2 mV | +29.9 mV |
| offset at 1.65 V | +8.3 mV | +5.6 mV | +5.3 mV |
| offset at 2.50 V | -34.6 mV | -35.7 mV | -39.6 mV |
| input common-mode range | 0.85-2.90 V | 0.85-2.90 V | 0.65-2.70 V |
| slew rate, 1.3-2.0 V rising | 42.7 V/us | 15.3 V/us | -- (nominal bias is generator-limited here) |
| node capacitance, fitted against bias | -- | 40.1 pF | 43.9 pF |

Silicon's slope shortfall from 1 is 1.12x the routed model's -- less than
tnt's 1.36x, the same direction as the currentsource legs. Slew rate was
swept 18-100 uA; only the bottom three bias points cleared the 3x margin
against the AD3 generator's own edge, so the nominal-bias slew isn't
directly comparable. The capacitance fit uses those three and matches the
routed model to 1.09x -- the same agreement as tnt's part.

The as-drawn column moved on 2026-09-10, when `mosbius_ota.sch` learned
that this part ties its NMOS input pair's bulk to the pair's own shared
source rather than to ground ([`../../PARTS.md`](../../PARTS.md)). Almost
all of the move lands on the offset at the top of the input range, which
goes from -31.7 mV to -34.6 mV: removing the body effect lowers the pair's
threshold, and the top of the range is where that headroom is scarcest.
The offsets at 1.00 V and 1.65 V move under a fifth of a millivolt each,
and the as-drawn slew rate does not move at all, because slew is set by the
tail current and the node capacitance rather than by a threshold. The
as-routed column is unchanged to the last digit, verified by re-running it
with the sheet reverted: it comes from the part's own extracted device
library, which always had the bulk right.

Two things this table does not settle. The input common-mode range is
carried over from `tt_um_tnt_mosbius` rather than simulated for this part,
which the bulk correction makes a weaker assumption than it was, since the
low end of that range is a threshold. And the slew row read 15.7 V/us until
2026-09-10, which was `tt_um_tnt_mosbius`'s number copied by mistake; the
simulation gives 15.3 both before and after the correction, and that is
what `tools/ad3/measure_settling_ad3.py` had all along.

## Try this

Trade current for speed. The follower's slew rate is set by how fast the
tail current can charge whatever hangs on the output -- the bond pad and
the probe included. `tools/ad3/measure_settling_ad3.py otabuf` steps the input
and times the output, and the bias current is whatever the supply and
series resistor put into pad K, so re-running it at a few supply settings
gives slew rate against bias. The table's slew row is what to compare
against; the script corrects for the Analog Discovery's 24 pF input first,
because that row assumes the sheet's 10 pF probe and slew goes as 1/C. The
silicon cell says "not published" rather than "not measured": this sweep
was run on 2026-08-29, but its result was never written down anywhere
outside a gitignored `build/` file, so there is no number here to stand
behind. Take it down until the output no longer
settles before the next step: that is this circuit's lower bias limit at
that load. The `tail` property (2, 4, 6 or 8) is the other half of the
same knob, and changing it is a new bitstream rather than a new supply
setting.

## Reproducing the numbers

The first line runs in the IIC-OSIC-TOOLS container; the rest run on
the host. [`../README.md`](../README.md#running-each-examples-commands)
has the docker invocation.

```bash
sh tools/sim/check_example_sim.sh otabuf                        # as drawn and as routed, in the container
python3 tools/ad3/measure_ibias_clamp_ad3.py --resistor 20000   # set the bias rail
python3 tools/ad3/measure_otabuf_ad3.py                         # on silicon, on the host
python3 tools/plot_otabuf_comparison.py                         # the figure
```
