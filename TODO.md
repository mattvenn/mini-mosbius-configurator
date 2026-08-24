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
