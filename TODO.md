# todo

Grouped by what kind of work an item is, and numbered from 1 straight
through the groups. As always, the numbering is rewritten whenever
anything is removed, so cite an item by describing it, not by its number.

## Bench and hardware in the loop

1 measure the inverter's rise time on silicon. `examples/inverter/`'s
table has a hole in it: the 10%-90% rise row reads 8.16 ns as drawn and
24.63 ns as routed, and "not measured" on the chip. It is the one row
where the switch matrix makes a large difference, so it is the row worth
having.

Two things make it harder than the DC sweep already in
`tools/measure_inverter_ad3.py`. The edge is a few tens of nanoseconds, so
the stimulus needs a source with a much faster edge than the AD3's
waveform generator, and its own settling has to be subtracted or ruled
out; the AD3's digital output is one candidate and is untested here. And
the meter is part of the circuit: the AD3's 1 MOhm / 24 pF input is a much
heavier load than the 10 pF the committed testbench assumes, so the
comparison has to be against a deck re-run at `rprobe=1meg cprobe=24p`,
which the testbench already parameterises.

2 no device-setting cycler bit has ever been varied on silicon, and the
mirror ratio is the cheapest one to check.

All 11 cyclers -- four FET widths, four mirror ratios, three tails --
share one encoding, `n = step * (1 + b_lsb + 2*b_msb)` (SPEC.md Sec 2.11),
and that came from the placeholder configurator's SVG, which is not an
independent oracle for its own bit map. Every measurement so far uses one
fixed setting per bitstream: `examples/diffamp/` and `examples/pdiffamp/`
do vary the tail current, but by moving the bias rail, not by changing
`tail=`, so the bits themselves are untested.

`examples/currentsource/` is the vehicle because the answer is a ratio of
two currents from the same reference, which cancels the demoboard's
uncalibrated bias source entirely -- the one experiment here immune to it.
Everything measured on that example so far was at `ratio=2`, and `ratio`
and the bias current enter the answer only as a product.

Making the four configurations needs no schematic edit: rewrite
`ratio=2` to 1/3/4 in `build/currentsource.spice` and route each, the same
netlist-not-schematic trick `tools/sweep_corners_currentsource.sh` uses so
the committed sheet and every published number stay put. Checked
2026-08-31: all four route, all four leave `psource_a` on `ua2` and
`nsink_a` on `ua3`, and the bitstreams differ only in the ratio cycler
bits. `tools/measure_currentsource_ad3.py --mode ratio` takes them with
`--configs`, reads each ratio back out of its own bitstream rather than
its filename, and warns if the router did move a device between them.

One measured result bears on this and currently lives only in a gitignored
`build/` file: stepping the bias current at `ratio=2` gave 7 points from
24 to 154 uA fitting out = 1.9127 x in - 0.508 uA. The linearity is
excellent (residuals under 0.6 uA) but the slope is 4.4% below the ideal
2.000 -- and that slope is not separable from a scale error in
`build/ibias_clamp.json`, since the ibias axis is read from it rather than
measured. The ratio experiment is what tells those two apart.

## Examples

3 make it easy for people to submit designs to the examples

## Tests and CI

4 look at combining the tests with the github tests and the spice regression and the AD3 tests. at
the moment I think they're all a bit separate. possiblity to reuse

5 the unit tests build their netlists as hand-written strings, and 20 of
them describe designs `mosbius route` would reject. Investigated
2026-08-28; the numbers below are measured, not estimated.

57 of 271 tests embed a `mosbius_*` device line, and they split in two.
37 are error-path tests -- a reversed drain/source, a tail with three
matching sources, a circuit that doesn't fit -- and those have to stay
hand-written, because the input is a deliberately broken circuit that no
committed schematic could reasonably carry. The other 20 are happy-path
"does this route to the right bits" tests, and those could read a real
xschem netlist instead.

**The gap worth closing first needs no fixtures at all.** `check_design`'s
B1 (exactly one bias generator) is an ERROR for any design using
`mosbius_nsink`/`psource`/`ntail`/`ptail`/`ota` without a `mosbius_bias`
block, and both `cli.py` and `watch.py` run `check_design` before routing.
The test strings mostly have no such block -- `test_route.py` has 16
bias-referenced device lines and no `mosbius_bias`, `test_netlist.py` 12
and none -- so those tests call `route()` underneath a gate the product
applies. The bits they assert are right; the composition is one the user
can never reach. Adding the missing line to the existing strings is a
ten-minute change and closes it. (Designs without a mirror are unaffected:
B1 is silent for a plain inverter, so the inverter, SR latch and ring
strings are already realistic.)

**Real netlists would work as fixtures if we go further.** All six
examples parse, route clean and reproduce their documented bitstreams
from `build/*.spice`, and the hand-written and real inverter netlists give
byte-identical bitstreams despite differing instance names (`nfeta_0`
against `XM1`) and the `**.subckt` markers. Cost is about 17 KB for all
six, mostly symbol bodies -- the inverter is 55 lines of which 13 are the
design block.

The dependency question that comes with it: committed fixtures do *not*
put xschem in pytest's path, they put staleness there instead. Two things
make that manageable. The netlists are byte-reproducible (no timestamps,
no version stamp), so a freshness check is a plain diff; and
`schematic_for_netlist()` already falls back to a same-named `.sch` under
`examples/`, so a fixture written with a container path resolves fine on
a host, which means `check_netlist_fresh()` works on fixtures and pytest
could assert one is not older than its schematic with no docker at all. A
CI job that re-netlists the six and diffs is the stronger version, and
would also be the fast route-only check that the monthly regression is
too slow to provide.

The argument against is worth keeping in view: a committed fixture is a
second copy of a generated file, which is the shape of the stale-netlist
bug this project already fixed once (see CLAUDE.md on netlisting twice).
The difference is that a fixture is declared to be a snapshot and has a
job policing it. Related to the question about combining the test suites
that the item above raises.

## Tooling and library

6 there will be various versions of mini mosbius (multiple pdks and multple chips). this might need tracking / handling in the tool.
ideally the same bitstreams will produce similiar results, but at least the routed spice will need to take intou account the pdk. and possible future versions of mosbius might have  a new feature that won't be available in older ones. we should be able to get a list of which chips the design is present on with the api

## Docs and user-facing text

7 check all the schematic texts

8 all user facing text will ultimately be in a separate file, for internationalisation and for easy re-writing of all messages

9 add limks for xschem viewer. doesn't work out of the box, need to be able to provide our custom library
