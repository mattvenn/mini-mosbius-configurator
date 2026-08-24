# todo

1 sim directory is still wrong

2 if no mosbius spice, then tb fails to netlist

3 all user facing text will ultimately be in a separate file, for internationalisation and for easy re-writing of all messages

4 with watch argument, ctrl c is the most likely way to end it, which prints a messy error

5 fix up tb_template

6 come up with some hardware in the loop test.

- use haralds 50 nifty

- try to get coverage of all devices

- could we use the scope against simulation

- could we use the rp2350's adc / dac / ibias control to do automatic hil testing

7 each new shuttle's mini mosbius will have pins tied to different lettered pcb pins

- could the tool fetch the pinout to make it clearer what pins to connect to / routed to/ automatically label an xschem sch

8 fix messy error:  python3 -m mosbius.cli  decode build/ring.mosbius.json 
Traceback (most recent call last):
  File "<frozen runpy>", line 203, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "/Users/mattvenn/asic/mini-mosbius-configurator/mosbius/cli.py", line 197, in <module>

9 as drawn has no pad loading. routed hides it. also I forgot the analog muxes on all the io pins

10 .github/workflows/spice-regression.yml checks the inverter (trise_drawn/trise_routed
   within 25% of examples/inverter/README.md's reference numbers), once a month plus
   workflow_dispatch. Still to add: the ring oscillator's frequency within bounds.

11 tb_diffamp: all four gain_* measures report failed even though ngspice
computes the number

- log shows `meas tran gain_drawn_pos param=9.596000e-01 failed!` -- the value
  is right there, the measure just also sets a failure status

- affects gain_drawn_pos, gain_drawn_neg, gain_routed_pos, gain_routed_neg

- looks like ngspice's `.meas ... PARAM=` returning a result but flagging
  failure; the vout_* measures it derives from all succeed

- pre-existing, not caused by the rshunt -> Vgnd change: the same four measures
  fail identically in runs before and after it (the computed values shift in the
  last digits, as every measure in every deck does) (2026-08-24)

12 tb_srlatch: treset_drawn / treset_routed never measure

- `Error: measure treset_drawn trig(TARG) : out of interval` -- the TARG edge
  (v(out_drawn) falling through 1.65) is not found inside the 400n window, so
  the reset propagation delay is never reported

- the qd_/qr_after_set and after_reset FIND measures in the same deck are fine,
  so the latch itself is switching; it is the delay measure that is mis-set up

- pre-existing, same before and after the rshunt -> Vgnd change (2026-08-24)
