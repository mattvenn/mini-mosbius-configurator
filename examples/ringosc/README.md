# Investigation: ring oscillator (as drawn vs as routed vs real silicon)

**Status: open investigation, not a finished example.** Unlike
`examples/inverter/` and `examples/srlatch/`, nothing here is a polished
tutorial artifact -- this is a working note on a specific gap-closing
exercise, kept so it can be picked back up later without re-deriving
everything from scratch. The schematic (`ring.sch`) and a testbench
(`tb_ring.sch`, modeled on `examples/inverter/tb_inverter.sch`) are both
committed, but `tb_ring.sch` has not actually been run yet -- this dev
host OOMs on the full switch matrix a free-running ring needs (see
CLAUDE.md/[[ring_oscillator_l2_sim]]), so it needs a higher-RAM machine.
This file records what was found and how to pick the rest of it up.

## The circuit

Bitstream `380088007001000010000404250109000400000040000014` decodes
(`python3 -m mosbius.cli decode 380088...0014`) to a 3-stage ring
oscillator: three inverting stages built from the six non-independent-slot
FETs (`nmos_a`/`pmos_a` w=4 as one stage, `ndiffpair+`/`pdiffpair+` and `ndiffpair-`/`pdiffpair-` as
the other two, each pair standalone-tied to its own rail per CLAUDE.md
trap #3), wired in a loop: `ua[2] -> ua[1] -> ua[4] -> ua[2]`. Three
inversions around a closed loop is odd, so the loop has no stable fixed
point -- it free-runs.

This bitstream has been loaded onto real silicon and **measured at ~30MHz**.

### Why `w=4`, and why three stages is the maximum

Both of these look like arbitrary choices in the bitstream above. Neither is.

**`w=4` is the only width that makes the stages match.** The diff-pair halves
have no width bits -- their geometry is fixed at W=40 nf=8 for NMOS
(`diff_n.sch` M1/M2) and W=120 nf=16 for PMOS (`diff_p.sch` M3/M4). The
programmable FET is a 1x always-on slice plus switchable 1x and 2x slices
(`nmos_prog.sch`), so `mosbius_nmos w=1` is W=10 nf=2 and its maximum, `w=4`,
is W=40 nf=8 -- an exact match. Any other width leaves the `nmos_a`/`pmos_a`
stage weaker than the two diff-pair stages. Note that a `w=` on a device the
router assigns to a diff-pair half cannot be programmed at all -- those halves
have no width bits -- so a schematic drawn at `w=1` throughout produces a
1x/1x/4x ring while looking symmetric on screen. The router used to drop that
`w=` in silence; as of 2026-08-21 it warns (`check.py`'s `R1`) and reports the
width every device is actually built at.

**Three inverting stages is the longest odd ring this chip can build.** Only
four devices per polarity expose both a drain and a source/tail to the matrix:
`nmos_a`, `nmos_b`, `ndiffpair+`, `ndiffpair-` (and the PMOS mirror image). The current
mirror legs expose a single terminal (`out`) and the OTA is a fixed block, so
neither can serve as an inverter FET. Four stages would fit but is even, and
five is unreachable -- which makes three the practical ceiling.

## The schematic

`ring.sch` is a hand-drawn 3-stage ring. As of 2026-08-24 it builds the
*same topology* as the measured bitstream above, not a different one --
`nmos_a`/`pmos_a` for the first inverting stage, `ndiffpair+`/`pdiffpair+`
and `ndiffpair-`/`pdiffpair-` (each pair standalone-tied to its own rail,
no `mosbius_ntail`/`mosbius_ptail` drawn, per CLAUDE.md Trap #3) for the
other two, wired in the same loop: `ua2` -> `ua1` -> `ua4` -> `ua2`. Open
it in xschem with `xschem/mosbius_lib` on the library path, press Netlist,
and route what it writes:

```
$ python3 -m mosbius.cli route build/ring.spice
OK -- no errors or warnings (1 info note hidden, use --verbose).

Device roles:
  XM1          -> nmos_a        w=4
  XM2          -> pmos_a        w=4
  XM3          -> ndiffpair+    w=4 (fixed)
  XM4          -> ndiffpair-    w=4 (fixed)
  XM5          -> pdiffpair+    w=4 (fixed)
  XM6          -> pdiffpair-    w=4 (fixed)

Bitstream: 380000007001000010000404250109000400000040000014
```

Every device is drawn at `w=4` for the reason given above: `ndiffpair+`/
`ndiffpair-`/`pdiffpair+`/`pdiffpair-` cannot be anything else, so the
other stage has to be brought up to match them rather than the other way
round. Drawn at `w=1` the router now says so out loud instead of quietly
building a mismatched ring (`check.py`'s `R1`).

**This reproduces the measured design's device roles and wiring exactly,
but not its literal bitstream -- compare the two hex strings above.** Every
hex digit matches except the third byte (`00` here vs `88` measured),
which decodes (`mosbius.cli decode`) to one difference:
`ndiffpair+`/`ndiffpair-`'s `shared_source_tied_to_VGND` (and the PMOS
pair's `..._VAPWR`) reads `False` here, `True` in the measured design.
Both give the diff pair's shared source the same final DC connection (its
own rail) -- the difference is *which switch* makes that connection: the
measured design uses `ctrl_dpn_source`/`ctrl_dpp_source`, the chip's
dedicated rail-tie for a diff pair whose source is wired straight to
VGND/VAPWR (CLAUDE.md Trap #3's "each half is an ordinary common-source
FET"); routing `ring.sch` here instead ties the pair's shared source
through the general-purpose bus/crosspoint switches, because that is how
this router's allocator resolves two same-polarity FETs sharing an
*internal* net (SPEC.md §3.4's "spend the constrained resource first").

Drawing `ring.sch` the other way -- each diff-pair half's source wired
directly to its rail instead of to each other -- does reach
`ctrl_dpn_source`/`ctrl_dpp_source`, but costs the pairing: with `nmos_a`
already holding the only other independent-slot claim, the router's
allocator is free to place one of `ndiffpair+`/`ndiffpair-`'s two
candidate FETs in the remaining `nmos_b` slot instead of pairing them,
which breaks this ring's loop. That was tried and confirmed while building
this example (2026-08-24) -- a real allocator behavior, not a drawing
mistake to fix. Since the two switch paths carry different parasitics,
this ~1-bit-off routed simulation will not land on exactly the same
frequency as the literal measured bitstream; for a bit-exact comparison,
see "Exact comparison" below.

`ring.sch` also brings only `ua1` out as a loop node touching a real
package pin -- same as the measured bitstream, which also has only `ua1`
among its three loop nodes on a real pin (`ua4`/`ua2` are internal bus
rows, per the "Nets" table `mosbius.cli decode` prints). So unlike the
pre-2026-08-24 version of this schematic, there is no known reason to
expect this one's pad loading to differ from the measured design's.

## Exact comparison

To simulate the *literal* measured bitstream -- bit-for-bit, not just the
same device roles -- skip routing `ring.sch` and build the routed
subcircuit directly from the known-good bitstream, since `mosbius simulate`
only ever reads a `"bitstream"` field out of its input JSON:

```bash
python3 -c "
import json
json.dump({'bitstream': '380088007001000010000404250109000400000040000014'},
          open('build/ring_measured.mosbius.json', 'w'))
"
python3 -m mosbius.cli simulate build/ring_measured.mosbius.json
```

This writes `build/ring_measured_routed.spice`, a self-contained
`.subckt ring_measured_routed` with the same 9-pin port list as
`ring.sch`'s own routed output -- drop it into `tb_ring.sch` in place of
`ring_routed` (or point a copy of the testbench's `x2` instance at it) for
the number that is directly comparable to the ~30MHz silicon measurement.

## What was tried

Successive stages of the investigation, in increasing fidelity:

| What it models | Period | Frequency | vs. real silicon |
|---|---|---|---|
| As drawn: `mosbius_nmos`/`mosbius_pmos` generic symbols, direct net-to-net wiring, no switch matrix at all | 0.41ns | ~2.45GHz | ~82x too fast |
| Switch matrix only: the actual chip netlist (`mosbius.sym`/`mosbius.sch`) with real `tt_asw_3v3` transmission gates, config driven by `mosbius/spice.py`, but no row coupling, bus-wire capacitance or pads | 1.98ns | ~505MHz | ~17x too fast |
| As routed, what `mosbius simulate` ships today: the above plus row-coupling capacitance, bus-wire capacitance, and real pad models | ~26.1ns | **~38.33MHz** | ~1.28x too fast |
| Real silicon | ~33.3ns | ~30MHz | — |

Including the real transmission gates closed most of the gap (82x -> 17x
too fast), confirming the switch matrix's resistance/capacitance is the
dominant effect drawing alone leaves out (SPEC.md Sec 3.1b's whole point).
Adding the parasitics the matrix sits in -- row coupling, bus-wire
capacitance, pads -- closed nearly all of the rest, 17x -> 1.28x. That
last combination is what `mosbius simulate` emits now, so the middle row
is history rather than something you can reproduce from the current tool;
it is kept because the size of each step is the actual result here.

## Reproducing this

Nothing from this exercise was committed to `build/` (gitignored) or
anywhere else, so redoing it means rebuilding from these steps:

1. **`mosbius.sym`'s pin list already matches `mosbius/spice.py`
   exactly.** `ttsky-mini-mosbius/xschem/mosbius.sym` exposes all 192
   config bits as individually-named bus pins (`cfga_nfeta_g[6:1]`,
   `ctrl_dpn_source`, etc.) using the exact same names
   `mosbius/bitmap.py`/`mosbius/spice.py` already use. `spice.py`'s
   `render_config_spice(config)` was built for exactly this pairing.

2. **Build a testbench schematic wiring every `mosbius.sym` pin to a
   self-labeled net.** Parse `mosbius.sym`'s `B` (pin box) lines directly
   with a regex to get each pin's exact coordinate -- a `B` line is
   `B 5 <x1> <y1> <x2> <y2> {name=<pin> dir=...}`, and the pin sits at
   the box's centre. Then place one
   `devices/lab_wire.sym` per pin, each labeled with that pin's own bus
   name (e.g. `lab=cfga_nfeta_d[6:1]`) touching the pin's exact
   coordinate. xschem expands a bus-width label into the individual
   per-bit net names on its own (confirmed working the same way
   `tb_mosbius_ringo.sch`'s own `bus_A[6:1]`-style labels do) -- this
   avoids hand-placing 192+ individual wires, which is exactly the kind
   of thing that silently floats a pin if one coordinate is wrong. That
   has bitten this project twice: xschem merges net names only across wire
   segments that *genuinely touch*, so a coordinate that is off by one
   produces a schematic that looks right, netlists without complaint, and
   has an unconnected pin in it. Generate the coordinates, never type
   them.

3. **Never place new files inside `ttsky-mini-mosbius/`** (read-only
   submodule, per CLAUDE.md). Keep the testbench `.sch`/`.spice` files in
   `build/` (gitignored), and reference `mosbius.sym` with a bare
   relative filename (`C {mosbius.sym}`) while running xschem with its
   working directory set to `ttsky-mini-mosbius/xschem`.

   The working directory is the load-bearing part, not the container.
   xschem resolves a bare symbol name against where it is running from, so
   whichever way you netlist, it has to be running in
   `ttsky-mini-mosbius/xschem`. The GUI would do just as well: start xschem
   from that directory, open `build/ring_routed.sch`, press Netlist, and read
   the result from whatever `netlist_dir` is in force -- note this step is
   the one case that does *not* run from the repo root, so the repo's own
   `xschemrc` does not apply to it.

   The batch form is written out here only because every other step of this
   flow is scripted -- the testbench is generated (step 2) and the netlist
   is post-processed (step 4) -- so a manual button press in the middle
   would be the odd one out. For drawing a circuit by hand, use the Netlist
   button; see `TUTORIAL.md`.
   ```bash
   docker run --rm -v "$PWD:/work" -w /work/ttsky-mini-mosbius/xschem \
     hpretl/iic-osic-tools:latest --skip bash -lc \
     'export PDK=sky130A PDK_ROOT=/foss/pdks
      xschem --rcfile $PDK_ROOT/sky130A/libs.tech/xschem/xschemrc -n -q \
        -o /work/build /work/build/ring_routed.sch'
   ```
   Referencing `mosbius.sym` by an *absolute* path instead breaks
   xschem's resolution of its sibling symbols (`tt_asw_3v3`, `nmos_prog`,
   `diff_n`/`diff_p`, `mirror_n`/`mirror_p`, `ota_n` all came back
   "IS MISSING" in the netlist until this was fixed).

4. **The full switch matrix (188 `tt_asw_3v3` instances + 6 real device
   blocks) OOMs ngspice in this environment** -- observed >1GB resident
   just from `.lib` loading plus the full device count, hitting a hard
   host memory ceiling (~1.9GiB) even for a 20ns transient window with a
   minimal `save` list. Fix: post-process the netlisted output, keeping
   only the `tt_asw_3v3` instances whose control net is driven HIGH per
   the target `SwitchConfig.bits` (i.e. actually closed) and dropping the
   rest. This is the same "skip electrically-irrelevant switches"
   technique M2 used by hand for the inverter's original ~55ns check
   (SPEC.md Sec 3.1b). For this bitstream it cut 188 switch instances
   down to 40 kept, and the simulation then ran in ~540MB.

5. **`ngspice`'s `wrdata` command can't parse bracketed vector names**
   (`v(bus_a[1])` fails with "bad `v()` syntax") even though `save
   v(bus_a[1])` and plotting the same vector work fine. Workaround:
   `save v(...)` as usual, then `set filetype=ascii` followed by `write
   file.raw` with **no explicit vector arguments** (it writes whatever was
   already `save`d) -- this sidesteps `write`/`wrdata` needing to
   re-parse the bracketed name at all.

## What's still open

The list below was written when the routed model stood at ~505MHz, ~17x
too fast. The first two items were then acted on and are **closed** --
they are what took the number to ~38.33MHz, ~1.28x. They are kept here
because which guesses turned out to matter is the useful part:

- **Closed. The 148 dropped-as-open switches were removed entirely**,
  not kept as small off-state parasitic capacitors, and every device
  stays physically connected to its bus segment on real silicon whether
  its own switch is open or closed. Re-adding that loading as row-coupling
  capacitance (~43fF per switch) was the largest single correction, as
  predicted.
- **Closed. No external pin/probe/PCB capacitance was modeled.** Real pad
  models on the package pins a config actually uses are now part of what
  `mosbius simulate` emits -- and they carry the analog mux switch too:
  `pad_model` holds one transmission gate held on (this project's mux
  slot) plus 15 held off (the deselected slots' loading on the same pad
  line).
- **Still open. Only the "tt" (typical) process corner was tried**, not
  the real chip's actual corner. At ~1.28x this is now a plausible size
  for the whole remaining gap rather than a footnote, so it is the next
  thing to try.
