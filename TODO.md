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
`merge_findings()`), leaving device allocation alone at §2. The fifth
closed §2 too: `allocate_devices()` no longer trusts netlist order.
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
nothing renumbered that time: what was left was §1 alone.

**Closed on 2026-08-23: §1, Level-2 simulation of the routed design --
the last item, so this file has nothing open right now.** A long
investigation (project memory `ring_oscillator_l2_sim`,
`dc_resistance_validation`) established, with real silicon validation,
what an accurate Level-2 simulation actually needs: the real switch
matrix (every switch, open or closed, as a real transistor -- a
closed-switches-only shortcut was tried and definitively rejected), a
real ~43fF row-coupling capacitance per matrix-column switch, real
bus-wire capacitance per bus row (20-40x bigger than an old, never
verified hand-estimate), and real pad models on whichever package pins a
design's routing actually uses. Shipped as `mosbius simulate` (SPEC.md
§3.7): a routed design's JSON in, one self-contained
`<name>_mosbius.spice` subcircuit out, matching the exact 9-pin port list
(`ibias ua1 ua2 ua3 ua4 ua5 VAPWR VDPWR VGND`) every hand-drawn design
already exposes, ready to drop into an existing testbench (e.g. via
xschem's `spice_sym_def` instance property) in place of an ideal
`mosbius_*`-symbol block, so the testbench's own stimulus/analysis/probes
carry over unchanged -- deliberately not the tool's job to guess what
kind of simulation a design needs. `mosbius/data/mosbius_device_library.spice`
bakes in the switch matrix + row-coupling capacitance as a static,
committed asset (rebuild recipe: `tools/rebuild_mosbius_device_library.sh`),
so ordinary use needs no docker/xschem/magic step, only Python. Validated
end to end against `examples/ringosc/ring.sch` (routed for real, `mosbius
simulate`d, output inspected directly: correct name, correct pad on
exactly its one real package pin, all 150 row-coupling caps and 12
bus-wire caps present, `.subckt`/`.ends` balanced) and against the exact
measured bitstream, which reaches **38.33MHz simulated vs. ~30MHz on real
silicon (~1.28x too fast)** -- down from 82x too fast before this
investigation started, and now in the same ballpark as the user's own
separate TT08 `tt_um_mattvenn_analog_ring_osc` design's inherent
simulation-to-silicon gap (~15-20%, a much simpler circuit with no switch
matrix at all). Real tests: `tests/test_simulate.py`, 12 new (221/221
full suite passing). Not done, if anyone picks this up later: splitting
credit between the three factors above (each was validated cumulatively,
never in isolation), real layout wire *resistance* (only capacitance has
been modeled), and process corners other than "tt" -- none seemed likely
to be another large, surprising factor the way the row-coupling and
bus-wire capacitance were, so this was treated as close enough to call
the core question answered rather than chased further.

This file used to keep numbers stable and leave gaps, because other files cite
items by number. Renumbering instead means those citations move too, and they
are updated in the same commit that renumbers -- so a `TODO.md` §number in the
repo is always live. Nothing outside this file should cite an item that no
longer exists. **Right now there is nothing to cite: no numbered item is
open.** The next deferred item, whenever one is raised, becomes §1 again.
