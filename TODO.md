# todo

Grouped by what kind of work an item is, and numbered from 1 straight
through the groups. As always, the numbering is rewritten whenever
anything is removed, so cite an item by describing it, not by its number.

## Bench and hardware in the loop

1 automatic hardware-in-the-loop testing. Eight scripts in `tools/` now
measure real silicon with an Analog Discovery -- inverter, ring, SR latch,
both diff amps, OTA follower, current source, and the ibias clamp -- and
each compares against the same design as drawn and as routed. What none of them
is, is automatic: every one asks a person to wire a rig and press Enter,
and nothing runs them on a schedule or checks the answers have not moved.
The RP2350's own ADC/DAC would remove the person for some of it. Note that
the demoboard here has no `analog_current_source`, so anything assuming
programmable bias will not run on this bench -- the bias has to come from a
supply through a series resistor, and which supply setting gives which
current is a lookup in `build/ibias_clamp.json`, not a calculation.
(This is the merge of two items that asked the same question twice: "come
up with some hardware in the loop test" and "could we use the rp2350's
adc / dac / ibias control to do automatic hil testing".)

2 do a curve tracer experiment. Scoped on 2026-08-29 but not built; the
analysis is worth keeping so it is not re-derived.

The hard part is not the sweep, it is that every FET terminal reaches its
pad through a crosspoint switch and a pad model -- together on the order of
150-200 Ohm, and voltage-dependent. For a current source that costs almost
nothing, which is why `examples/currentsource/` measured cleanly: a current
source is indifferent to what is in series with it. For a FET it is fatal,
because the resistance sits between the instrument and the drain, so the
Vds you set is not the Vds the device sees. At `w=1` the NMOS is W=10/L=0.5
and a few hundred microamps is tolerable; at `w=4` and Vgs=3.3 the drop is
hundreds of millivolts and the trace is substantially of the switch.

Three ways out; take the first and third. Compare against the routed deck
rather than the drawn one -- it already contains every switch and pad, so
no correction is needed and it fits the drawn/routed/measured framing the
other examples use. Stay at `w=1` and modest Vgs for anything to be called
"the transistor". And Kelvin-sense the drain on a second `ua` pin:
crosspoints are independent switches, so one terminal can close two and
bring the same node out on a pad carrying no current. Whether `route.py`
can express two `ua` pins on one net is unchecked.

Vg, Vd and Id do not fit in the AD3's two scope channels, so it needs two
passes over a deterministic sweep, or the gate taken from W1's setpoint at
+/-25 mV. `tools/measure_currentsource_ad3.py` already has the reusable
half: the differential shunt read, the common-mode zero check (-9.7 mV/V on
this instrument), the pin-servoing sweep, and `--mode background` for what
the pad node draws on its own (487 kOhm to the channel offset, ie the two
scope inputs).

3 measure the inverter's rise time on silicon. `examples/inverter/`'s
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

4 use haralds 50 nifty

5 finish the fallout of the model-binning fix. Four of the five
re-measures are done (2026-08-29); what is left is one design decision and
two stale tables.

The fix itself, and why it was needed, is in `examples/pdiffamp/README.md`
under "The model-binning bug this example found" and in CLAUDE.md's trap
list. Re-measured and updated, README and `tools/check_*_sim.py` reference
together: the inverter (`trise_drawn` 8.90 -> 8.16 ns, trip point 1.495 ->
1.605 V, gain -8.5 -> -14.79 V/V, and the 100 pF pair 88.43 -> 81.07 ns),
the ring (`freq_drawn` 2.083 -> 2.289 GHz), and the diff amp (base 1.985 ->
2.012 V, gains 18.22/19.08 -> 18.31/19.35). `examples/otabuf/` and
`examples/currentsource/` came back inside tolerance, as predicted, since
the OTA and mirror symbols size off `tail` and `ratio`, which collide with
nothing. Every as-routed number is unchanged.

`examples/pdiffamp/` was measured on silicon the same day and is fully
closed: 17.82 V/V fitted against 21.22 as drawn, a +18 mV input offset,
and gain flat with tail current, all taken on the corrected library from
the start.

The SR latch needed a design decision and got one the same day:
`examples/srlatch/`'s `XM5`/`XM6` are drawn `w=4` now, matching what
silicon builds, so its as-drawn branch sets again and `treset_drawn` is
1.77 ns against the routed 10.94 -- the ordering every other example
shows, and one the checker now asserts. The bitstream is byte-identical,
since there were never any width bits behind the old request. CI is green
across all seven examples.

Two tables were not re-run and say so on their own pages: the diff amp's
+-2/5/10/20/40 mV sweep (a one-off 13-level PWL deck, not the committed
testbench) and its figure. Rebuilding that deck is the work; the settled
table that `check_diffamp_sim.py` reproduces is the current source of
truth either way.

6 `examples/currentsource/` owes two simulation sweeps and one bench sweep,
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

7 make it easy for people to submit designs to the examples

## Tests and CI

8 look at combining the tests with the github tests and the spice regression and the AD3 tests. at
the moment I think they're all a bit separate. possiblity to reuse

9 the unit tests build their netlists as hand-written strings, and 20 of
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

10 put `.github/workflows/spice-regression.yml` back on its monthly
schedule. It was switched to run on every push on 2026-08-29, deliberately
and temporarily, because the examples are changing daily and a break is
worth hearing about the same day. It costs about five minutes per push --
the six jobs run in parallel, and most of each one is ngspice parsing
sky130A's model library rather than simulating anything. Flip it back once
the examples settle -- delete the bare `push:` trigger and the note above
it; the `schedule:` and `workflow_dispatch:` entries are still there
untouched.

## Tooling and library

11 `route_rail_net()` picks a `cfg_bus_pwr` tap without looking at the row
its `cfg_bus_short` will drag in on the other side, so which of two unrelated
failures you get depends on the order xschem happened to list the instances
in. Found 2026-08-29 while checking what `examples/pdiffamp/` would cover.

Any net that needs a rail *row* trips this -- which in practice means any FET
whose drain goes to a rail, i.e. every source follower, the most ordinary
buffer a beginner draws. (A source reaching a rail is free: it uses the
device's own `ctrl_*_source` tie and no row at all, which is why no example
had ever exercised a tap.)

There are only three VAPWR taps -- bus_A[4], bus_B[1], bus_B[6] -- and a
VAPWR net touching both bus sides has to sit on the same row number on both,
bridged by `cfg_bus_short`. bus_A[4] pairs with bus_B[4], which is bonded to
ua5; bus_B[1] pairs with bus_A[1], which is bonded to ua1. Only bus_B[6] /
bus_A[6] has neither end bonded. The router takes `usable[0]` on the side of
whichever touch came first, so on one PMOS-pair-plus-two-followers netlist it
picked bus_A[4] and the checker correctly reported `DANGEROUS -- ua[5]
shorted to VAPWR`, and with the two follower instances swapped it picked
bus_B[1] and died with `DOESN'T FIT -- bus_A[1] is needed by both 'ua1' and
'VAPWR'`. Same circuit, same devices, two different answers. VGND is the same
shape: taps at bus_A[2], bus_B[5], bus_A[6].

The fix is to score the tap by what the partner row costs -- prefer a row
free on both sides, which is the same rule `route_internal_net()` already
applies to two-sided nets -- rather than taking the lowest-numbered one. This
is the rail-row twin of the instance-order dependence
`_allocate_fets_by_constraint()` fixed for FET allocation on 2026-08-22.

12 there will be various versions of mini mosbius (multiple pdks and multple chips). this might need tracking / handling in the tool.
ideally the same bitstreams will produce similiar results, but at least the routed spice will need to take intou account the pdk. and possible future versions of mosbius might have  a new feature that won't be available in older ones. we should be able to get a list of which chips the design is present on with the api

13 the six `tools/plot_*_comparison.py` figures draw silicon in a green
that collides with the orange they draw "as routed" in. The dataviz
palette validator scores that adjacent pair at Delta E 4.5 for protanopes,
against a floor of 8, so the two series are not reliably separable for a
red-green colourblind reader; the blue/orange pair is fine.
`tools/plot_pdiffamp_comparison.py` already uses a purple (`#7d5bbe`)
that scores 18.9 against the same orange and passes every check. Swapping
the other five over is a one-constant change each plus a re-run, and until
it happens the figure set is inconsistent -- which is the only reason not
to have done it at the time.

14 check all the mosbius library symbols for cleanup

## Docs and user-facing text

15 all user facing text will ultimately be in a separate file, for internationalisation and for easy re-writing of all messages

16 document what VDPWR is actually for. Nowhere says that the FETs a user
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
