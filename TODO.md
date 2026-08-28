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

15. finish the two new examples and put them in the library.
`examples/currentsource/` (a programmable current source and sink) and
`examples/otabuf/` (an OTA unity-gain follower) are committed, run end to
end, and are deliberately not listed in `examples/README.md` yet -- both
READMEs open by saying so. Promoting them means: a row each in that file's
index table, a job each in `.github/workflows/spice-regression.yml`
(currently four), and dropping the work-in-progress banners.

`examples/otabuf/` is the closer of the two. `examples/currentsource/`
still owes the analysis its own "Still to do" list asks for, and the
measurements exist -- they were taken on 2026-08-28 and are only written
down here, so fold them in before they rot. At ratio=2, ibias=100uA, the
psource leg swept 0 to 3.3V on its pin reads:

    0.0V 224.6uA   1.0V 216.7uA   1.65V 209.9uA   2.5V 195.2uA
    2.9V 178.5uA   3.0V 166.6uA   3.2V  83.0uA    3.3V   0.0uA

Three separate things in that column, and the example exists to explain
them. The gentle slope from 0 to 2.5V is finite output resistance --
12 uA/V, about 85 kOhm -- not a flat region: taking the mid-rail value as
nominal, the current is within 5% only between about 0.55V and 2.3V,
bounded at both ends. Above ~2.5V the PMOS leaves saturation and the slope
tears away, 57 uA/V to 3.0V and 555 uA/V beyond it, reaching zero at
VAPWR where there is no drain-source voltage left. And 209.9uA rather than
exactly 200 is the classic mirror error: the diode-connected reference
sits at |Vsd| ~ 0.8V while the slave at mid-rail sits at 1.65V, so the
slave passes more; the curve crosses 200uA right where the two match, at
about 2.5V.

The drawn and routed curves track within 0.5% until the knee, where the
routed one degrades slightly faster (-23% against -20.6% at 3.0V). Reading
the offset off the two curves, the routed leg behaves like the drawn one
at about 3.017V -- roughly 17mV at 165uA, implying on the order of 100 Ohm
of series resistance in the matrix and pad. That is arithmetic on two
measured curves rather than a measured resistance, and it is the same
lesson the other examples give from the other side: at DC the matrix costs
nothing until you are close to a rail, where the tens of millivolts it
eats are the difference between working and not.

Still genuinely unrun: the ratio 1-4 sweep (four netlist-and-route runs,
checking the spacing is even, which is the one measurement immune to the
demoboard's uncalibrated bias source) and the nested `dc` sweep over
`ibias_amps` for the family of curves.

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

