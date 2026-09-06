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

- nothing here has been near his silicon. `--verify` will not catch a wrong
  bit-to-function mapping either, only a broken chain, since it just shifts
  the same bits back out.

The wider question this came from is answered for now: every mini-MOSbius so
far is sky130A, so the PDK axis is still hypothetical, and
https://index.tinytapeout.com/index.json plus `<shuttle>.json` is how to ask
which chips carry a design.

3 settle what a bus row's `Cwire` is supposed to contain, then decide whether
tnt's committed numbers should change. `tools/extract_bus_caps.sh` measures a
row's total capacitance and gets 1.15x to 1.28x tnt's committed figures across
all twelve rows. Two separate things cause that, separated by re-extracting
`asw_matrix.mag` on its own with the same settings:

- **What is summed, worth about 1.11x.** The committed numbers count a row's
  coupling to other signal nets and leave out its capacitance to the rails and
  substrate. Excluding the rails from a fresh run of the same cell lands within
  4-6% of them, which is what identifies the difference. Since `Cwire` is
  written into the deck as a capacitor from the row *to VGND*, leaving the
  row's real capacitance to the rails out of it looks wrong.
- **Scope, worth only about 1.05x.** The matrix cell alone against the whole
  chip. This was assumed to be the whole story when Andrew's numbers were
  measured, and it is the smaller half.

Before changing anything, though, there is a prior question that neither number
answers. On tnt's `bus_A[1]`, 59% of the total is coupling to that row's own
crosspoint nodes -- and the generated library already models exactly those, as
one 43.19 fF `Ccpl` per switch. So a total that includes them, dropped into the
deck as `Cwire` as well, counts them twice. Both the committed numbers and the
new ones have this. Work out what `Cwire` is meant to be the total *of* first;
re-extracting is easy and cheap once that is decided.

The reason to bother: the ring simulates about 1.28x faster than the silicon it
was measured against, as if capacitance were short. `tools/run_ringo_measured_bitstream.sh`
re-runs the measured bitstream and is how any candidate answer gets tested. If
one closes that gap, both parts move onto extracted numbers and Andrew's stop
being scaled.

## Docs and user-facing text

4 check all the schematic texts

5 add limks for xschem viewer. doesn't work out of the box, need to be able to provide our custom library

6 overview of how the router works

7 can the name from the xschem make it to the pinout? so we'd see 'inverter input' if we'd labelled it

8 proof the readme
