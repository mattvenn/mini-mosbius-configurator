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

**Status as of 2026-08-22: real progress, not closed.** Best result so far is
**93.5MHz simulated vs. ~30MHz on real silicon (~3.1x too fast)** -- down from
an earlier "no switch-matrix simulation possible at all" state, and from an
intermediate hand-built attempt that only reached ~12x too fast. Full
reasoning, dead ends, and the exact numbers are in this project's memory
(`ring_oscillator_l2_sim` -- ask to recall it, or see below for the parts
that matter for resuming in a fresh session/repo checkout).

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
works headless, runs ngspice, measures the period). **Currently untracked
in git** -- decide whether to commit it before relying on it surviving a
fresh checkout.

**Ruled out, don't re-test:** pad/ESD/bond-wire loading (the real
`pad_model.sym` contributes only 250fF at the chip-side node once the
1nH bond wire and two series resistors isolate it from its bigger
2pF/3pF stages further out -- measuring pre- vs. post-pad gave the same
period to within noise); and a flat lumped capacitance standing in for
an open switch's off-state loading (an MVP attempt -- real transistor
model when closed, single 9.9fF cap when open -- only reached ~365MHz/
~12.2x too fast, vs. 93.5MHz/~3.1x for the real full switch matrix. The
lesson, not just the number: an open `tt_asw_3v3`'s real contribution
isn't well approximated by one flat capacitance value, so don't reach for
that shortcut again expecting it to hold up).

**What's still untested, roughly in order of likely payoff:**
1. The 93.5MHz result is for `tb_mosbius_ringo.sch`'s own baked-in ring
   config, not the exact measured bitstream
   (`380088007001000010000404250109000400000040000014`, per
   `examples/ringosc/README.md`) -- same class of 3-stage ring, not a
   strict apples-to-apples. Re-run the same full-switch-matrix approach
   against that exact bitstream's config for a real comparison.
2. The within-column row-to-row coupling capacitance (~43fF between
   adjacent switches in one `asw_col_*` column, a real value found via
   magic PEX extraction of `ttsky-mini-mosbius/mag/asw_col_a.mag` with
   `cthresh=5fF`/`rthresh=10Ω`) was skipped for simplicity, twice. Unlike
   the ruled-out flat open-switch cap, this one is a measured layout
   value, not a guess -- worth adding on top of the full real-transistor
   model.
3. Only the "tt" (typical) process corner was tried.
4. Real layout-extracted wire R/C (vs. today's zero-length ideal wiring
   between real switch-matrix devices) hasn't been tried at all yet --
   an early analytical estimate suggested it's negligible, but that was
   before the 93.5MHz baseline existed and is worth re-checking now.

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
