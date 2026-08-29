# todo

1 all user facing text will ultimately be in a separate file, for internationalisation and for easy re-writing of all messages

2 come up with some hardware in the loop test.

3 use haralds 50 nifty

4 try to get coverage of all devices

5 could we use the scope against simulation

6 could we use the rp2350's adc / dac / ibias control to do automatic hil testing

7 each new shuttle's mini mosbius will have pins tied to different lettered pcb pins

8 could the tool fetch the pinout to make it clearer what pins to connect to / routed to/ automatically label an xschem sch

9 there will be various versions of mini mosbius (multiple pdks and multple chips). this might need tracking / handling in the tool.
ideally the same bitstreams will produce similiar results, but at least the routed spice will need to take intou account the pdk. and possible future versions of mosbius might have  a new feature that won't be available in older ones. we should be able to get a list of which chips the design is present on with the api

10 make it easy for people to submit designs to the examples

11 document what VDPWR is actually for. Nowhere says that the FETs a user
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

12. check all the mosbius library symbols for cleanup

13. two simulation sweeps `examples/currentsource/` still owes, both
listed in its own "Still to do". The `ratio` 1-4 sweep is four netlist
and route runs rather than one deck, since `ratio` is a device property
that changes the bitstream; it checks the four currents come out evenly
spaced, which is the one measurement immune to the demoboard's
uncalibrated bias source. The nested `dc` sweep over `ibias_amps` is one
run and gives the family of curves.

Everything else in that item is done as of 2026-08-28: both examples are
listed in `examples/README.md`, both have a job in
`.github/workflows/spice-regression.yml` (six now, with
`tools/check_otabuf_sim.sh` and `tools/check_currentsource_sim.sh`), the
work-in-progress banners are gone, and the I-V sweep analysis that was
only written down here is folded into
`examples/currentsource/README.md`. One correction went with it: the
drawn-versus-routed voltage offset at the knee is 24.3 mV and about
150 Ohm, interpolated between sweep points, not the 17 mV and ~100 Ohm
the scratch note here had.

14. no example exercises mosbius_ptail. Its orientation was fixed on
2026-08-28 -- it had been drawn upside down, a PMOS with a ground symbol
under it, and its pin moved from (0,-40) to (0,+40) -- so nothing but the
test suite has ever placed one. A PMOS differential pair mirroring
`examples/diffamp/` would cover it, and would be the cheapest of the
example ideas that came out of that session.

15. the bench plans in the two new examples are written but unrun, and now
runnable: real silicon was programmed and read back on 2026-08-28. Both
READMEs carry an "On the bench" section. The valuable one is
`examples/currentsource/`'s ibias calibration sweep -- `program.py`'s
level-to-amps constant is marked approximate in its own source, and that
sweep turns it into a real number that every other analog measurement on
this chip depends on. Ratio linearity and slew-versus-tail are both ratio
measurements, so they survive the uncalibrated source and can be done
first.

16. look at combining the tests with the github tests and the spice regression and the AD3 tests. at
the moment I think they're all a bit separate. possiblity to reuse

17. `examples/srlatch/`'s as-drawn branch simulates a circuit the chip
cannot build. `XM5` and `XM6` land on diff-pair halves, whose geometry is
fixed in silicon at `w=4`; the sheet draws `w=1`. The router already says
so -- `WARNING -- XM5 and XM6 had their w=1 ignored: ndiffpair+ and
ndiffpair- have a fixed width` -- but the as-drawn deck goes on
simulating the `w=1` circuit, so for this one example "as drawn" is not
the ideal version of the same circuit, it is a different circuit with 4x
weaker write transistors.

This may also explain something the README and `tools/check_srlatch_sim.py`
both record as unexplained: `treset_routed` comes out *faster* than
`treset_drawn`, the opposite of the inverter's result, and
`check_srlatch_sim.py` declines to assert an ordering because of it. A
reset through a transistor four times weaker than the one on the chip
would do that. Worth measuring at `w=4` to find out.

Drawing `w=4` on those two devices is a one-character change each. What
makes it a decision rather than a fix is that it moves `treset_drawn`, a
published number, in the README, in `check_srlatch_sim.py`'s references
and in the monthly regression -- and it silences a router warning that is
currently doing its job, which is worth being deliberate about.


18. the unit tests build their netlists as hand-written strings, and 20 of
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

19. do a curve tracer experiement
