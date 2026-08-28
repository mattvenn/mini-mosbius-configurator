# Investigation: ring oscillator (as drawn vs as routed vs real silicon)

*Shared background for all four examples -- as drawn vs as routed, the
testbench idiom, capacitive loading, the common gotchas -- is in
[`../README.md`](../README.md).*

**Status: open investigation, not a finished example.** Unlike
`examples/inverter/` and `examples/srlatch/`, nothing here is a polished
tutorial artifact -- this is a working note on a specific gap-closing
exercise, kept so it can be picked back up later without re-deriving
everything from scratch. `ring.sch` and `tb_ring.sch` are both committed
and both run: the testbench takes about two minutes in the
IIC-OSIC-TOOLS container. (An earlier version of this note said it OOMed
and needed a higher-RAM machine. That was the hand-built full-matrix deck
described under "Reproducing this", not what `mosbius simulate` emits.)

## The circuit

Three inverting stages in a loop, plus an output buffer -- eight
transistors, which is every usable single FET the chip has.

```
    ua1 -> net1 -> ua2 -> ua1          the loop, three inversions
    ua1 -> ua3                         the buffer
```

Three inversions round a closed loop is odd, so the loop has no stable
fixed point and free-runs. The buffer is a fourth inverter tapping `ua1`
and driving `ua3`, which is what anything outside the chip measures.

**Why there is a buffer.** Without it you have to observe a loop node,
and a loop node is inside the feedback path: a scope probe there changes
the oscillator instead of measuring it. Measured on this circuit, 100pF
on a loop node stops the drawn ring oscillating outright (it latches at
~1.6V) and even 1pF drags it from 2.5GHz to 1.5GHz with the swing already
collapsing. With the buffer, the load sits on `ua3`, outside the loop, so
a probe capacitance models a probe again -- the same situation as
`examples/inverter/`. The loop pays only the buffer's gate capacitance,
which is a real on-chip load rather than an invented one.

**But the buffer cannot drive that load, and that is a result too.** A
ring stage drives one gate, tens of fF. The buffer drives `cload` plus a
bond pad -- 15pF, three orders of magnitude more -- with an identical
`w=4` device. Scaling `examples/inverter/`'s own measurement (a `w=1`
inverter takes 8.9ns to slew 10pF, so `w=4` takes about 2.2ns), the drawn
ring's 240ps half-period gives it about a tenth of the time it needs.
Measured swings, steady state:

| node | swing | centre |
|---|---|---|
| `loop_drawn` | 3.463 V | 1.694 V |
| `out_drawn` | 0.249 V | 1.941 V |
| `loop_routed` | 2.630 V | 1.610 V |
| `out_routed` | 1.550 V | 1.323 V |

The oscillator is healthy -- the loop node swings past both rails. Only
the buffered output is squashed, and the routed branch, with 8.6ns per
half period, gets most of the way there. Real chips solve this with a
tapered chain of progressively larger inverters; this chip has no
transistors left to build one, since all eight usable single FETs are
already committed.

**So frequency is measured on the loop nodes, not the outputs.** That is
not a preference. `out_drawn` spans 1.82-2.07V and never properly crosses
the 1.5V trigger, so the same deck reported 58.3MHz one run and 44.0MHz
the next with no electrical change. Counted over the whole steady-state
window, `loop_drawn` crosses 1.5V 74 times with **zero** spread in period,
`out_drawn` 8 times with +-4.1ps. The `.meas` lines trigger on
`loop_drawn`/`loop_routed`; `out_drawn`/`out_routed` and their `cload`
stay as the pin view, which is a real answer about driving an external
load off this chip.

**Which loop nodes carry pads.** `net1` is not named after a package pin,
and `route.py` guarantees such nets never land on a bonded bus row -- so
it carries only the row's own ~0.9pF of wire capacitance. `ua1` and `ua2`
do carry pads. You cannot make all three internal: only bus row 6 is free
of a bond wire on *both* sides, so at most one internal net can span the
two bus sides, and with eight devices split four per side the loop cannot
avoid spanning more than once. The router says so rather than quietly
moving one onto a pin:

```
DOESN'T FIT -- 'net1' spans both bus sides and no row can join them
  ... Free on both sides here: bus row 6.
  The terminals above can share only bus rows 1, 2 and 3.
```

`mosbius route` prints which nets ended up bonded -- see "The schematic".

**The measured-silicon reference is a different circuit.** Bitstream
`380088007001000010000404250109000400000040000014` -- a three-stage ring
with no buffer, all three loop nodes on package pins -- has been loaded
onto real silicon and **measured at ~30MHz**. Everything below that
compares against ~30MHz is comparing against that bitstream, not against
this schematic. See "Exact comparison".

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

That leaves exactly one NMOS and one PMOS over, which is exactly one
inverter, which is the buffer. Nothing is spare afterwards: all eight
usable single FETs are committed, so this circuit cannot also widen a
stage. The leftovers are diff-pair halves at fixed W=40 nf=8 and W=120
nf=16 -- identically `w=4` -- so the buffer comes out the same strength as
a stage without any compromise.

## The schematic

`ring.sch` is hand-drawn. Open it in xschem launched from the repo root,
press Netlist, and route what it writes:

```
$ python3 -m mosbius.cli route build/ring.spice
OK -- no errors or warnings (1 info note hidden, use --verbose).

Device roles:
  XM1          -> nmos_a        w=4
  XM2          -> pmos_a        w=4
  XM3          -> nmos_b        w=4
  XM4          -> pmos_b        w=4
  XM5          -> ndiffpair+    w=4 (fixed)
  XM6          -> pdiffpair+    w=4 (fixed)
  XM7          -> ndiffpair-    w=4 (fixed)
  XM8          -> pdiffpair-    w=4 (fixed)

Bus rows:
  net1     bus_A[2]
  ua1      bus_A[1] + bus_B[1]   package pin ua1 -- bond pad + analog mux
  ua2      bus_A[3] + bus_B[3]   package pin ua2 -- bond pad + analog mux
  ua3      bus_A[5] + bus_B[5]   package pin ua3 -- bond pad + analog mux

Bitstream: 3f008803f004001401000210188406000050040100000019
```

The "Bus rows" section is what tells you the pad story for a given
routing. `net1` landed on a bare row; `ua1`, `ua2` and `ua3` did not, and
`ua3` could not -- it is the output, so it has to be reachable.

Every device is drawn at `w=4` for the reason given above: the diff-pair
halves cannot be anything else, so the programmable FETs have to be
brought up to match rather than the other way round. Drawn at `w=1` the
router says so out loud instead of quietly building a mismatched ring
(`check.py`'s `R1`).

Which device becomes which hardware slot is the allocator's choice, not
the drawing's, and it is not stable against unrelated edits -- the buffer
here landed on `nmos_b`/`pmos_b` and the loop's third stage on the
diff-pair halves, but an earlier arrangement of the same circuit came out
the other way round. Read the roles from the route output rather than
assuming.

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
`ring.sch`'s own routed output -- point a copy of the testbench's `x2`
instance at it for the number directly comparable to the ~30MHz silicon
measurement.

Two things to change in that copy, because the measured bitstream is the
unbuffered circuit: its loop nodes are `ua[1]`, `ua[2]` and `ua[4]`, so
`out_routed` has to move to one of those rather than `ua3`, and
`Cload_routed` has to come off, since observing a loop node means the
probe is back inside the feedback path. That is the comparison being made
-- the measured silicon had no buffer to hide behind.

## What was tried

Successive stages of the investigation, in increasing fidelity. The first
four rows are the *unbuffered, all-pins* circuit, which is what the ~30MHz
silicon measurement is of:

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

### What the committed schematic measures now

`ring.sch` is no longer that circuit -- it has the buffer, and one of its
three loop nodes is an internal net. Running `tb_ring.sch` as committed,
measured on the loop nodes:

```
freq_drawn  = 2.083 GHz    (period 480.2 ps)
freq_routed = 43.89 MHz    (period 22.78 ns)
```

`freq_drawn` sits below the 2.45GHz in the table because the loop now
carries the buffer's gate capacitance, which the unbuffered version did
not have. `freq_routed` is ~1.46x the ~30MHz silicon figure, but that
figure is of a *different* circuit -- unbuffered, all three loop nodes on
pins -- so the two are not directly comparable. This circuit has never
been measured on silicon.

**The experiment worth running.** Route the same eight devices with every
loop node on a package pin, and compare against this one, where `net1` is
internal. Same devices, same widths, same topology, same tail ties, same
observation point on `ua3` -- only one bond pad's worth of bus row
differs. Two bitstreams, one board, a frequency counter. That would test
the pad and mux model directly, which nothing in this project currently
does: `examples/inverter/README.md`'s conclusion that the bond pad
dominates rests on simulation alone.

The simulated ratio for that pair has **not** been measured soundly yet.
An earlier attempt gave 1.7x, but it was measured on `out_routed`, which
is the one node that does not reliably cross the trigger level -- see
above. Redo it with the measures on the loop nodes before quoting a
number.

## Reproducing this

This section is **history**. It describes the hand-built full-matrix deck
used before `mosbius simulate` existed -- the "switch matrix only" row of
the table above. You do not need any of it to run this example today;
`sh tools/regenerate_routed.sh examples/ringosc/ring.sch` does the whole
job in Python. It is kept because the traps in it are real and would cost
someone a day to rediscover:

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
  thing to try. Every testbench here hardcodes `corner=tt` on its
  `sky130_fd_pr/corner.sym`.
- **Still open, and now the biggest one. The pad model has never been
  checked against silicon.** The committed schematic and an all-pins
  version of the same circuit differ by one bond pad; measuring both on a
  demoboard would test the pad and mux model directly, which nothing in
  this project currently does. The simulated ratio to hold them to still
  needs measuring properly -- see "What the committed schematic measures
  now".

## How `tb_ring.sch` is set up

The sheet's ngspice block is bare; the reasoning behind it lives here.

**Load capacitors on `ua3` only.** `Cload_drawn`/`Cload_routed` are both
`'cload'` with `.param cload=10p`, one scope probe's worth, held equal on
both instances so the only difference between `out_drawn` and `out_routed`
is the chip -- the same convention as every other testbench here, and
[`../README.md`](../README.md)'s "Capacitive loading" explains why they are
equal and why the routed one is not zero. There are
no capacitors on the loop nodes, for the reason given at the top of this
file: a cap inside the feedback path changes the oscillator rather than
measuring it. The buffer is what makes a probe load meaningful here at
all.

**Labels, and what is measured where.** `ua2` is
`loop_drawn`/`loop_routed`, `ua3` is `out_drawn`/`out_routed`. The two
`.meas` lines trigger on the loop nodes, for the reason given at the top
of this file: the buffered output does not reliably cross 1.5V, so
measuring there gave a different frequency on consecutive identical runs.
Both graphs show the loop and the output of their own branch together, so
the attenuation is visible on the sheet. Port order is `ibias ua1 ua2 ua3 ua4 ua5 ...`,
so the `lab_wire` on the second port is the loop and the third is the
output. Getting these one position out is easy and quiet: it put the
startup kick on an unconnected pin once, and the deck still ran.

**Two `tran` runs, not one.** The branches oscillate ~40x apart, GHz
versus tens of MHz, and no single analysis serves both: a step fine enough
to resolve `x1` makes `x2`'s window enormous, and a window long enough for
`x2` leaves `x1` aliased. ngspice allows several `tran` runs in one
`.control` block -- each makes its own plot (`tran1`, `tran2`, ...) and a
`.meas` placed immediately after a `tran` measures that run. So each branch
gets an analysis sized for it, and the two graphs on the sheet read
dataset 0 and dataset 1.

**`Ikickd`/`Ikickr` are stimulus, not load.** A real ring starts from
noise. ngspice is noiseless, and a symmetric ring has a perfectly good
stable solution with every node parked at the switching threshold, so from
a 0V `UIC` start both branches sit there forever. The two current pulses
break that symmetry, and they inject into the *loop* node, not the
buffered output -- kicking the output would do nothing. `tb_srlatch.sch`
has the same symmetry problem and solves it with `.ic` instead.

**`Vgnd VGND 0 0` is what gives ngspice its node 0.** xschem emits ground
as a named global net (`VGND`, plus `.GLOBAL VGND`), never as SPICE node
0, so without that line nothing in the deck connects to 0 and the whole
circuit floats. `.option rshunt` papers over it by strapping every node to
0 through a huge resistor -- enough to make the matrix solvable, but the
absolute level is then set only by the balance of those shunt currents.
That is a real hazard: with `x2` deleted for debugging, the 100uA bias
source lost its only DC return path and the entire circuit floated to
about -277kV with the real signals riding on top. Every node reading
-277777.xx meant a floating reference, not a broken circuit. Grounding it
properly fixes that at the source, and `rshunt` then merely costs solve
time -- measured 1m54 without it against 2m40 with, same answer to 7
digits. Every testbench in this project now carries the `Vgnd` line.

## Testbench net names

`tb_ring.sch` follows the shared convention -- no suffix for a net shared
between the two instances, `_drawn`/`_routed` for one that differs per
instance. See [`../README.md`](../README.md).
