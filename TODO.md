# new todo

an annoying ux issue is that xschem wants to save simulations in its own directory. and they really want to be in ./build . There needs to be an easy workflow for someone to be able to start xschem, load the templates and see the symbols, then export the netlist and run the docker all in one place. I'm having to remember to copy the spice netlist from xdschem/mosbius/simulation -> build, then run the docker and the python.

(Half of this is answered as of 2026-08-21: there is no copying and no docker
step any more. Press Netlist in xschem, then point the router straight at
`<schematic dir>/simulation/<name>.spice`. What remains is the rest
of the ask: launching xschem with the library path already set, so the whole
loop is one place.)

# TODO — deferred work

Raised during the first outside-user run through `TUTORIAL.md` (2026-08-20),
drawing an inverter and heading for a 3-stage ring oscillator. Each item has
the context needed to act on it without re-deriving anything.

**Renumbered from 1 on 2026-08-21**, when the first eight items were resolved
and removed: the symbol redraw, the pin-direction errors, netlisting via the
container, widths silently dropped on diff-pair halves, W2 firing on every
internal node, the missing `@spiceprefix`, and the example schematics left on
the old pin geometry.

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
"Reproducing it", which has the working invocation. The one trap worth
carrying forward: netlisting needs the sky130A xschemrc **and**
`xschem/mosbius_lib` on the library path. With only the library path the
schematic netlists fine, our own devices come out correctly prefixed, and the
*inner* `nfet3_*`/`pfet3_*` instances are replaced by
`*  M1 -  nfet3_g5v0d10v5  IS MISSING !!!!` -- a deck with no transistors in
it, which ngspice runs quite happily. Level-2 will hit the same thing against
`ttsky-mini-mosbius/xschem/mosbius.sym`, which pulls in `tt_asw_3v3` as well.
That run took 54s wall clock, essentially all model load.


## 2. Diagnose a probable drain/source swap instead of "doesn't fit"

Raised 2026-08-21, from a real 15-minute misdiagnosis.

A 3-stage ring whose PMOS had drain and source exchanged produced:

```
DOESN'T FIT -- not enough PMOS with independent sources
Your circuit needs 3 PMOS transistors (M2, M4, M6),
but the chip has only 2 with a source you can route anywhere
```

Every word true, and every word pointing away from the actual fault. The
netlist was

```
M2 ua1 VAPWR net1 VAPWR mosbius_pmos w=1     (g d s b)
```

-- drain on VAPWR, source on an internal node. That is not a circuit anyone
draws deliberately, and the allocator sees it as three PMOS each demanding a
routable source.

The check to add, before the allocator gives up: a FET whose **drain** sits on
a supply rail while its **source** sits on a net that is neither a rail nor a
`ua[]` pin is almost certainly wired backwards. For PMOS the rail is `VAPWR`,
for NMOS `VGND`. Say so, name the instances, and say what to do -- for a
`mosbius_pmos` the source is the *top* pin and the drain the *bottom* (the
reverse of `mosbius_nmos`), so the usual cause is a symbol flipped vertically
out of habit from a schematic drawn before 2026-08-21.

Keep it a *hint*, not an error: source-on-an-internal-net is legitimate in a
cascode or a source follower. It should fire only when the drain is on the
matching rail, which is the combination that has no sensible reading.

Worth checking whether this belongs in `check.py` (so it fires on a netlist
that routes, too) rather than only on the allocator's failure path.

## 3. Tail currents never reach the bitstream

Raised 2026-08-21, found while fixing the dropped-width item (now
resolved: widths are reported per device and a drop is warned about).

`route.py`'s device-settings loop emits width/ratio bits and nothing else:

```python
for dev_name, role in roles.items():
    if role in WIDTH_SETTING:
```

`WIDTH_SETTING` covers the four programmable FETs and the four mirror legs.
The three tail-current fields that exist in the bit map -- `ctrl_dpn_tail`,
`ctrl_dpp_tail` and `ctrl_otan_tail`, each a step=2 cycler taking 2/4/6/8
(SPEC.md §2.11) -- are never written by the router at all.

Two consequences, one live and one structural.

**`mosbius_ota`'s `tail=` is read by nothing.** The symbol's template is
`template="name=X1 tail=2 bn=VGND bp=VAPWR"`, so every OTA instance carries a
`tail` property into the netlist, and `route.py` looks only at `w` and
`ratio`. Writing `tail=4` in the schematic changes the netlist and does not
change one bit of the bitstream.

This is masked by an unlucky coincidence: an all-zero cycler field decodes to
`step * (1 + 0)` = 2, exactly the symbol's default, so `tail=2` is
accidentally correct and only the other three values are silently wrong. The
masking is the dangerous part -- the bug cannot be found by trying the
default.

**A real differential pair has no way to set its tail at all.**
`mosbius_nmos`/`mosbius_pmos` expose only `w=`, so when two of them share a
source and `_allocate_fets` pass 1 pairs them onto `ndiffpair+`/`ndiffpair-`,
the tail current of the pair they have just formed is unreachable from the
schematic. `ctrl_dpn_tail` is the only thing that sets it, and nothing the
user can draw reaches that bit.

Fix, in two parts:

- Read `tail=` on `mosbius_ota` and emit `ctrl_otan_tail` -- a `TAIL_SETTING`
  table beside `WIDTH_SETTING`, keyed by role, with step=2.
- Decide how a diff pair's tail is expressed in the schematic at all. It is
  not a per-device property, since the two halves share one tail, which is
  why `w=`'s shape does not fit it. Worth weighing: a `tail=` on both halves
  that must agree, versus a separate symbol wired to the shared source node.

Either way the same rule applies that `R1` in `check.py` now enforces for
widths: a property that cannot reach the bitstream gets said out loud
rather than dropped.

## 4. A single OTA crashes the router

Raised 2026-08-21, found while writing §3.

Routing any design containing one `mosbius_ota` raises an unhandled
`KeyError: 'ota'` out of `_collect_touches`:

```
    side=ROLE_SIDE[role], pin=_pin_name(role, terminal))
         ~~~~~~~~~^^^^^^
KeyError: 'ota'
```

It looks like a missing dictionary entry and is not one. `ROLE_SIDE` maps a
role to *one* bus side, and the OTA is the only device that straddles both:

| terminal | crosspoint pin | side |
|---|---|---|
| `inp`  | `cfga_otan_inp`  | A |
| `outp` | `cfga_otan_outp` | A |
| `inm`  | `cfgb_otan_inm`  | B |
| `outm` | `cfgb_otan_outm` | B |

So side is a property of the *terminal*, not of the role, and no value put
into `ROLE_SIDE["ota"]` can be right. `_pin_name()` has the same shape --
it builds the `cfga_`/`cfgb_` prefix from `ROLE_SIDE[role]`.

Fix: make the side per (role, terminal). `DEVICE_TERMINALS` already maps a
terminal to its crosspoint, and a crosspoint's side is knowable from the bit
map, so both `ROLE_SIDE` and `_pin_name` can be *derived* from `bitmap.py`
rather than transcribed -- which is the discipline `route.py`'s own module
docstring already claims for its row tables ("so a bit-map correction there
can't silently drift out of sync with the router").

Why it survived: the only OTA test is
`test_two_ota_devices_reports_doesnt_fit`, and two OTAs raise in
`allocate_devices` before `_collect_touches` is ever reached. No test has
routed a single OTA.

Note for whoever takes this: the OTA's inputs reach only bus rows 1-3
(CLAUDE.md trap 6), so the row picker needs to respect that once it can get
far enough to matter.

## 5. Device allocation is decided by netlist order, and fails with a traceback

Raised 2026-08-21, found routing a hand-drawn SR latch.

`_allocate_fets` pass 2 hands the two independent slots (`nmos_a`/`nmos_b`)
to whichever requests come first in the netlist, then pass 3 gives the
diff-pair halves to whatever is left. Nothing consults where those devices'
*gates* have to land -- so whether a design routes can depend on the order
xschem happened to list its instances in.

The SR latch in `examples/srlatch/` is the worked case. Six devices, four
NMOS all sourced on `VGND`, so two of them necessarily take diff-pair
halves. As listed it routes: `M2`/`M4` take the independent slots and the
halves fall to `M5`/`M6`, whose gates are on `ua1` and `ua2`. Relist the
same six devices in a different order and:

```
KeyError: ('cfgb_dpn_inm', 6)
```

Not a `RouteError` -- a traceback out of `route_internal_net`.

**Why row 6 specifically, and why no pin choice avoids it.** The free rows
are `A{2,4,6}` and `B{1,3,5,6}`, so the only row free on *both* sides is 6.
An internal net touching devices on both sides is therefore forced onto row
6. Diff-pair inputs reach only rows 1-3 (CLAUDE.md trap 6). So:

> a diff-pair half's gate can never sit on an internal net that spans both
> bus sides.

In the latch that net is `net1`, the cross-coupling node, which gates
`M3`/`M4`. Moving Q from `ua3` to `ua4` does not help -- checked. The
constraint is about the internal net, not the package pin, which makes it
strictly harder to see than the `ua3`-as-a-gate problem
`examples/srlatch/README.md` already describes.

Two separate fixes, and the first is worth doing even alone:

- **Raise a real `RouteError`.** Name the device, the net, the row it
  needed, and say that diff-pair inputs are limited to rows 1-3 and why.
  Every crossing of `_MATRIX_BIT_BY_PIN_ROW` with a missing key is this
  same class -- an unreachable (pin, row) pair -- so the lookup wants
  wrapping once rather than guarding at each call site.

- **Allocate by constraint rather than by line order.** Give the
  independent slots to the devices whose gates sit on nets a diff-pair
  input cannot reach, and spend the halves on the ones that fit. That is
  a genuine ordering rule (SPEC.md Sec 3.4's "spend the constrained
  resource first"), not a heuristic: a two-sided internal net on a gate is
  a hard exclusion, knowable before any row is picked.

Note this interacts with sticky routing (SPEC.md Sec 3.2b): a better
allocator must not silently relocate an existing working design, so it
belongs behind the same stored-routing reuse as everything else.

## 6. Repeated findings repeat their whole explanation

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
