# Investigation: ring oscillator (Level-1 vs Level-2 vs real silicon)

**Status: open investigation, not a finished example.** Unlike
`examples/inverter/` and `examples/srlatch/`, nothing here is a polished
tutorial artifact -- this is a working note on a specific gap-closing
exercise, kept so it can be picked back up later without re-deriving
everything from scratch. No schematic or testbench file from this session
was committed (see "Reproducing this" below); this file records what was
found and how to redo it.

## The circuit

Bitstream `380088007001000010000404250109000400000040000014` decodes
(`python3 -m mosbius.cli decode 380088...0014`) to a 3-stage ring
oscillator: three inverting stages built from the six non-independent-slot
FETs (`nfeta`/`pfeta` w=4 as one stage, `dpn+`/`dpp+` and `dpn-`/`dpp-` as
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
is W=40 nf=8 -- an exact match. Any other width leaves the `nfeta`/`pfeta`
stage weaker than the two diff-pair stages. Note the router **silently
discards** a `w=` on a device it assigns to a diff-pair half (`TODO.md` §5), so
a schematic drawn at `w=1` throughout produces a 1x/1x/4x ring while looking
symmetric on screen.

**Three inverting stages is the longest odd ring this chip can build.** Only
four devices per polarity expose both a drain and a source/tail to the matrix:
`nfeta`, `nfetb`, `dpn+`, `dpn-` (and the PMOS mirror image). The current
mirror legs expose a single terminal (`out`) and the OTA is a fixed block, so
neither can serve as an inverter FET. Four stages would fit but is even, and
five is unreachable -- which makes three the practical ceiling.

## What was tried

Three simulation levels, in increasing fidelity:

| Level | What it models | Period | Frequency | vs. real silicon |
|---|---|---|---|---|
| Level-1 ideal | `mosbius_nmos`/`mosbius_pmos` generic symbols, direct net-to-net wiring, no switch matrix at all | 0.41ns | ~2.45GHz | ~82x too fast |
| Level-2 real switch matrix | the actual chip netlist (`mosbius.sym`/`mosbius.sch`) with real `tt_asw_3v3` transmission gates, config driven by `mosbius/spice.py` | 1.98ns | ~505MHz | ~17x too fast |
| Real silicon | — | ~33.3ns | ~30MHz | — |

Including the real transmission gates closed most of the gap (82x -> 17x
too fast), confirming the switch matrix's resistance/capacitance is the
dominant effect Level-1 leaves out (SPEC.md Sec 3.1b's whole point). The
remaining ~17x gap has specific, identified, untested causes -- see
"What's still open" below, not an unexplained mystery.

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
   (regex, or see `tools/gen_example_schematic.py` for the general
   pattern) to get each pin's exact coordinate, then place one
   `devices/lab_wire.sym` per pin, each labeled with that pin's own bus
   name (e.g. `lab=cfga_nfeta_d[6:1]`) touching the pin's exact
   coordinate. xschem expands a bus-width label into the individual
   per-bit net names on its own (confirmed working the same way
   `tb_mosbius_ringo.sch`'s own `bus_A[6:1]`-style labels do) -- this
   avoids hand-placing 192+ individual wires, which is exactly the kind
   of thing that silently floats a pin if one coordinate is wrong (it's
   bitten this project twice already; see `tools/gen_example_schematic.py`'s
   docstring).

3. **Never place new files inside `ttsky-mini-mosbius/`** (read-only
   submodule, per CLAUDE.md). Keep the testbench `.sch`/`.spice` files in
   `build/` (gitignored), and reference `mosbius.sym` with a bare
   relative filename (`C {mosbius.sym}`) while running xschem with its
   working directory set to `ttsky-mini-mosbius/xschem`.

   This is one of the few places a batch `docker run` is still the right
   tool. The everyday path is xschem's Netlist button (`TUTORIAL.md`), but
   that netlists the schematic you have open, into `simulation/` beside it
   -- no use for a generated testbench in `build/` that has to resolve
   `mosbius.sym` from the submodule's own directory:
   ```bash
   docker run --rm -v "$PWD:/work" -w /work/ttsky-mini-mosbius/xschem \
     hpretl/iic-osic-tools:latest --skip bash -lc \
     'export PDK=sky130A PDK_ROOT=/foss/pdks
      xschem --rcfile $PDK_ROOT/sky130A/libs.tech/xschem/xschemrc -n -q \
        -o /work/build /work/build/ring_l2.sch'
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

Why Level-2's ~505MHz is still ~17x faster than the real ~30MHz, roughly
in order of how likely each is to matter, not yet tested:

- **The 148 dropped-as-open switches were removed entirely**, not kept as
  small off-state parasitic capacitors. In reality every device stays
  physically connected to its bus segment whether its own switch is open
  or closed, so real silicon has loading on every bus segment this
  simulation strips out. This is the most likely single largest factor,
  and the natural next thing to try: re-add the dropped switches as small
  (fF-scale, not the 100pF used for the inverter's external-pin load)
  parasitic caps rather than deleting them outright.
- **No external pin/probe/PCB capacitance was modeled** -- this ring's
  observed nodes (`bus_A[1]`, `bus_A[3]`, `bus_B[2]`) are purely internal
  in this simulation. Unclear whether the real 30MHz measurement point
  was probed through an actual package pin (which would add real
  capacitance, the same effect modeled as 100pF for the inverter example)
  or observed some other way.
- **Only the "tt" (typical) process corner was tried**, not the real
  chip's actual corner -- process spread alone is usually a much smaller
  effect than the two above, but hasn't been ruled out.
