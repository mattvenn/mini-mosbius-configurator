# todo

Grouped by what kind of work an item is, and numbered from 1 straight
through the groups. As always, the numbering is rewritten whenever
anything is removed, so cite an item by describing it, not by its number.

## Examples

1 make it easy for people to submit designs to the examples

## Tooling and library

2 finish supporting Andrew Kang's mini-MOSbius (tt_um_mosbius), alongside
tnt's. Routing, bitstreams, pad tables, programming and the as-routed SPICE
model all work on both parts; `MOSBIUS_PROJECT` in the environment picks
which, `--project` overrides it per command, and an unmapped macro stops
rather than guessing. Every example -- inverter, ring, diff amp, PMOS diff
amp, OTA follower, current source, SR latch -- routes on his part and has
now been measured on his silicon; PARTS.md has every number side by side
with tnt's.

What is left is the as-drawn ideal library's one remaining device
difference. The finger-count half of the geometry question is done and a
no-op for tnt (CLAUDE.md has the binning investigation); this is the
other half, and neither piece below needs a chip:

- **The PMOS bulk tie.** His generic PMOS and PMOS differential-pair
  halves tie bulk to their own source; tnt's tie every PMOS bulk to VAPWR.
  Every other PMOS on both parts already has its source on the rail, so
  this only bites a PMOS whose source moves with the signal -- negligible
  on a differential pair's shared source (1.9% of gain, 4.8 mV on
  `examples/pdiffamp/`), but about 20% low on a PMOS source follower drawn
  with the bulk on the rail instead of the source. Nothing in the examples
  draws that circuit yet. Shape of the fix, from CLAUDE.md: an internal
  well node in `mosbius_pmos`, tied to the rail through one resistor and
  to the source through another, both values from the `Chip` alongside
  the width per finger.

- **The NMOS bulk, unsettled.** This used to assume his NMOS schematics
  tie bulk to source too but that there is no deep nwell anywhere in his
  layout, so the bulk is really the substrate and the two parts agree.
  His top-level layout does contain three deep-nwell rectangles, and at
  least three NMOS placements fall inside them. Check that before relying
  on it.

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
