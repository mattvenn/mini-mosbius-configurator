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

Today you can only simulate the *pre-route* schematic — SPEC.md §3.1b's
Level-1 "ideal" result, real sky130 device sizing but no switch-matrix
parasitics. `examples/inverter/README.md` quantifies the gap: 84.4 ns
simulated at `w=1` against tnt's ~50 ns on real silicon.

The mechanism for the accurate version already exists and is unused:
`mosbius/spice.py`'s `render_config_spice()` emits a tie for all 192 config
pins of `mosbius.sym`, so a routed `SwitchConfig` can be simulated through the
real switch matrix with no behavioural model of the shift register (SPEC.md
§3.7). What's missing is the workflow around it — generating a testbench from
a routed config and running it. Budget ~2 min of sky130A model load per run
(see CLAUDE.md).

The container half of that workflow is now known, from re-simulating the SR
latch at Level-1 on 2026-08-21 -- see `examples/srlatch/README.md`'s
"Reproducing it" for the working invocation. `examples/ringosc/README.md`'s
"Reproducing this" carries the rest of the plan: how to wire all 192
`mosbius.sym` config pins from its `B` (pin box) lines, and why those
coordinates must be generated rather than typed -- xschem merges net names
only across wire segments that genuinely touch, so one coordinate off by
a hair gives you a schematic that looks right, netlists without complaint,
and has a floating pin in it. Netlisting is handled by the
repo-root `xschemrc` as long as xschem runs from the repo root; that run took
54s wall clock, essentially all sky130A model load.

Level-2 is the case that `xschemrc` does *not* cover, and it is worth knowing
before starting. `ttsky-mini-mosbius/xschem/mosbius.sym` resolves its own
sub-symbols (`tt_asw_3v3` and friends) by bare name relative to where xschem
is running, so that netlist has to be produced from inside
`ttsky-mini-mosbius/xschem` -- a different working directory, hence a
different `xschemrc`, hence a different `netlist_dir`. Either add that
directory to the repo `xschemrc`'s `XSCHEM_LIBRARY_PATH` and check the bare
names still resolve, or accept the second working directory and pass `-o`
explicitly. Get it wrong and the failure is silent: devices are replaced by
`*  x1 -  tt_asw_3v3  IS MISSING !!!!` and ngspice runs the empty deck.
