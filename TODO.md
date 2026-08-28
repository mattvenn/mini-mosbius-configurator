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

14. check all the mosbius library symbols for cleanup

15. two simulation sweeps `examples/currentsource/` still owes, both
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

16. no example exercises mosbius_ptail. Its orientation was fixed on
2026-08-28 -- it had been drawn upside down, a PMOS with a ground symbol
under it, and its pin moved from (0,-40) to (0,+40) -- so nothing but the
test suite has ever placed one. A PMOS differential pair mirroring
`examples/diffamp/` would cover it, and would be the cheapest of the
example ideas that came out of that session.

17. the bench plans in the two new examples are written but unrun, and now
runnable: real silicon was programmed and read back on 2026-08-28. Both
READMEs carry an "On the bench" section. The valuable one is
`examples/currentsource/`'s ibias calibration sweep -- `program.py`'s
level-to-amps constant is marked approximate in its own source, and that
sweep turns it into a real number that every other analog measurement on
this chip depends on. Ratio linearity and slew-versus-tail are both ratio
measurements, so they survive the uncalibrated source and can be done
first.

18. look at combining the tests with the github tests and the spice regression and the AD3 tests. at
the moment I think they're all a bit separate. possiblity to reuse
