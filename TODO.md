# todo

Grouped by what kind of work an item is, and numbered from 1 straight
through the groups. As always, the numbering is rewritten whenever
anything is removed, so cite an item by describing it, not by its number.

## Examples

1 make it easy for people to submit designs to the examples

## Tooling and library

2 finish supporting Andrew Kang's mini-MOSbius (tt_um_mosbius), alongside
tnt's. Routing, bitstreams, pad tables, programming and the as-routed SPICE
model all work on both parts now; `--project` picks which, and an unmapped
macro stops rather than guessing. The same inverter schematic routed onto each
part and simulated agrees to 2 mV of trip point, and tnt's side still
reproduces its published 1.600 V exactly. What is left:

- one ideal symbol library covering both, for the as-drawn side. Every device
  has the same width and length and the same slice values on both parts; the
  whole geometry difference is that every PMOS on his part has 1.5x the
  fingers. So a per-chip parameter include, not a second library. Check first
  whether the finger count moves the sky130 model bin, which is trap 10's
  failure mode. His PMOS bulk goes to its own source where tnt's goes to
  VAPWR, which only matters when a PMOS source is off the rail; his NMOS
  schematics say the same but there is no deep nwell anywhere in his layout,
  so that bulk is the substrate and the two parts agree.

- the examples, re-routed and published for his part. Five of the seven route
  as drawn, and neither refusal is a router failure:
  * the ring oscillator's three package pins land on rows 1-3, the only rows
    a differential pair's gate can reach, leaving none for the internal net
    that also needs one. Naming its pins ua3, ua4 and ua5 would free rows 1
    and 2.
  * the OTA buffer probes the OTA's diode-connected node, which his part
    keeps internal. Dropping that one wire routes it, and the diagnostic
    says so.

- the example numbers for his part need re-measuring. Every one of them was
  produced with `ctrl_otan_diode` floating, which is the bug that made his
  decks emit singular-matrix warnings and run five times slow, and fixing it
  moves the answer a little: on a 67-point sweep of the inverter the trip
  point reads 1.5996 V where the floating pin gave 1.5988 V.

- his bus-wire capacitance and the 43.19 fF row-coupling figure are tnt's
  extracted numbers reused, and the generated library says so. Nobody has run
  PEX on his layout.

- nothing here has been near his silicon. `--verify` will not catch a wrong
  bit-to-function mapping either, only a broken chain, since it just shifts
  the same bits back out.

The wider question this came from is answered for now: every mini-MOSbius so
far is sky130A, so the PDK axis is still hypothetical, and
https://index.tinytapeout.com/index.json plus `<shuttle>.json` is how to ask
which chips carry a design.

## Docs and user-facing text

3 check all the schematic texts

4 add limks for xschem viewer. doesn't work out of the box, need to be able to provide our custom library

5 overview of how the router works

6 can the name from the xschem make it to the pinout? so we'd see 'inverter input' if we'd labelled it

7 proof the readme
