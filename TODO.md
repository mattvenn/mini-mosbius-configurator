# new todo

an annoying ux issue is that xschem wants to save simulations in its own directory. and they really want to be in ./build . There needs to be an easy workflow for someone to be able to start xschem, load the templates and see the symbols, then export the netlist and run the docker all in one place. I'm having to remember to copy the spice netlist from xdschem/mosbius/simulation -> build, then run the docker and the python.

(Half of this is answered as of 2026-08-21: there is no copying and no docker
step any more. Press Netlist in xschem, then point the router straight at
`<schematic dir>/simulation/<name>.spice` -- see §4. What remains is the rest
of the ask: launching xschem with the library path already set, so the whole
loop is one place.)

# TODO — deferred work

Raised during the first outside-user run through `TUTORIAL.md` (2026-08-20),
drawing an inverter and heading for a 3-stage ring oscillator. Each item has
the context needed to act on it without re-deriving anything.

Numbers are stable, so the list starts at 2: items 1 (redraw the symbols),
3 (pin-direction errors), 4 (netlisting via the container), 5 (widths dropped
on diff-pair halves) and 6 (W2 firing on every internal node) were resolved
and removed on 2026-08-21. Other files cite these by number, so completed
items are removed without renumbering the rest -- and a citation of a number
that is no longer here means the thing it described is fixed, not that the
reference rotted.

## 2. Level-2 simulation of the routed design

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


## 7. Library symbols emit an invalid subcircuit call

Every `mosbius_*.sym` declares `type=subcircuit`, but the format string omits
`@spiceprefix`:

```
ours:    format="@name @pinlist @b @symname w=@w"  template="name=M1 w=1 b=VGND"
sky130:  format="@spiceprefix@name @pinlist sky130_fd_pr__@model L=@L W=@W ..."
         template="name=M1 ... spiceprefix=X"
```

Four of the five templates default to `name=M1` (`mosbius_nmos`,
`mosbius_pmos`, `mosbius_nsink`, `mosbius_psource`), so instances netlist as
`M1 ua1 net1 VGND VGND mosbius_nmos w=1`. `M` is ngspice's MOSFET primitive, so
the last token has to name a `.model` -- but `mosbius_nmos` is a `.subckt`.
Verified against the real netlist with the real PDK models loaded:

```
warning, can't find model 'mosbius_nmos' from line
    m1 in out 0 0 mosbius_nmos w=1
could not find a valid modelname
    Simulation interrupted due to error!
```

Only `mosbius_ota.sym` escapes it, by accident: its template is `name=X1`.
This is why the *inner* device netlists correctly as `XM1` -- sky130's own
symbol includes `@spiceprefix`, ours doesn't.

Fix, matching sky130's convention:

```
format="@spiceprefix@name @pinlist @b @symname w=@w"
template="name=M1 w=1 b=VGND spiceprefix=X"
```

That emits `XM1 ua1 net1 VGND VGND mosbius_nmos w=1` and keeps the familiar
M1/M2 names visible in the schematic. Downstream consequence:
`mosbius/netlist.py` takes the first token as the instance name, so devices
become `XM1`..`XM6`; that changes the `device_roles` keys and the
`design_topology_hash`, forcing one re-route. The bitstream itself does not
change.

Note this is a **second, independent cause** of the "could not find a valid
modelname" error that CLAUDE.md trap 7 attributes to `ngbehavior=hsa`. Both are
real; seeing that message does not by itself mean `.spiceinit` is at fault.

## 8. Regenerate the example schematics for the new symbol geometry

Raised 2026-08-21, immediately after the item-1 redraw.

**Only `examples/srlatch/srlatch.sch` is left.** The two inverter files were
replaced with hand-drawn versions on 2026-08-21 (`examples/inverter/` now
holds a real schematic drawn in xschem, and `inverter_w4.sch` is that same
file with one `w=` changed), and `examples/ringosc/ring.sch` was added the
same way. That leaves the srlatch as the last generated file still on the
old geometry.

`examples/inverter/inverter.sch`, `examples/inverter/inverter_w4.sch` and
`examples/srlatch/srlatch.sch` were produced by
`tools/gen_example_schematic.py` against the *old* pin coordinates (g at
`(-60,0)`, d at `(60,-60)`, s at `(60,60)`, b at `(0,80)`). Every symbol now
has pins at `nmos3`'s coordinates instead, so those files' wires end nowhere
near the pins.

Verified 2026-08-21: *every* pin is now dangling. The inverter netlists as

```
nfeta_0 net1 net2 net3 VGND mosbius_nmos w=1
pfeta_1 net4 net5 net6 VAPWR mosbius_pmos w=1
```

-- six pins, six auto-named nets, no connectivity at all; the srlatch gives
nineteen. Routing does fail, but on the first thing it happens to run out of:

```
DOESN'T FIT -- no free bus_A[] row left for 'net4'
```

which says nothing about the actual problem. Another instance of item 9.

These are generated, not hand-drawn, so the fix is to re-run the generator
rather than to edit them:

```bash
python3 tools/gen_example_schematic.py <netlist.spice> <out.sch>
```

The input each one was built from is the wrinkle -- `build/` is gitignored, so
the source netlists are not in the repo. Recover each from its example README's
netlist listing, or from the committed bitstream via `schgen.generate_schematic`
(that is a different layout algorithm but the same pin tables, and it is what
`mosbius decode` would draw).

While regenerating, check the result actually netlists in the container before
committing it -- `examples/*/README.md` quote device connectivity that has to
keep matching.

Related: the same geometry change broke a hand-drawn `ring.sch` in a way that
took a routing failure to notice (see item 9).

Note the hand-drawn route taken for the inverter and the ring is not a
rejection of the generator -- `gen_example_schematic.py` reads the pin
coordinates out of the `.sym` files at run time, so it would produce correct
geometry today. It is simply that a schematic a person drew is the better
artifact for an example a person is meant to learn from.

## 9. Diagnose a probable drain/source swap instead of "doesn't fit"

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

## 10. Tail currents never reach the bitstream

Raised 2026-08-21, found while fixing §5.

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

Either way §5's rule applies, and it is now enforced for widths by `R1` in
`check.py`: a property that cannot reach the bitstream gets said out loud
rather than dropped.

## 11. A single OTA crashes the router

Raised 2026-08-21, found while writing §10.

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
