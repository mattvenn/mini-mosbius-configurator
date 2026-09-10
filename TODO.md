# todo

Grouped by what kind of work an item is, and numbered from 1 straight
through the groups. As always, the numbering is rewritten whenever
anything is removed, so cite an item by describing it, not by its number.

## Examples

1 make it easy for people to submit designs to the examples

## Tooling and library

2 three loose ends left over from supporting Andrew Kang's part
(`tt_um_mosbius`), which is otherwise done -- routing, bitstreams, pad
tables, programming, the as-routed SPICE model, the finger-count geometry
and the bulk tie all work on both parts, all seven examples route on his
part and have been measured on his silicon, and PARTS.md has every number
side by side with tnt's. None of these three blocks using the part.

- **Two committed scripts measure a circuit that exists nowhere.**
  `tools/ad3/measure_pfollower_ad3.py` and `measure_nfollower_ad3.py` were
  the one-shot silicon checks that confirmed the bulk difference before it
  was fixed, and their schematics lived in `build/pfollower/` and
  `build/nfollower/`, which is gitignored and has since been cleaned. Their
  own headers tell you to re-run `tools/regenerate_routed.sh`, which cannot
  work, because the schematic that script starts from is the file that is
  gone. Promote the followers to real examples or drop the scripts. Do not
  simply edit the scripts' hard-coded bitstreams: those are the provenance
  for a measurement that really happened on silicon, not build output.
- **`examples/otabuf/`'s input common-mode range on his part is tnt's,
  carried over rather than simulated.** The bulk correction of 2026-09-10
  makes that a weaker assumption than it was, because the low end of a
  common-mode range is a threshold and a threshold is what moved. Deriving
  it needs a DC sweep `tb_otabuf.sch` does not have; the same sweep would
  settle it on both parts at once. `sim_cmr` in
  `tools/ad3/measure_otabuf_ad3.py` is the constant, and its comment
  already says it is carried over.
- **`examples/inverter/`'s peak gain on his part is measured but never
  simulated**, so that README publishes a bare silicon number with no
  as-drawn or as-routed column beside it. tnt's inverter has the whole row.

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

5 add links for xschem viewer. doesn't work out of the box, need to be able to provide our custom library

6 overview of how the router works

7 can the name from the xschem make it to the pinout? so we'd see 'inverter input' if we'd labelled it

8 proof the readme. One thing already found: the two differential
amplifier READMEs publish a "small-signal gain" without saying what it is
the slope of, and the four rows involved use three different definitions.
The testbench settles the output at three input levels, so three lines can
be drawn through them -- base to the positive endpoint, base to the
negative endpoint, and the symmetric one across the whole step -- and the
transfer curve bends enough that they differ by a few percent. `pdiffamp`'s
tnt row is the symmetric one, its Kang row is the positive half, and both
of `diffamp`'s rows are the negative half, which puts that table 2.6% away
from its own figure, whose legend computes the symmetric one. Pick the
symmetric chord, say so in both tables, and re-publish the two tnt numbers
that move.
