# TODO — deferred work

Raised during the first outside-user run through `TUTORIAL.md` (2026-08-20),
drawing an inverter and heading for a 3-stage ring oscillator. Each item has
the context needed to act on it without re-deriving anything.

**Renumbered from 1 on 2026-08-22**, for the fifth time. The first
renumber removed the eight items the symbol/pin-geometry work closed; the
second removed two more and shrank two, leaving the drain/source-swap
hint (`check.py`'s `D2`), a working single-OTA route, the OTA's `tail=`
reaching the bitstream, and an unreachable (pin, row) explaining itself
instead of raising `KeyError`; the third removed the tail-symbol work
order, which renumbered device allocation down to §2 and repeated
findings down to §3; the fourth closed that §3 (`check.py`'s
`merge_findings()`), leaving device allocation alone at §2. This one
closes §2 too: `allocate_devices()` no longer trusts netlist order.
`_allocate_fets_by_constraint()` tries every ordering of a polarity's FET
requests (at most 4! = 24, since only 4 roles exist per polarity) against
the *other* polarity's own allocation, and keeps the first one where no
diff-pair-role gate is forced onto a two-sided net or an out-of-range
package pin -- `itertools.permutations` yields the netlist's own order
first, so a design with no conflict keeps its exact existing assignment.
Sticky routing (SPEC.md §3.2b, an unchanged design reusing its stored
routing byte-for-byte) is untouched by this and still means a *changed*
design gets a full fresh `route()`, same as before -- explicitly out of
scope for this pass, since this is still a development phase and nothing
depends on a stored routing surviving yet. §2 was the last item, so
nothing renumbers this time: what's left is §1 alone.

This file used to keep numbers stable and leave gaps, because other files cite
items by number. Renumbering instead means those citations move too, and they
are updated in the same commit that renumbers -- so a `TODO.md` §number in the
repo is always live. Nothing outside this file should cite an item that no
longer exists.

## 1. Level-2 simulation of the routed design

**Status as of 2026-08-23: real progress, not closed.** Best result --
and the first genuine apples-to-apples comparison in this whole
investigation -- is **CONFIRMED: 38.33MHz simulated vs. ~30MHz on real
silicon (~1.28x too fast)**, from
`tools/run_ringo_measured_bitstream_wire_cap.sh`: the exact measured
bitstream (`380088007001000010000404250109000400000040000014`, not a
stand-in config), with real pad models on all three of its package pins,
the row-coupling cap, and real bus-wire self-capacitance (20-40x bigger
than an old, never-verified hand-estimate -- see below) all applied
together. All three loop nodes agree tightly (26.0879-26.0884ns), a good
sign the sim converged cleanly. This is down from an earlier "no
switch-matrix simulation possible at all" state, an intermediate
hand-built attempt (~12x too fast), a 93.5MHz milestone (~3.1x too fast,
on a *different* config -- `tb_mosbius_ringo.sch`'s own baked-in one,
never measured on real silicon), 67.66MHz (~2.26x too fast, same
wrong-config caveat, + row-coupling cap), and 42.92MHz (~1.43x too fast,
the same exact-bitstream/pads/row-coupling combo as the current best, but
without bus-wire capacitance). An intermediate 37.62MHz result (2026-08-22)
had a real bug (wrong `bus_B[2]` value) -- fixed and re-run 2026-08-23 for
the confirmed 38.33MHz above; treat 37.62MHz as superseded, not a separate
data point. Not yet known how much of the total 93.5->38.33MHz drop is
attributable to which specific factor (exact bitstream+pads, row-coupling
cap, bus-wire cap) -- each was added cumulatively, never isolated. (An
earlier "78.81MHz" row-coupling result was also briefly reported and
retracted the same day -- a real bug, coupling caps inserted at the wrong
netlist scope, disconnected from the actual switch nodes. Fixed; 67.66MHz
above is the real number for that specific test.) Full reasoning, dead
ends, and exact numbers are in this project's memory
(`ring_oscillator_l2_sim` and `dc_resistance_validation` -- ask to recall
them, or see below for the parts that matter for resuming in a fresh
session/repo checkout). A separate, independent DC validation (different
bitstream: real device + pad models matched a real multimeter reading,
300Ω, to within ~1%, 303.4Ω simulated) strongly suggests the remaining gap
is capacitance-related, not resistance/on-state modeling -- which both the
row-coupling and bus-wire results confirm. For context: the user's own
separate TT08 `tt_um_mattvenn_analog_ring_osc` design (a simple
standard-cell inverter chain, no switch matrix) measured ~15-20% off its
own predicted frequency on real silicon -- so ~1.28x here is now in the
same ballpark as a much simpler design's inherent simulation-to-silicon
gap, despite starting 82x off before any parasitic modeling. Given how
close this now is, worth asking the user whether the remaining gap is
worth chasing further or whether this answers the investigation's core
question well enough.

**The unlock: use the submodule's own testbench, not a hand-built one.**
`ttsky-mini-mosbius/xschem/tb_mosbius_ringo.sch` is the upstream author's
own ring-oscillator testbench -- instantiates `mosbius.sym` with real
VAPWR=3.3V/VDPWR=1.8V/Ibias=100µA, real PDK device symbols with
`spiceprefix=X` set correctly, a working `.control` block, and a real
`pad_model.sym` already wired onto its 5 observable nodes (`n1`-`n5`,
`out`). A hand-built testbench (wiring `mosbius.sym`'s 192 pins from
scratch via `mosbius/spice.py`'s `render_config_spice()`, the approach
originally planned below) hit a spurious "could not find a valid
modelname" error that turned out to be an artifact of hand-copying a
`.lib` line rather than using `sky130_fd_pr/corner.sym` the way the
upstream testbench does -- not a real device limitation, but a wasted
detour. **Look for an existing upstream testbench before building one.**
`ttsky-mini-mosbius/xschem/tb_*.sch` has several more (device-level DC/AC
sweeps, OTA stability/CMRR, etc.) that are likely similarly useful
reference points for other simulation work, not just this one.

**The other unlock: this dev host's 1.9GB RAM is not enough**, even
filtered down to ~90 of the 188 switch instances (confirmed OOM). The user
has a second, occasionally-available machine with more RAM -- that's what
actually ran the 93.5MHz result, interactively in xschem, measuring
`v(out)` (not `v(out_ref)`, the testbench's own parallel *ideal*
discrete-transistor reference circuit with no switch matrix at all --
easy to grab by mistake, reads ~2.09GHz). A script for reproducing this
headlessly now exists: `tools/run_ringo_full_sim.sh` (netlists
`tb_mosbius_ringo.sch` unmodified, patches only the generated `build/`
netlist's `.control` block to `wrdata` instead of interactive `plot` so it
works headless, runs ngspice, measures the period). Committed, along with
`tools/run_ringo_no_stage2_pad.sh`, `tools/run_ring_pad_loaded.sh`,
`tools/run_ringo_row_coupling.sh`, `tools/run_ringo_measured_bitstream.sh`,
and `tools/run_ringo_measured_bitstream_wire_cap.sh` (the current
best-result script, confirmed with the corrected `bus_B[2]` value) -- all
follow the same pattern and all need the higher-RAM machine except
`tools/run_ringo_measured_bitstream_lowmem.sh`, which runs fine on this
dev host directly but is a documented negative result, not a viable
shortcut (see below).

**Ruled out, don't re-test:** pad/ESD/bond-wire loading *on non-loop-critical
nodes* (the real `pad_model.sym` contributes only 250fF at the chip-side
node once the 1nH bond wire and two series resistors isolate it -- measuring
pre- vs. post-pad on the testbench's output-buffer tap gave the same period
to within noise; note pad loading on a *loop-critical* node did matter,
~22%, when tested separately -- it's driver-strength-dependent, not a fixed
rule, see memory for the full comparison); and a flat lumped capacitance
standing in for an open switch's off-state loading (an MVP attempt -- real
transistor model when closed, single 9.9fF cap when open -- only reached
~365MHz/~12.2x too fast, vs. 93.5MHz/~3.1x for the real full switch matrix.
The lesson, not just the number: an open `tt_asw_3v3`'s real contribution
isn't well approximated by one flat capacitance value, so don't reach for
that shortcut again expecting it to hold up).

**Confirmed real, now with a valid measurement: within-column coupling
capacitance.** Corrected from an earlier "row-to-row adjacency" description
(that was wrong; re-verified via a fresh magic PEX extraction of
`ttsky-mini-mosbius/mag/asw_col_a.mag`): every one of a column's 6 switches
shares the same `mod` net (its one fixed device terminal), and each
switch's own `bus` stub couples to that shared trace at a consistent
~43.19fF regardless of row. `tools/run_ringo_row_coupling.sh` applies this
to all 150 real matrix-column switches -- its first version had a real
netlist-scoping bug (caps landed outside `.subckt mosbius`, disconnected
from the real nodes), fixed and re-run: **67.66MHz, a genuine ~27.6%
slowdown from the 93.5MHz baseline**, closing real ground (3.12x -> 2.26x
too fast).

**Also confirmed real, now included in the best result: bus-wire
capacitance.** Every result before 2026-08-22's later pass left the
horizontal bus wire itself as a zero-length ideal net (distinct from the
row-coupling cap, a short-distance switch-to-column-terminal effect).
Real magic PEX extraction of the full `ttsky-mini-mosbius/mag/asw_matrix.mag`
(not just one column) gives the true full-length wire capacitance per
bus row -- all roughly 20-40x bigger than an old hand-estimate (~30-50fF)
that had justified skipping this. Applied via
`tools/run_ringo_measured_bitstream_wire_cap.sh`: 42.92MHz -> 37.62MHz
(2026-08-22, later found to have a wrong `bus_B[2]` value -- see below).
**Correction found the same day: that run's `bus_B[2]` value (1819.36fF)
was wrong**, found while independently re-extracting all 12 rows for the
reusable feature below -- it was measured through the special
`asw_col_short` column assuming its per-index row order matches the
regular, hardware-validated columns' `[6,3,5,2,4,1]` pattern; re-checking
directly proved that wrong for `asw_col_short` specifically (its supposed
row-2 node isn't even electrically the same net as the real `bus_B[2]`,
measured through a regular column: **922.84fF**, roughly half the original
value). **Re-run 2026-08-23 with the corrected value: 38.33MHz**, slightly
higher than 37.62MHz as predicted (less capacitance -> less loading ->
faster) -- confirming the fix and giving the trustworthy final number.
37.62MHz is superseded, not a separate data point.

**New reusable feature, real code not just a script (2026-08-22):
`mosbius/spice.py`'s `BUS_WIRE_CAPACITANCE_F` + `render_bus_wire_caps()`.**
All 12 bus rows' real capacitance (not just the 5 this investigation's
bitstream happened to use), extracted once via the same full-matrix PEX
recipe, committed as real data with tests (`tests/test_spice.py`) so future
testbenches never need to re-run the slow (~5min) magic extraction --
matches `render_config_spice()`'s existing pattern (include unconditionally
alongside a `mosbius.sym` instance, ties to `VGND`). One row (`bus_B[5]`)
couldn't be found as a distinctly-labeled node in either extraction attempt
(an `ext2spice` net-naming quirk specific to that one row/column
combination, not understood) -- uses `bus_A[5]`'s value as a same-row
estimate, documented in the module rather than silently guessed.

**Tried and rejected, real negative result: dropping open switches
entirely.** Hypothesis: since the bus-wire cap (aggregate, whole-matrix)
and the row-coupling cap (one column) looked like they might be measuring
the same physical effect at different scales (26 columns x ~43fF ~= 1.1pF
lines up with the ~900fF-1.8pF per-row values), maybe real transistor
models are only needed for *closed* switches, with every *open* switch
dropped from the netlist entirely (no transistor, no cap) and the bus-wire
cap alone standing in for their aggregate contribution -- cutting the real
transistor count from 188 to about a dozen, small enough to run on a normal
1.9GB host without needing the second machine at all.
**Tested directly (`tools/run_ringo_measured_bitstream_lowmem.sh`, ran
successfully right here, no OOM): 63.17MHz -- not close to the (then
uncorrected) 37.62MHz reference (68% higher, worse than even the 67.66MHz
row-coupling-only result; still not close to the now-confirmed 38.33MHz
either).** A real transistor's off-state electrical behaviour and a wire's
layout capacitance are additive, different physical effects, not
redundant -- confirmed, not just suspected. **Don't build a low-memory
"closed switches only" shortcut on this basis; keeping every switch in the
matrix as a real transistor, open or closed, is load-bearing for accuracy.**
The low-memory win instead comes from the reusable bus-wire-cap lookup
table above -- it doesn't reduce simulation cost, but it does remove the
"someone has to babysit a 5-minute magic extraction" cost from every new
design.

**What's still untested, roughly in order of likely payoff:**
1. Isolating how much of the 93.5->38.33MHz drop is the exact-bitstream
   (3 real pads, different topology) switch versus the row-coupling cap
   versus the bus-wire cap specifically -- each was added cumulatively,
   never in isolation. Not yet done.
2. Real layout wire *resistance* -- only capacitance has been added so
   far; the same wire that carries this capacitance also has real series
   resistance, untested.
3. Only the "tt" (typical) process corner was tried.
4. At ~1.28x too fast, already comparable to the user's own separate TT08
   ring-oscillator design's inherent simulation-to-silicon gap (~15-20%,
   no switch matrix at all) -- worth explicitly deciding whether to keep
   chasing this gap or treat it as close enough. Not purely a technical
   question, ask the user.

**Reusable groundwork from this pass, if any of the above needs it:**
a full, verified static mapping from `mosbius/bitmap.py`'s 156
switch-matrix bits (chain positions 0-155, grouped in 26 columns of 6) to
`ttsky-mini-mosbius/mag/asw_matrix.mag`'s 26 physical column instances (no
LVS needed -- matched by x-coordinate order, exact type-sequence match)
plus the row order within a column (physical array index is the *reverse*
of the RTL's per-column row order `[1,4,2,5,3,6]` -- confirmed against all
5 real `ua[]` pads, not guessed). Netgen/LVS-based net-correspondence was
tried and abandoned as unnecessarily heavyweight for this -- the static
mapping above supersedes it; don't redo the LVS route.

---

Original plan (superseded above, kept for the parts still relevant to a
from-scratch hand-built testbench if the upstream-testbench route above
ever stops being viable): the mechanism for the accurate version is
`mosbius/spice.py`'s `render_config_spice()`, which emits a tie for all 192
config pins of `mosbius.sym`, so a routed `SwitchConfig` can be simulated
through the real switch matrix with no behavioural model of the shift
register (SPEC.md §3.7). Budget ~2 min of sky130A model load per run (see
CLAUDE.md).

`examples/ringosc/README.md`'s "Reproducing this" has the plan: how to wire
all 192 `mosbius.sym` config pins from its `B` (pin box) lines, and why
those coordinates must be generated rather than typed -- xschem merges net
names only across wire segments that genuinely touch, so one coordinate off
by a hair gives you a schematic that looks right, netlists without
complaint, and has a floating pin in it.

`ttsky-mini-mosbius/xschem/mosbius.sym` resolves its own sub-symbols
(`tt_asw_3v3` and friends) by bare name relative to where xschem is
running, so that netlist has to be produced from inside
`ttsky-mini-mosbius/xschem` -- a different working directory, hence a
different `xschemrc`, hence a different `netlist_dir`. Either add that
directory to the repo `xschemrc`'s `XSCHEM_LIBRARY_PATH` and check the bare
names still resolve, or accept the second working directory and pass `-o`
explicitly. Get it wrong and the failure is silent: devices are replaced by
`*  x1 -  tt_asw_3v3  IS MISSING !!!!` and ngspice runs the empty deck.
