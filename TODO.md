# todo

1 all user facing text will ultimately be in a separate file, for internationalisation and for easy re-writing of all messages

2 automatic hardware-in-the-loop testing. Seven scripts in `tools/` now
measure real silicon with an Analog Discovery -- inverter, ring, SR latch,
diff amp, OTA follower, current source, and the ibias clamp -- and each
compares against the same design as drawn and as routed. What none of them
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

3 use haralds 50 nifty

4 try to get coverage of all devices

5 automatically label an xschem sheet with the PCB pad letters. The lookup
half is done as of 2026-08-29: `mosbius/pads.py` composes the shuttle
index's `analog_pins` with the carrier's own wiring, and
`format_analog_header()` draws the ANALOG header with the pads in use
bracketed, which `mosbius program` and five of the measurement scripts
print. What is not done is putting those letters onto the schematic itself,
so a sheet says "ua2 (pad J)" beside the pin rather than making the reader
run a command to find out.

Two items are closed by work already done and have been dropped rather
than renumbered: "each new shuttle's mini mosbius will have pins tied to
different lettered pcb pins", which `pad_map()` handles by composing the
index with the carrier table; and "could we use the scope against
simulation", which is what the seven measurement scripts in item 2 do,
every one of them against the same design as drawn and as routed.

6 there will be various versions of mini mosbius (multiple pdks and multple chips). this might need tracking / handling in the tool.
ideally the same bitstreams will produce similiar results, but at least the routed spice will need to take intou account the pdk. and possible future versions of mosbius might have  a new feature that won't be available in older ones. we should be able to get a list of which chips the design is present on with the api

7 make it easy for people to submit designs to the examples

8 document what VDPWR is actually for. Nowhere says that the FETs a user
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

9 check all the mosbius library symbols for cleanup

10 `examples/currentsource/` owes two simulation sweeps and one bench sweep,
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
sweep that item 15 called "the valuable one" was run on 2026-08-29; and
otabuf's slew-versus-tail was run the same day.

11 no example exercises mosbius_ptail. Its orientation was fixed on
2026-08-28 -- it had been drawn upside down, a PMOS with a ground symbol
under it, and its pin moved from (0,-40) to (0,+40) -- so nothing but the
test suite has ever placed one. A PMOS differential pair mirroring
`examples/diffamp/` would cover it, and would be the cheapest of the
example ideas that came out of that session.

12 look at combining the tests with the github tests and the spice regression and the AD3 tests. at
the moment I think they're all a bit separate. possiblity to reuse

13 `examples/srlatch/`'s as-drawn branch simulates a circuit the chip
cannot build. `XM5` and `XM6` land on diff-pair halves, whose geometry is
fixed in silicon at `w=4`; the sheet draws `w=1`. The router already says
so -- `WARNING -- XM5 and XM6 had their w=1 ignored: ndiffpair+ and
ndiffpair- have a fixed width` -- but the as-drawn deck goes on
simulating the `w=1` circuit, so for this one example "as drawn" is not
the ideal version of the same circuit, it is a different circuit with 4x
weaker write transistors.

This explained something the README and `tools/check_srlatch_sim.py` both
recorded as unexplained, and that half is now closed (measured
2026-08-29): `treset_routed` came out *faster* than `treset_drawn`, the
opposite of the inverter's result, and the cause is exactly this width
mismatch. Widen `XM5`/`XM6` to `w=4` and the sheet's own deck gives
`treset_drawn` = 1.82 ns against the routed 10.94 ns, the ordering every
other example shows. Under the bench's own 20 ns stimulus edge at `ss`
(`sh tools/run_srlatch_measured_edge.sh ss --drawn-w4`) the same change
takes as-drawn from 40.70 ns to 9.07 ns, against 21.30 ns as routed and
24.46 ns measured on silicon. So nearly all of the as-drawn deck's error
was this one discrepancy. Both READMEs and `check_srlatch_sim.py` now say
so.

What is left is only the decision. Drawing `w=4` on those two devices is a
one-character change each, and it would make the as-drawn branch simulate
the circuit the chip actually builds. Against that: it moves
`treset_drawn`, a published number, in `examples/srlatch/README.md`, in
`check_srlatch_sim.py`'s references and in the monthly regression -- and
it silences a router warning that is currently doing its job, which is
worth being deliberate about.

14 the unit tests build their netlists as hand-written strings, and 20 of
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

15 do a curve tracer experiment. Scoped on 2026-08-29 but not built; the
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

16 put `.github/workflows/spice-regression.yml` back on its monthly
schedule. It was switched to run on every push on 2026-08-29, deliberately
and temporarily, because the examples are changing daily and a break is
worth hearing about the same day. It costs about five minutes per push --
the six jobs run in parallel, and most of each one is ngspice parsing
sky130A's model library rather than simulating anything. Flip it back once
the examples settle -- delete the bare `push:` trigger and the note above
it; the `schedule:` and `workflow_dispatch:` entries are still there
untouched.
