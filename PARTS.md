# The two mini-MOSbius parts

There are two taped-out mini-MOSbius chips, same architecture, different
device geometry:

| | macro | title |
|---|---|---|
| tnt's | `tt_um_tnt_mosbius` | [tt_um_tnt_mosbius](https://tinytapeout.com/chips/ttsky25a/tt_um_tnt_mosbius) |
| Andrew Kang's | `tt_um_mosbius` | [tt_um_mosbius](https://tinytapeout.com/chips/ttsky25a/tt_um_mosbius) |

One xschem library and one Python toolchain cover both -- see
[`examples/README.md`](examples/README.md#which-part) for how to point a
build at either one. This page is what's actually different between them,
and what's been measured on each.

## What's different

**Every PMOS splits the same total width into 1.5x as many fingers on
`tt_um_mosbius`.** A finger is 5.0 um wide there against 7.5 um on
`tt_um_tnt_mosbius`; every NMOS is identical on both parts. Checked at all
three PMOS widths in use: the sky130 PDK bins its high-voltage PMOS on
total width and length, treats finger count as an ordinary instance
parameter, and has one width bin from 20 um to 1.01 mm -- so the finger
count cannot move the model bin. `mosbius simulate` writes each part's real
geometry into the routed netlist as a `.param pmos_width_per_finger`, which
the ideal `mosbius_*` symbols on the design sheet read too, so the as-drawn
half always matches whichever part the as-routed half was built for.

**A generic transistor's bulk follows a different node on each part.**
`tt_um_mosbius`'s generic PMOS and PMOS differential-pair halves tie their
bulk to their own source, and its NMOS differential pair and OTA input pair
do the same on the NMOS side, through real deep-nwell isolation;
`tt_um_tnt_mosbius` ties every bulk to the rail. Every device whose source
never leaves a rail is unaffected either way, which is most of both chips.
It bites a source whose voltage moves: negligible on a differential pair's
shared source, which is a virtual ground for a differential input (1.9% of
gain, 4.8 mV of output on `examples/pdiffamp/`), but worth 15-19% on a
source follower.

`mosbius simulate` writes this into the generated routed netlist as a pair
of resistor values, `rwell_rail` and `rwell_source`, driven by
`Chip.bulk_follows_source` -- the route `pmos_width_per_finger` takes, so
`--project` stays the only place a part is named. `mosbius_pmos.sch` and
`mosbius_nmos.sch` split an internal `well` node between the rail and the
device's own drawn source with those two values. Confirmed on silicon
before it was fixed, with a PMOS and an NMOS source follower on
`tt_um_mosbius`: 0.921 V/V and 0.924 V/V measured, against 0.918 and 0.929
as routed but only 0.746 and 0.789 as drawn.

The OTA's input pair shares one tub on its own tail node, so
`mosbius_ota.sch` splits its well the same way; its PMOS loads sit on the
supply on both parts and keep their existing tie. Every transistor in the
ideal library whose source can leave a rail now follows the right node on
both parts, which was checked by flattening both extracted device libraries
and listing every instance with an off-rail bulk. `tt_um_tnt_mosbius` has
none. `tt_um_mosbius` has eight, in the two generic transistors, the two
differential pairs and the OTA input pair, plus three shorted dummies.

**The config chain is a different length.** 192 bits (48 hex characters)
on `tt_um_tnt_mosbius`, 196 (49) on `tt_um_mosbius`. `--project`/
`MOSBIUS_PROJECT` is the only place either is named; every bitstream,
pad table and routed netlist follows from it.

**Which PCB pad a design's `ua[k]` reaches is unrelated to the geometry,
and differs per part.** It is composed from two looked-up halves -- the
shuttle index's `analog_pins` entry for that macro, and the demoboard
carrier's own wiring -- never computed, and the two parts land on
different letters for the same `ua[k]`:

| | `ibias` | `ua1` | `ua2` | `ua3` | `ua4` | `ua5` |
|---|---|---|---|---|---|---|
| `tt_um_tnt_mosbius` | K | C | J | D | G | F |
| `tt_um_mosbius` | F | K | C | J | D | G |

`mosbius pads`/every `measure_*_ad3.py` script derives this at run time
(`mosbius/pads.py`); it is never worth memorising.

**Bus row parasitics differ per part too**, which is why an as-routed
number can move even when the as-drawn one barely does -- see the ring's
numbers below, where both parts' as-drawn frequency agrees to 0.05% but
the as-routed frequencies are 17% apart.

## Measured on silicon, both parts

Every example except currentsource's ratio sweep and OTA's DC offsets has
now been measured on both chips. `tt_um_tnt_mosbius`'s die was established
as an `ss` process corner (CLAUDE.md, from the ring and the inverter
together); `tt_um_mosbius`'s corner is not established -- one sample, not
a full corner sweep -- but every measurement below tracks its own `tt`
simulation more closely than tnt's die does.

| example | metric | `tt_um_tnt_mosbius` | `tt_um_mosbius` |
|---|---|---|---|
| inverter | trip point | 1.599 V | 1.614 V |
| diffamp | gain | 16.19 V/V | 17.91 V/V |
| pdiffamp | gain | 17.82 V/V | 18.10 V/V |
| ring | frequency | 39.60 MHz | 44.61 MHz |
| otabuf | node capacitance, fitted | not published | 43.9 pF (1.09x the model) |
| currentsource | `psource_a` @ mid-rail | +191.3 uA | +213.3 uA |
| currentsource | `nsink_a` @ mid-rail | -220.4 uA | -200.5 uA |
| srlatch | reset time | 24.46 ns | 27.95 ns |

Each example's own README has the full as-drawn/as-routed/on-silicon
comparison and the "Try this" that goes with it.
