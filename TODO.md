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
