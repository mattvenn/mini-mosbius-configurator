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

## 3. Fix the unmatched pin-direction errors

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
(`netlist.py` skips lines starting with `*`). **Unverified** — batch mode with
`-q` doesn't print these messages at all, so confirming the fix means
netlisting from the GUI and watching the log.

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
