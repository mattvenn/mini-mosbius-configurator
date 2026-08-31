# todo

Grouped by what kind of work an item is, and numbered from 1 straight
through the groups. As always, the numbering is rewritten whenever
anything is removed, so cite an item by describing it, not by its number.

## Bench and hardware in the loop

1 no device-setting cycler bit has ever been varied on silicon, and the
mirror ratio is the cheapest one to check.

All 11 cyclers -- four FET widths, four mirror ratios, three tails --
share one encoding, `n = step * (1 + b_lsb + 2*b_msb)` (SPEC.md Sec 2.11),
and that came from the placeholder configurator's SVG, which is not an
independent oracle for its own bit map. Every measurement so far uses one
fixed setting per bitstream: `examples/diffamp/` and `examples/pdiffamp/`
do vary the tail current, but by moving the bias rail, not by changing
`tail=`, so the bits themselves are untested.

`examples/currentsource/` is the vehicle because the answer is a ratio of
two currents from the same reference, which cancels the demoboard's
uncalibrated bias source entirely -- the one experiment here immune to it.
Everything measured on that example so far was at `ratio=2`, and `ratio`
and the bias current enter the answer only as a product.

Making the four configurations needs no schematic edit: rewrite
`ratio=2` to 1/3/4 in `build/currentsource.spice` and route each, the same
netlist-not-schematic trick `tools/sweep_corners_currentsource.sh` uses so
the committed sheet and every published number stay put. Checked
2026-08-31: all four route, all four leave `psource_a` on `ua2` and
`nsink_a` on `ua3`, and the bitstreams differ only in the ratio cycler
bits. `tools/ad3/measure_currentsource_ad3.py --mode ratio` takes them with
`--configs`, reads each ratio back out of its own bitstream rather than
its filename, and warns if the router did move a device between them.

One measured result bears on this and currently lives only in a gitignored
`build/` file: stepping the bias current at `ratio=2` gave 7 points from
24 to 154 uA fitting out = 1.9127 x in - 0.508 uA. The linearity is
excellent (residuals under 0.6 uA) but the slope is 4.4% below the ideal
2.000 -- and that slope is not separable from a scale error in
`build/ibias_clamp.json`, since the ibias axis is read from it rather than
measured. The ratio experiment is what tells those two apart.

## Examples

2 make it easy for people to submit designs to the examples

## Tooling and library

3 there will be various versions of mini mosbius (multiple pdks and multple chips). this might need tracking / handling in the tool.
ideally the same bitstreams will produce similiar results, but at least the routed spice will need to take intou account the pdk. and possible future versions of mosbius might have  a new feature that won't be available in older ones. we should be able to get a list of which chips the design is present on with the api

## Docs and user-facing text

4 check all the schematic texts

5 all user facing text will ultimately be in a separate file, for internationalisation and for easy re-writing of all messages

6 add limks for xschem viewer. doesn't work out of the box, need to be able to provide our custom library
