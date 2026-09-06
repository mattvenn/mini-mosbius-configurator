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

- his decks are about 35% slower than tnt's, and it is worth knowing why
  before anyone runs a long transient on one. On a 661-point DC sweep of the
  inverter: 30.4s against 22.5s wall, of which the load and first operating
  point are 21.5s against 20.0s, so the sweep itself is ~9s against ~2.5s.
  The extra time is the transient-operating-point fallback firing repeatedly,
  not deck size -- his deck is only 2-3% bigger.

- ngspice emits six singular-matrix warnings on his decks, always naming
  `bus_A[6]`, and recovers. Two explanations were tested and both disproved:
  a pad model on all five package pins, and a 1 TOhm DC path on every bus
  row, each leave the count at six and the trip point unmoved to within
  20 uV. So it is neither the switched package pins nor a floating row.
  `bus_A[6]` is the one row no package pin can ever reach on his part -- 13
  switches against 14 on the rows either side -- so ngspice naming it is not
  a coincidence, but being least-connected is not the same as being what the
  solver is stuck on. Mechanism unknown; it costs time, not accuracy.

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
