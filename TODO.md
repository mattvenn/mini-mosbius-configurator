# todo

1 all user facing text will ultimately be in a separate file, for internationalisation and for easy re-writing of all messages

2 with watch argument, ctrl c is the most likely way to end it, which prints a messy error

3 come up with some hardware in the loop test.

4 use haralds 50 nifty

5 try to get coverage of all devices

6 could we use the scope against simulation

7 could we use the rp2350's adc / dac / ibias control to do automatic hil testing

8 each new shuttle's mini mosbius will have pins tied to different lettered pcb pins

9 could the tool fetch the pinout to make it clearer what pins to connect to / routed to/ automatically label an xschem sch

10 fix messy error:  python3 -m mosbius.cli  decode build/ring.mosbius.json 
Traceback (most recent call last):
  File "<frozen runpy>", line 203, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "/Users/mattvenn/asic/mini-mosbius-configurator/mosbius/cli.py", line 197, in <module>

11 .github/workflows/spice-regression.yml checks the inverter (trise_drawn/trise_routed
   within 25% of examples/inverter/README.md's reference numbers), once a month plus
   workflow_dispatch. Still to add: the ring oscillator's frequency within bounds.

12 tb_diffamp: all four gain_* measures report failed even though ngspice
computes the number

- log shows `meas tran gain_drawn_pos param=7.761175e+00 failed!` -- the value
  is right there, the measure just also sets a failure status

- affects gain_drawn_pos, gain_drawn_neg, gain_routed_pos, gain_routed_neg

- looks like ngspice's `.meas ... PARAM=` returning a result but flagging
  failure; the vout_* measures it derives from all succeed

- pre-existing, not caused by the rshunt -> Vgnd change: the same four measures
  fail identically in runs before and after it (the computed values shift in the
  last digits, as every measure in every deck does) (2026-08-24), and
  unchanged by the 100pF -> 10pF load change (2026-08-27)

13 there will be various versions of mini mosbius (multiple pdks and multple chips). this might need tracking / handling in the tool.
ideally the same bitstreams will produce similiar results, but at least the routed spice will need to take intou account the pdk. and possible future versions of mosbius might have  a new feature that won't be available in older ones. we should be able to get a list of which chips the design is present on with the api
