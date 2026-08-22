# TODO — deferred work

Raised during the first outside-user run through `TUTORIAL.md` (2026-08-20),
drawing an inverter and heading for a 3-stage ring oscillator. Each item has
the context needed to act on it without re-deriving anything.

**Renumbered from 1 on 2026-08-22**, for the third time. The first renumber
removed the eight items the symbol/pin-geometry work closed; the second
removed two more and shrank two, leaving the drain/source-swap hint
(`check.py`'s `D2`), a working single-OTA route, the OTA's `tail=` reaching
the bitstream, and an unreachable (pin, row) explaining itself instead of
raising `KeyError`. This one removes the tail-symbol work order: two new
symbols (`mosbius_ntail`/`mosbius_ptail`), `netlist.py`/`route.py`/`check.py`
updated, and `examples/diffamp/` proving it end to end (route table, no
dropped `tail=`, `ctrl_dpn_tail` reaching the bitstream). What's left
renumbers down: device allocation by netlist order is now §2, repeated
findings is now §3.

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


## 2. Device allocation is decided by netlist order

Raised 2026-08-21, found routing a hand-drawn SR latch. The diagnostic half
of this is done -- the failure below now raises a `RouteError` that names
the device, the net, the rows each terminal can reach and the rule it ran
into, instead of `KeyError: ('cfgb_dpn_inm', 6)`. The allocation itself is
unchanged, so the same designs still fail; they just fail legibly.

`_allocate_fets` pass 2 hands the two independent slots (`nmos_a`/`nmos_b`)
to whichever requests come first in the netlist, then pass 3 gives the
diff-pair halves to whatever is left. Nothing consults where those devices'
*gates* have to land -- so whether a design routes can depend on the order
xschem happened to list its instances in.

The SR latch in `examples/srlatch/` is the worked case. Six devices, four
NMOS all sourced on `VGND`, so two of them necessarily take diff-pair
halves. As listed it routes: `XM2`/`XM4` take the independent slots and the
halves fall to `XM5`/`XM6`, whose gates are on `ua1` and `ua2`. Relist the
same six devices in a different order and `XM4` takes a half instead, with
its gate on `net1` -- and that is the combination the next paragraph rules
out.

**Why row 6 specifically, and why no pin choice avoids it.** The free rows
are `A{2,4,6}` and `B{1,3,5,6}`, so the only row free on *both* sides is 6
(`route.py`'s `ROWS_FREE_ON_BOTH_SIDES` derives this rather than asserting
it). An internal net touching devices on both sides is therefore forced
onto row 6. Diff-pair inputs reach only rows 1-3 (CLAUDE.md trap 6). So:

> a diff-pair half's gate can never sit on an internal net that spans both
> bus sides.

In the latch that net is `net1`, the cross-coupling node, which gates
`XM3`/`XM4`. Moving Q from `ua3` to `ua4` does not help -- checked. The
constraint is about the internal net, not the package pin.

Note the tail-symbol work (closed 2026-08-22) does part of this for free: a
drawn `mosbius_ntail`/`mosbius_ptail` declares which two FETs are the pair,
so the allocator stops having to infer it for any pair that has one. What
is left here is the case with no tail drawn.

The fix: **allocate by constraint rather than by line order.** Give the
independent slots to the devices whose gates sit on nets a diff-pair input
cannot reach, and spend the halves on the ones that fit. That is a genuine
ordering rule (SPEC.md §3.4's "spend the constrained resource first"), not
a heuristic: a two-sided internal net on a gate is a hard exclusion,
knowable before any row is picked. `route.py` already computes the reach
half of it -- `rows_reachable()` and `_shared_reach()`, both derived from
the bit map -- so what is missing is using that during allocation rather
than only when placing a row.

Note this interacts with sticky routing (SPEC.md §3.2b): a better
allocator must not silently relocate an existing working design, so it
belongs behind the same stored-routing reuse as everything else.

## 3. Repeated findings repeat their whole explanation

Raised 2026-08-21 by the user, seeing two near-identical 23-line warnings
from one `mosbius route`.

Every check emits one `Finding` per offending thing, and `_format_report`
prints each in full. When a check fires on several devices at once the
reader gets the same explanation over and over. The SR latch is the
smallest case: two `R1` warnings, 23 lines each, **21 of those lines
identical** -- only the device name and the role differ. That is 46 lines
of a 57-line report saying one thing twice.

`I1` is the same shape and worse in bulk: five "does nothing" notes on the
SR latch, seven on the ring oscillator, one per bus segment, all of them
the same sentence with a different segment name. They are hidden without
`--verbose`, which is a workaround rather than a fix.

Wanted: name every device the finding applies to, then explain once.

```
WARNING -- XM5 and XM6 had their w=1 ignored: ndiffpair+ and ndiffpair-
           have a fixed width

  <the explanation, once>
```

Two things to get right rather than grouping blindly:

- **Group by what the explanation actually depends on, not just by check
  code.** `R1`'s text quotes the geometry, and that differs by polarity:
  an NMOS half is `W=40 nf=8` from `diff_n.sch` and a PMOS half is
  `W=120 nf=16` from `diff_p.sch`. So the ring's two `R1` warnings are
  *not* mergeable, while the SR latch's two are. The key is roughly
  (check, device kind, requested width) -- worth deriving from the message
  inputs rather than guessing.

- **Keep each finding individually addressable.** `check()` returns a
  `SafetyReport` that `program.py` gates uploads on and the tests assert
  against per-code. Grouping belongs in the *formatting*, not in the
  finding list -- so `_format_report` (and `watch.py`, which formats its
  own) should merge for display while `SafetyReport.findings` stays one
  entry per offending device.
