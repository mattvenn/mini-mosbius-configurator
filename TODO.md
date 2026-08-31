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

## Examples

2 `examples/currentsource/` owes two simulation sweeps and one bench sweep,
all three about `ratio`.

In simulation, both are listed in its own "Still to do, in simulation". The
`ratio` 1-4 sweep is four netlist and route runs rather than one deck,
since `ratio` is a device property that changes the bitstream. The nested
`dc` sweep over `ibias_amps` is one run and gives the family of curves --
its measured counterpart is now done (7 points, 24-154 uA, giving
out = 1.9127 x in - 0.508 uA), so this is what that would be compared
against.

On the bench, ratio linearity is the last unrun experiment on that example,
and the only one immune to the demoboard's uncalibrated bias source, since
a ratio of two currents from the same reference cancels it. Everything
measured there so far was taken at `ratio=2`, and `ratio` and the bias
current enter the answer only as a product, so nothing yet confirms the
mirror-ratio bits mean what the bit map says.
`tools/measure_currentsource_ad3.py --mode ratio` takes the four routed
designs and reads each ratio back out of its own bitstream rather than its
filename.

The rest of what this item and the bench-plan item used to cover is done.
Both examples are in
`examples/README.md` and in `.github/workflows/spice-regression.yml`; the
I-V analysis is folded into the example's README (with the correction that
the drawn-versus-routed offset at the knee is 24.3 mV and about 150 Ohm,
not the 17 mV and ~100 Ohm a scratch note here had); the ibias calibration
sweep this list once called "the valuable one" was run on 2026-08-29; and
otabuf's slew-versus-tail was run the same day.

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
