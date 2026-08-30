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

6 put `.github/workflows/spice-regression.yml` back on its monthly
schedule. It was switched to run on every push on 2026-08-29, deliberately
and temporarily, because the examples are changing daily and a break is
worth hearing about the same day. It costs about five minutes per push --
the six jobs run in parallel, and most of each one is ngspice parsing
sky130A's model library rather than simulating anything. Flip it back once
the examples settle -- delete the bare `push:` trigger and the note above
it; the `schedule:` and `workflow_dispatch:` entries are still there
untouched.

## Tooling and library

7 which hardware slot a FET gets still decides whether an ordinary
circuit fits, because the slot fixes which bus side each terminal is on.
Found 2026-08-30, as the residue of the two routing-order fixes made the
same day (a rail tap now scores its bridge, and nets now route in order of
how little choice they have). Those two took a PMOS-pair-plus-two-followers
netlist from 0 clean orderings out of 120 to 90; this is the other 30.

The contention is for bus row 6. It is the only row with no ua[] bond wire
on either side (`ROWS_FREE_ON_BOTH_SIDES`, derived from the pin map), so it
is the only row *any* net spanning both bus sides can use -- rail or
internal, and there is one of it. Whether a given net spans both sides is
not a property of the schematic: it follows from which slot
`allocate_devices()` handed each FET. Two source followers plus an inverter
routes in 3 of its 6 orderings; in the other 3 the allocation makes VAPWR
two-sided, it takes row 6, and the internal net that also needs row 6 gets
`DOESN'T FIT -- 'outa' needs a free row on both sides, joined`.

`_allocate_fets_by_constraint()` already searches orderings, but it scores
only for diff-pair gates on two-sided nets and out-of-range package pins
(2026-08-22). Adding "and don't make a net two-sided when row 6 is already
spoken for" is the same shape of constraint and the same search. The
honest alternative is to say the router is greedy and leave it, since the
message names the net and the rule; but a source follower plus an inverter
is not an exotic circuit to be told to reorder by hand.

8 there will be various versions of mini mosbius (multiple pdks and multple chips). this might need tracking / handling in the tool.
ideally the same bitstreams will produce similiar results, but at least the routed spice will need to take intou account the pdk. and possible future versions of mosbius might have  a new feature that won't be available in older ones. we should be able to get a list of which chips the design is present on with the api

9 the six `tools/plot_*_comparison.py` figures draw silicon in a green
that collides with the orange they draw "as routed" in. The dataviz
palette validator scores that adjacent pair at Delta E 4.5 for protanopes,
against a floor of 8, so the two series are not reliably separable for a
red-green colourblind reader; the blue/orange pair is fine.
`tools/plot_pdiffamp_comparison.py` already uses a purple (`#7d5bbe`)
that scores 18.9 against the same orange and passes every check. Swapping
the other five over is a one-constant change each plus a re-run, and until
it happens the figure set is inconsistent -- which is the only reason not
to have done it at the time.

10 check all the schematic texts

## Docs and user-facing text

11 all user facing text will ultimately be in a separate file, for internationalisation and for easy re-writing of all messages

12 document what VDPWR is actually for. Nowhere says that the FETs a user
draws never see 1.8V: every analog device in the submodule (nmos_prog,
pmos_prog, diff_n/p, mirror_n/p, ota_n) is g5v0d10v5 with its body on
VAPWR, so the whole analog half runs at 3.3V. VDPWR reaches only
tt_asw_3v3, whose 01v8/01v8_hvt pair is the level shifter that turns a
1.8V config bit into a 3.3V pass-gate drive -- spice.py ties all 192
config pins to VDPWR/VGND, so without that rail a routed design is 192
open switches. It is also a dead port in the as-drawn instance: a design
built from mosbius_* symbols never connects it. So it powers nothing you
draw, and exists so the matrix can be told what to be. Belongs in
TUTORIAL.md, and probably as a line in the mini_mosbius.sym pin table.

13 add limks for xschem viewer. doesn't work out of the box, need to be able to provide our custom library
