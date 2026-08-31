# Ring oscillator

Three inverting stages wired in a loop, with a fourth inverter buffering
the loop out to `ua3`. Eight transistors, which is every usable single FET
on the chip. An odd number of inversions round a closed loop has no stable
state, so the loop free-runs. The buffer is there because a probe on a
loop node is inside the feedback path and changes the oscillator instead
of measuring it.

![Ring oscillator output as drawn, and as routed against silicon](ring_comparison.png)

*Fig. 1. Two periods of the buffered output on `ua3`: as drawn (ideal
wires), and as routed (through the configured switch matrix, from `mosbius
simulate`) against a ttsky25a chip measured with an Analog Discovery 3.
The silicon trace is folded from 300 periods and scaled into the routed
swing, since the leads roll off badly at 40 MHz; the period is what is
being compared, not the amplitude.*

| | as drawn | as routed | on silicon |
|---|---|---|---|
| frequency | 2.289 GHz | 43.89 MHz | 39.528 MHz |
| against silicon | x58 too fast | +11% | -- |

## Try this

Find the process corner this chip came from. `sh tools/sweep_corners.sh`
re-runs the routed deck at `tt`, `fs`, `sf`, `ff` and `ss` by rewriting
the `.lib` line in the netlist, and `python3 tools/compare_corners.py`
ranks the results against the bench.

A ring's frequency alone will not settle it, which is the interesting
part: slowing the PMOS while speeding the NMOS roughly cancels around a
loop, so the mixed corners sit close together. Run the same sweep on
[`../inverter/`](../inverter/README.md), whose trip point is a pure
NMOS-against-PMOS strength ratio, and see which corner the two agree on.

## Reproducing the numbers

```bash
sh tools/check_example_sim.sh ring      # as drawn and as routed, in the container
python3 tools/measure_ring_ad3.py       # on silicon, on the host
python3 tools/plot_ring_comparison.py   # the figure
```
