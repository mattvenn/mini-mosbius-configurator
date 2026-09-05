# todo

Grouped by what kind of work an item is, and numbered from 1 straight
through the groups. As always, the numbering is rewritten whenever
anything is removed, so cite an item by describing it, not by its number.

## Examples

1 make it easy for people to submit designs to the examples

## Tooling and library

2 finish supporting Andrew Kang's mini-MOSbius (tt_um_mosbius), alongside
tnt's. Routing, bitstreams, pad tables and programming all work on both parts
now; `--project` picks which. What is left:

- an as-routed SPICE library for his part. His repo commits the netlist, so
  no docker or layout step is needed, but the plumbing is not mechanical: his
  `bus_A[k]` ports are the package pins and the bus rows are `bus_A_int[k]`,
  which is not a port at all, so simulate.py cannot attach the bus-wire
  capacitance the way it does for tnt.
- one ideal symbol library covering both. Every device has the same width and
  length and the same slice values on both parts; the whole geometry
  difference is that every PMOS on his part has 1.5x the fingers. So a
  per-chip parameter include, not a second library. Check first whether the
  finger count moves the sky130 model bin (trap 10's failure mode). His PMOS
  bulk goes to its own source where tnt's goes to VAPWR, which only matters
  when a PMOS source is off the rail; his NMOS schematics say the same but
  there is no deep nwell in his layout, so that bulk is the substrate and the
  two parts agree.
- the examples, re-routed and published for his part. Six of the seven route
  today. The ring oscillator does not, and that is a real constraint of his
  chip rather than a router failure: its three package pins land on rows 1-3,
  the only rows a differential pair's gate can reach. Naming its pins ua3,
  ua4 and ua5 instead would leave rows 1 and 2 free.
- his bus-wire capacitance is tnt's numbers reused as a stated estimate.
  Nobody has run PEX on his layout.

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
