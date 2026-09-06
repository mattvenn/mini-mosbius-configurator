# todo

Grouped by what kind of work an item is, and numbered from 1 straight
through the groups. As always, the numbering is rewritten whenever
anything is removed, so cite an item by describing it, not by its number.

## Examples

1 make it easy for people to submit designs to the examples

## Tooling and library

2 finish supporting Andrew Kang's mini-MOSbius (tt_um_mosbius), alongside
tnt's. Routing, bitstreams, pad tables, programming and the as-routed SPICE
model all work on both parts now; `MOSBIUS_PROJECT` in the environment picks
which, `--project` overrides it per command, and an unmapped macro stops
rather than guessing. The same inverter schematic routed onto each
part and simulated agrees to 2 mV of trip point, and tnt's side still
reproduces its published 1.600 V exactly.

The binning question is answered and the ideal symbol library now covers
both parts, through one parameter rather than two libraries (first bullet).
What is left is the examples and the bench. The bullets below can be done in
any order, and none of it needs a chip except the last one.

What is left:

- one ideal symbol library covering both, for the as-drawn side. The finger
  count half of this is done; the PMOS bulk is not, and is the last piece.
  Every device has the same width and length and the same slice values on
  both parts; the whole geometry difference is that every PMOS on his part
  has 1.5x the fingers, at the same total width. So width per finger is 5 um
  on his part against 7.5 um on tnt's, and every PMOS width in use is 30, 60
  or 120, so both divide exactly.

  **The binning question is settled: finger count does not move the bin**
  (2026-09-06). `build/bintest_pmos_fingers.spice`, built on the
  `build/bintest3.spice` shape that settled trap 10, diode-connects a
  `sky130_fd_pr__pfet_g5v0d10v5` at each of the three PMOS widths in use and
  compares tnt's finger count against his at the same current: W=30 nf=4
  against nf=6, W=60 nf=8 against nf=12, W=120 nf=16 against nf=24. Every one
  of the six selects `phv_model.7`, and |Vsg| at the bias current differs by
  1.18 mV (1.2667 V against 1.2655 V, 0.09%), with 1.4 mV between the two
  thresholds. That residue is BSIM4's narrow-width terms seeing a different
  per-finger effective width, not a different model card.

  The PDK says why, and it generalises past these three widths: the model
  file's `.subckt sky130_fd_pr__pfet_g5v0d10v5` hands the binned `phv_model`
  the instance's *total* `w` and `l`, with `nf` alongside as an ordinary
  BSIM4 instance parameter, so nf is not an input to bin selection at all.
  Every bin in that file carries `wmin = 2E-5 wmax = 1.01E-3`, i.e. one
  width bin from 20 um to 1.01 mm covering every width either part uses --
  the binning is on length. So no PMOS geometry difference of this kind can
  put the two parts in different bins.

  **Done 2026-09-06: the geometry is one parameter,
  `pmos_width_per_finger`, and `--project` is the only place a part is
  named.** It is a `Chip` field, and `mosbius simulate` writes it into the
  routed netlist it generates as a global `.param` above the `.subckt`. A
  testbench includes that netlist at the top level, so the parameter reaches
  the ideal symbols on the design sheet too and the as-drawn half follows the
  part the design was routed for, with nothing on the testbench naming a
  part. Five device sheets divide a literal total width by it: `mosbius_pmos`
  (inside the `wdev`/`nfdev` code block, because `w` collides with sky130's
  own parameter -- trap 10), `mosbius_psource`, `mosbius_ptail`,
  `mosbius_ota` (two PMOS) and `mosbius_bias` (one). The NMOS sheets are
  untouched. `tests/test_geometry.py` guards it and `examples/README.md`
  gained a "Which part" section.

  A per-testbench `GEOMETRY` block with committed `geometry_<part>.spice`
  files was built first and removed the same day, because it made the part a
  second thing to set and let a sheet disagree with the netlist beside it.
  See CLAUDE.md; don't re-propose it.

  For tnt it is exactly a no-op, checked rather than argued.
  `build/nfcheck.spice` prints every old literal finger count minus its new
  expression at 7.5 um and every difference is 0 -- 30, 60 and 120 all
  divide exactly -- and all seven examples re-simulate to their published
  numbers. The other part was exercised end to end on `examples/pdiffamp/`.

  One thing found while confirming the 1.5x claim, worth not rediscovering:
  Andrew Kang's device library has five PMOS his part has and tnt's does
  not (`diff_p` W=20 nf=4, `mirror_p` W=40 nf=8 and W=5 nf=1, `ota_n`
  W=20 nf=4, `pmos_prog` W=20 nf=4). Every one has drain, gate, source and
  bulk on the same node, so they are dummies and change nothing
  electrically. The active devices do line up 1.5x for 1.5x, and the pad
  mux is identical on both parts at W=180 nf=18, so "every PMOS" means
  every PMOS in the ideal library, not every PMOS on the die.

  Still open, and the last piece of the shared library: his PMOS bulk goes to
  its own source where tnt's goes to VAPWR. It is his generic PMOS and his
  PMOS differential-pair halves only; every other PMOS on both parts has its
  source on the rail, so the bulk lands in the same place. Measured sizes and
  the shape of the fix (an internal well node with two resistors, values from
  the `Chip`) are in CLAUDE.md. Short version: 1.9% of gain and 4.8 mV on
  `examples/pdiffamp/`, which is inside the checkers' tolerance, but about
  20% on a PMOS source follower, which is not. The as-routed side is already
  correct, so leaving it puts an artifact into his drawn-versus-routed
  comparison that is not the switch matrix.

  The NMOS half of that claim is NOT settled. This list used to say his NMOS
  schematics tie bulk to source too but that there is no deep nwell anywhere
  in his layout, so the bulk is really the substrate and the two parts agree.
  His top-level layout does contain three deep-nwell rectangles, and at least
  three NMOS placements fall inside them. Check that before relying on it.

- the examples, re-routed and published for his part. Five of the seven route
  as drawn, and neither refusal is a router failure:
  * the ring oscillator's three package pins land on rows 1-3, the only rows
    a differential pair's gate can reach, leaving none for the internal net
    that also needs one. Naming its pins ua3, ua4 and ua5 would free rows 1
    and 2.
  * the OTA buffer probes the OTA's diode-connected node, which his part
    keeps internal. Dropping that one wire routes it, and the diagnostic
    says so.

  The toolchain side of this is done: `MOSBIUS_PROJECT` sets which part every
  command and the testbench's own button assume, the routed JSON records the
  part it was routed for, and both the sticky router and `mosbius simulate`
  refuse to mix parts. See CLAUDE.md.

- the example numbers for his part need re-measuring. Every one of them was
  produced with `ctrl_otan_diode` floating, which is the bug that made his
  decks emit singular-matrix warnings and run five times slow, and fixing it
  moves the answer a little: on a 67-point sweep of the inverter the trip
  point reads 1.5996 V where the floating pin gave 1.5988 V.

- nothing here has been near his silicon. `--verify` will not catch a wrong
  bit-to-function mapping either, only a broken chain, since it just shifts
  the same bits back out. This needs no new hardware: his macro is on the same
  ttsky25a chip as tnt's, at address 490 against 239, so the demoboard already
  used for every measurement in this repo can program it. Do the simulation
  work above first -- bench time is the scarce thing, and a session is worth
  having only if every example is already routed with a predicted number to
  disagree with. That is what pinned the corner on tnt's part.

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
