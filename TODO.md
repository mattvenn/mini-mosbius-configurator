# TODO — deferred work

Raised during the first outside-user run through `TUTORIAL.md` (2026-08-20),
drawing an inverter and heading for a 3-stage ring oscillator. Each item has
the context needed to act on it without re-deriving anything.

**Renumbered from 1 on 2026-08-21**, for the second time that day. The first
renumber removed the eight items the symbol/pin-geometry work closed. This
one removes two more and shrinks two: the drain/source-swap hint now exists
(`check.py`'s `D2`), a single OTA no longer crashes the router, the OTA's
`tail=` now reaches the bitstream, and an unreachable (pin, row) is now a
`RouteError` that explains itself rather than a `KeyError`. What is left of
those last two items is in §2 and §3 below.

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


## 2. Draw the tail: two new symbols, and `ibias` made implicit

Decided 2026-08-22, not started. The decision is the part that was missing;
what follows is a work order, not an open question.

**What is wrong today.** `ctrl_dpn_tail` (bits 180/181) and `ctrl_dpp_tail`
(bits 162/163) are real and programmable, and nothing a user can draw
reaches them. A differential pair is not a symbol: you draw two
`mosbius_nmos` sharing a source and `_allocate_fets` pass 1 infers the pair
*afterwards*, so the tail belongs to no object on the schematic. The OTA is
fine -- it is a symbol, it has `tail=`, and that reaches `ctrl_otan_tail`.

**The decision: draw the tail as the transistor it is.** Two new symbols,
`mosbius_ntail` and `mosbius_ptail`, each with **one drawn pin** -- the
drain, wired to the pair's shared source node -- and a `tail=2/4/6/8`
property. Drawing one *declares* the pair (the two FETs sourced on that node
are its halves) instead of leaving the router to infer it. Drawing none
keeps today's behaviour exactly: shared source tied to its rail by
`ctrl_dp{n,p}_source`, halves usable as two standalone FETs, which is what
`examples/srlatch/` depends on.

**Gate and source are implicit** (`extra=`, as the body ties already are).
Not a style choice: the NMOS tail's gate really is on `ibias`, but the PMOS
tail's is on `ibias_p`, which `mirror_n`'s `iout_fixed` leg generates
*inside* the chip. `ibias_p` is not a port of `minimosbius_template.sch` and
cannot become one without exposing chip internals as pins, so there is no
honest net to draw a PMOS tail's gate to. Symmetry between the two symbols
matters more than matching the mirrors.

**Same change to the mirrors and the OTA, for the same reason.**
`mosbius_nsink`, `mosbius_psource` and `mosbius_ota` each carry a *drawn*
`ibias` pin whose connection the router ignores completely -- wire a
`mosbius_nsink`'s `ibias` to `ua3` today and it routes clean, no warning
(verified 2026-08-22). All four bias connections are hardwired in silicon,
so all four should be implicit. Nothing in the repo instantiates those three
symbols yet, so no schematic needs editing -- this is as cheap as it will
ever be.

### Hardware facts, verified 2026-08-22 -- do not re-derive

Read out of the read-only submodule, `ttsky-mini-mosbius/xschem/`:

- **The tail is a bank, not one FET.** `diff_n.sch`: `M8` (`W=20 nf=4`,
  `L=1`) always in circuit; `M6` (same geometry) behind switch `x4`, gated
  by `ctrl_tail[0]`; `M10` (`W=40 nf=8`) behind `x5`, gated by
  `ctrl_tail[1]`. A 1x + 1x + 2x bank, all gates on `vbias`, all sources on
  GND. `diff_p.sch` mirrors it. So the setting is a **parallel unit count**,
  never a length -- same as the widths (SPEC.md §2.12).
- **2/4/6/8 rather than 1/2/3/4** because a pair splits its tail between two
  matched halves: `n = 2 * (1 + b_lsb + 2*b_msb)`, and `n/2` is the number
  of unit slices.
- **The tail and the source tie are alternatives on one node.** `diff_n.sch`
  switch `x1`, gated by `ctrl_source`, shorts `itail` straight to GND,
  bypassing the bank. One or the other, never both -- which is exactly the
  "tail drawn / not drawn" distinction above.
- **Bias chain.** `ua[0]` -> `ibias` -> `mirror_n` reference, the `dpn` tail
  and the OTA tail. `mirror_n`'s `iout_fixed` -> `ibias_p` -> `mirror_p` and
  the `dpp` tail. Two nets, chained; the PMOS side is two mirror hops from
  the pin.
- **Drawing a tail as a `mosbius_nmos` does not work today**, which is why
  this needs a symbol rather than a convention: gate on `ibias`, drain on
  the shared node, `w=4` -> the router allocates it as `nmos_a`, burning one
  of the two independent NMOS and writing `ctrl_nfeta_width`. Verified.

### The work, in order

1. **`mosbius_ntail.sym` / `mosbius_ptail.sym`.** One drawn pin `d`;
   `tail=2` in the template; gate and source via `extra=`, templated to
   `ibias`/`VGND` and `ibias_p`/`VAPWR`. Note `ibias_p` will netlist as a
   net nothing else touches -- harmless, but check `check.py`'s design
   checks and `W2`/`W3` do not flag it.
2. **`netlist.py`.** `SYMBOL_KIND` and `DEVICE_PINS` for the two kinds;
   add `ibias` (and the tails' `g`/`s`) to `IMPLICIT_PINS`. Extra pins
   append in `extra=` order, so `DEVICE_PINS` ordering must be re-derived
   by netlisting each symbol, not guessed.
3. **The three existing symbols.** Move `ibias` from a drawn `B` box into
   `extra=` on `mosbius_nsink`, `mosbius_psource`, `mosbius_ota`; update
   their `DEVICE_PINS` rows to match.
4. **`route.py`.** Roles `ntail`/`ptail`, at most one of each. A drawn tail
   claims the two same-polarity FETs sourced on its drain as the pair
   halves -- this *replaces* pass 1's inference for that pair. Emit
   `ctrl_dp{n,p}_tail` from `tail=` via the existing `TAIL_SETTING` table,
   and suppress `ctrl_dp{n,p}_source` whenever a tail is drawn.
5. **`check.py`.** Delete `_check_r2_tail_dropped` and `route.py`'s
   `UNSETTABLE_TAIL` -- they exist only to say the value went nowhere. Add,
   in their place: a tail whose drain is not exactly two same-polarity
   sources, and a tail drawn on a pair whose halves are also asking for a
   rail-tied source.
6. **Tests and an example.** No committed design uses a diff pair as a pair
   yet; a small differential amplifier would be the honest way to prove
   this end to end.
7. **Docs.** SPEC.md §2.12/§3.4's symbol list, `TUTORIAL.md`, `README.md`,
   and CLAUDE.md's "no body pin" note, which becomes "no body or bias pin".

### One-time cost, and why both halves land together

Changing what a symbol emits changes every netlist line, so
`design_topology_hash()` changes and every stored `.mosbius.json` re-routes
once. That is fine now -- three example designs, none of them using the
affected symbols -- and annoying later. Do the mirrors' `ibias` and the tail
symbols in the same commit so the cost is paid once.

## 3. Device allocation is decided by netlist order

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

Note §2 does part of this for free: a drawn tail declares which two FETs
are the pair, so the allocator stops having to infer it for any pair that
has one. What is left here is the case with no tail drawn.

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

## 4. Repeated findings repeat their whole explanation

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
