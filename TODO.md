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

The as-drawn ideal library's one device difference from real silicon --
the bulk tie -- is fixed as of 2026-09-10, for both PMOS and NMOS, both
confirmed on silicon first. The finger-count half of the geometry question
was already done and a no-op for tnt (CLAUDE.md has the binning
investigation); this was the other half.

**What was wrong.** His generic PMOS/PMOS differential-pair halves tie
bulk to their own source; tnt's tie every PMOS bulk to VAPWR. `diff_n.sch`
(NMOS pair, `itail`) and `ota_n.sch` (NMOS input pair) do the same on the
NMOS side. Both need deep-nwell isolation to be physically real, and
`tt_um_mosbius.mag` has it: four top-level `dnwell` rectangles, with
several `sky130_fd_pr__nfet_g5v0d10v5_*` instances sitting fully inside
them. Every PMOS/NMOS whose source never leaves a rail is unaffected --
`mirror_n`'s tail bank, the bias mirror legs, `tt_asw_3v3`'s pass-FETs,
and every existing example except a diff-pair/OTA input pair (a small
effect, 1.9% of gain / 4.8 mV on `examples/pdiffamp/`, from the shared
source acting as a virtual ground). A source follower is where it bites
hard, and nothing in the examples drew one, so two one-shot circuits did
(not committed examples -- `build/pfollower/`, `build/nfollower/`,
`tools/ad3/measure_pfollower_ad3.py`, `measure_nfollower_ad3.py`):
0.921 V/V measured on `tt_um_mosbius` silicon against 0.918 V/V simulated
as routed (0.3% off) and 0.746 V/V as drawn (19% off) for PMOS; 0.924
against 0.929 routed (0.5% off) and 0.789 drawn (13.5% off) for NMOS.
`mosbius simulate`'s switch-matrix model already had this right in both
cases, since it comes from Andrew Kang's own extracted device library --
only the ideal library was wrong.

**The fix.** `mosbius_pmos.sch`/`mosbius_nmos.sch` each gained an internal
`well` node: the FET's `body=` now points there instead of straight at the
rail, and two resistors (`Rwell_rail`, `Rwell_source`) connect `well` to
the rail and to the device's own drawn source. Both resistor values are
`.param`s driven by a new `Chip.bulk_follows_source` field (False for tnt,
True for Kang), written into the generated routed netlist by
`mosbius/simulate.py`'s `render_drawn_geometry()` -- the exact mechanism
`pmos_width_per_finger` already uses, so `--project` stays the one place a
part is chosen. One trap on the way: the first resistor values (1e-12/1e12
ohm, mirroring `CONFIG_TIE_OHMS`'s near-zero convention) made ngspice hang
for 50+ minutes at ~100% CPU instead of the usual ~2-minute model load --
a 24-decade spread on one internal node, with 1e-12 sitting on top of
ngspice's own default `gmin`, is a much harder linear-algebra problem than
a single tie to a fixed rail. 1 ohm / 1e9 ohm (nine decades, comfortably
past the stiffest real node in these decks, ~50 kOhm) fixed it and reran
in seconds. `BULK_TIE_OHMS`/`BULK_OPEN_OHMS` in `mosbius/simulate.py`.

**Verified.** All 382 pytest tests pass. Every tnt example with a
published number (inverter, diff amp, PMOS diff amp, SR latch, OTA
follower, current source, ring oscillator) matches its README exactly --
confirms the fix is a true no-op for tnt, not just in the resistor math
but in the actual regression. Both one-shot followers moved from
15-19% off the as-routed/silicon numbers to within ~1.5%. `examples/pdiffamp`
on `tt_um_mosbius` shifted about 2% (21.6->21.1, 20.8->20.5 V/V), matching
the virtual-ground-cancellation size predicted above rather than the
follower's much larger shift.

**Left:** `examples/diffamp` (the NMOS pair) on `tt_um_mosbius` hasn't
been re-simulated with the fix yet. Kang's `pdiffamp`/`diffamp` READMEs
still publish the old as-drawn numbers and need updating once diffamp is
checked too. `build/pfollower/`/`build/nfollower/` are still one-shot,
uncommitted, gitignored -- promote to real examples only if that's
wanted, since the silicon check was the point, not a permanent addition.

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

8 proof the readme
