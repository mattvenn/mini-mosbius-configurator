# TODO — deferred work

Raised during the first outside-user run through `TUTORIAL.md` (2026-08-20),
drawing an inverter and heading for a 3-stage ring oscillator. Each item has
the context needed to act on it without re-deriving anything.

Numbers are stable, so the list starts at 2: item 1 (redraw the symbols) was
done on 2026-08-21. Other files cite these by number -- `CLAUDE.md` points at
§4 and §7, `examples/ringosc/README.md` at §5 -- so completed items are
removed without renumbering the rest.

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

## 3. Fix the unmatched pin-direction errors -- FIXED 2026-08-21, NEEDS GUI CONFIRMATION

Netlisting from the xschem GUI prints, once per device:

```
Error: Symbol mosbius_nmos.sym: Unmatched subcircuit schematic pin direction: g
    iopin <--> in
```

Cause: the `.sym` declares the pin `dir=in`, while the `.sch` wires it with
`devices/iopin.sym` (inout). Systematic across the library — every `dir=in`
pin is an `iopin` in its schematic: `g` on `mosbius_nmos`/`mosbius_pmos`,
`ibias` on `mosbius_nsink`/`mosbius_psource`, and `inp`/`inm`/`ibias` on
`mosbius_ota`.

Cosmetic, not blocking: the netlist is correct regardless, and the
hand-drawn inverter that triggered it routed to the exact reference bitstream
`080000004010000001000000000000000040000400000000`.

Fix: change those pins to `devices/ipin.sym`. The only netlist change is the
annotation `*.iopin g` -> `*.ipin g`, which nothing downstream reads
(`netlist.py` skips lines starting with `*`).

**Applied 2026-08-21** to `g` (nmos/pmos), `ibias` (nsink/psource) and
`inp`/`inm`/`ibias` (ota). Netlists verified byte-identical in batch. Still
needs someone to netlist from the GUI and confirm the log is clean, because
batch mode with `-q` does not print these messages at all -- and without `-q`
xschem does not exit, so there is no way to capture them non-interactively
either. Close this item once that's seen.

The same GUI netlist should also be free of two errors introduced by the
item-1 redraw and fixed alongside:

```
Error: Symbol mosbius_nmos.sym: schematic pin: b not in symbol
Error: Symbol mosbius_nmos.sym has 3 pins, its schematic has 4 pins
```

Cause: the body ties are supplied by the symbol's `extra` attribute, so they
are not symbol pins, but the schematics still declared them with
`devices/iopin.sym` -- and xschem's symbol/schematic consistency check does
not know about `extra`.

Two attempts failed before the right fix. `devices/lab_pin.sym` cleared the
pin-count errors but produced `Error: undriven node: b` instead, because
sky130's 4-terminal FETs declare their `B` terminal `dir=in` and so does
`lab_pin` -- no driver on the net. A custom `dir=inout` label did not help
either: xschem does not accept it as a driver for a net it thinks is
internal, and `extra` ports are invisible to that check.

The fix, and it is the obvious one in hindsight: **the device schematics now
instantiate the PDK's 3-terminal FETs** (`sky130_fd_pr/nfet3_g5v0d10v5.sym`,
`pfet3_g5v0d10v5.sym`) and pass the bulk as their `@body` template parameter
rather than wiring it. `D`/`G`/`S` sit at identical coordinates in the 3- and
4-terminal symbols, so only the bulk connection changed. For `mosbius_nmos`,
`mosbius_pmos` and the OTA's `bn` there is now no bulk net on the canvas at
all -- nothing left to call undriven. Where the net does survive
(`mosbius_nsink`/`mosbius_psource`'s `b` and the OTA's `bp`, which are also
the shared *source* node) it is driven by the FETs' `dir=inout` source pins.

This is what the 3-terminal PDK symbols were for, and the reason they never
showed the error themselves: their body is a parameter, not a node.

Verified: every `.subckt` interface, every instance line, every internal bulk
binding and the ring's bitstream are byte-identical to before the change.

Separately, the `Warning: open net: ua3/ua4/ua5/VDPWR/ibias` lines in the same
output are expected, not a bug — the template places all nine chip ports and
most designs use a few. Worth saying so in `TUTORIAL.md`, since it reads as a
problem on a first run.

## 4. Let the Python CLI drive the container

Netlisting means hand-writing a long `docker run` with four paths that have to
agree (host mount, `-w`, `--rcfile`, `-o`). A `mosbius netlist <sch>`
subcommand should derive all of them from the repo root and the schematic's
location.

Points to fold in, both hit on the first run:

- **Library path.** Schematics reference symbols bare (`C {mosbius_nmos.sym}`),
  so they only resolve if `xschem/mosbius_lib` is on the library path. The
  sky130A xschemrc already honours `XSCHEM_USER_LIBRARY_PATH` and appends it
  ([iic-osic-tools#7](https://github.com/iic-jku/iic-osic-tools/issues/7)) —
  set it and designs netlist from anywhere, instead of only from inside
  `mosbius_lib`. `TUTORIAL.md` step 1 doesn't say where to save the file and
  step 2's `-w` only works if it landed in `mosbius_lib`; this removes the
  trap rather than documenting it.
- **No accidental pulls.** Pass `--pull=never` so a missing image fails
  loudly instead of starting a ~20 GB download.
- **Say whether it worked.** The `docker run` above is silent: `-q` suppresses
  xschem's messages, so a successful netlist and a failed one look the same on
  the terminal, and xschem's exit status isn't a reliable signal either (it can
  exit 0 having written nothing). Today the only way to tell is to go looking
  for `build/<name>.spice` and check its mtime. The subcommand should report the
  outcome explicitly — the path written, its size, and the device count found —
  and fail loudly with a beginner-readable explanation when the file wasn't
  produced (most likely cause: a symbol that didn't resolve on the library path,
  see above).
- **One netlist location, not two.** The GUI's Netlist button and the `docker
  run` above write to *different directories*, and nothing reconciles them.
  xschem's `simuldir` proc (`xschem.tcl`: "point netlist_dir to simulation dir
  'simulation/' under current schematic directory") puts GUI netlists in
  `xschem/mosbius_lib/simulation/`, while the tutorial's `-o` puts batch
  netlists in `build/`. So you can netlist from the GUI as many times as you
  like and `build/<name>.spice` never changes -- and the router, pointed at
  `build/`, keeps reading a netlist from before your edits. Cost a real
  debugging session on 2026-08-20: `build/ring.mosbius.json` held a
  2-transistor inverter routing while `ring.sch` had been a 6-transistor ring
  oscillator for 20 minutes, and neither the GUI nor the docker command said
  anything was stale.
- **Refuse to reuse a stale routing.** `route_sticky()` compares topology
  hashes, which is the right check *once it reads the current netlist* -- it
  can't help when the netlist itself is the stale thing. `route`/`watch` should
  refuse (or warn loudly) when the `.mosbius.json` it is about to reuse is older
  than the `.spice` it is routing, and when the `.spice` is older than the
  `.sch` it came from.

## 5. Widths are silently dropped for devices that land on diff-pair halves

`route.py:469` applies a width only when the assigned role has one:

```python
for dev_name, role in roles.items():
    if role in WIDTH_SETTING:
```

`WIDTH_SETTING` covers the four independent FETs and the four mirrors. It does
not cover `dpn+`/`dpn-`/`dpp+`/`dpp-`, because those have no width bits on the
chip -- their geometry is fixed. So a device the router assigns to a diff-pair
half keeps whatever `w=` you wrote in the schematic in the *netlist*, has it
ignored in the *bitstream*, and nothing tells you.

This matters more than it sounds, because the fixed geometry is not `w=1`:

| device | sky130 instance | equivalent |
|---|---|---|
| `mosbius_nmos w=1` | W=10 nf=2 (`nmos_prog.sch` M1, the always-on slice) | 1x |
| `diff_n` input half (`dpn+`/`dpn-`) | W=40 nf=8 (`diff_n.sch` M1/M2) | **w=4** |
| `mosbius_pmos w=1` | W=30 nf=4 | 1x |
| `diff_p` input half (`dpp+`/`dpp-`) | W=120 nf=16 (`diff_p.sch` M3/M4) | **w=4** |

`nmos_prog` is a 1x always-on slice plus switchable 1x and 2x slices, so its
maximum, `w=4`, is W=40 nf=8 -- an exact match for the diff-pair half. That is
why `examples/ringosc/README.md`'s measured bitstream uses `nfeta`/`pfeta` at
`w=4`: at any other width the stages are mismatched. (Matched in W/L, not in
parasitics -- the programmable FET's 2x and 1x slices sit behind drain
switches, the diff-pair half doesn't.)

Found by routing a hand-drawn 3-stage ring: with `w=1` on all six devices, the
two stages on `nfeta`/`nfetb` come out 1x and the third, forced onto
`dpn+`/`dpp+`, comes out 4x. The design looks symmetric in the schematic and
isn't on silicon.

Fix: the router should report the width it actually programmed per device, and
say plainly when a `w=`/`ratio=` was discarded because the assigned role has no
width bits -- naming the role and its fixed equivalent width, so the user can
match the other stages to it deliberately.

Related: the Level-1 simulation netlists every device at its schematic `w=`, so
it simulates a symmetric ring the chip will not build. That is a second,
independent reason Level-1 misses -- on top of the missing switch matrix that
item 2 and `examples/ringosc/README.md` already quantify.

## 6. W2 fires on every internal node of a multi-stage design

`check.py:226`'s `_check_w2_floating_crosspoint` builds its graph from closed
switches only. A transistor channel is not an edge, so any net that reaches a
rail *through a device* rather than through the matrix looks floating.

Its docstring already anticipates half of this -- it anchors on the `ua[]` pins
as well as the rails, specifically so W2 doesn't "fire on nearly every signal
node in nearly every design ... which teaches a beginner to ignore warnings
rather than trust them". That fix covers inputs and outputs. It does not cover
*internal* nodes of chained stages, which is exactly what a ring oscillator is.

The 3-stage ring produces eight W2 warnings for two nets:

```
net1 -> xpt_nfeta_d, xpt_pfeta_d, xpt_dpn_inp, xpt_dpp_inp
net2 -> xpt_nfetb_g, xpt_pfetb_g, xpt_dpn_outp, xpt_dpp_outp
```

Both are ordinary CMOS inverter outputs. The advice W2 gives ("give this net a
DC path to a rail or a pin") is wrong for them, and it is repeated once per
crosspoint rather than once per net.

Two things to fix, in order of value:

1. **Don't fire when the net is driven.** A net that reaches a rail through a
   transistor whose own terminals are routed is an output, not a float. Needs
   the check to walk device channels, not just switches.
2. **Group by net.** Report the net once, listing its crosspoints, instead of
   N nearly-identical warnings.

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
