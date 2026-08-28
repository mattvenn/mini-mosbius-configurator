# Working with the examples

*Four circuits share one workflow, one testbench idiom, and one set of
traps. This page is the common ground; each example's own README covers
only what is particular to that circuit.*

| Example | Circuit | What it is for |
|---|---|---|
| [`inverter/`](inverter/) | Two FETs | The whole pipeline end to end, and the sharpest as-drawn/as-routed comparison. Start here. |
| [`srlatch/`](srlatch/) | Six FETs | State, plus a routing constraint that bites: which devices can take diff-pair halves. |
| [`diffamp/`](diffamp/) | Five FETs + tail bank | Drawing a differential pair *as a pair*, with a real tail current. |
| [`ringosc/`](ringosc/) | Eight FETs | An open investigation, not a polished example: how close the routed model gets to measured silicon. |

[`TUTORIAL.md`](../TUTORIAL.md) at the repo root walks the inverter
through from a blank sheet, one instruction at a time. This page is the
other half: the reference you come back to once you are drawing your own
circuits, and it assumes you have done that walkthrough once.

## Three things a number can be

Every measurement in these READMEs is one of three, and the difference
between them is the point of the examples.

**As drawn** is your schematic simulated directly: the real sky130 device
sizing behind each `mosbius_*` symbol, wired net-to-net with ideal wires.
No switch matrix, no bus rows, no pads. It is what the circuit does
electrically, and it is optimistic.

**As routed** is the same design pushed through `mosbius route` and then
`mosbius simulate`, which emits a self-contained `<name>_routed.spice`
containing the actual configured switch matrix, its row-coupling and
bus-wire capacitance, and a real pad model on every package pin the design
uses. It exposes the same nine-pin port list as a hand-drawn design
(`ibias ua1 ua2 ua3 ua4 ua5 VAPWR VDPWR VGND`), so it drops into a
testbench in place of the ideal block.

**Measured on silicon** is a number from real hardware. Only the inverter
and the ring oscillator have one, both from
[tnt's bring-up post](https://www.tinytapeout.com/news/mini-mosbius/), and
in the ring's case it is a *different bitstream* from the committed
schematic.

The expected ordering is as drawn faster than as routed faster than
silicon: the drawn model omits the most, the routed model omits less, the
chip omits nothing. When an example violates that ordering it says so
explicitly rather than smoothing it over.

There is no "Level 1"/"Level 2" here, and net names follow the same
vocabulary: `out_drawn`/`out_routed`, `trise_drawn`/`trise_routed`.

## The side-by-side testbench

All four testbenches have the same shape, and `xschem/mosbius_lib/tb_template.sch`
is that shape with the circuit-specific parts removed. Two instances of
one symbol -- `mini_mosbius.sym`, the chip as a nine-pin block, which is
identical for every design -- differing only in what each stands for:

| instance | `schematic=` | netlists as | is |
|---|---|---|---|
| `x1` | `tcleval([file normalize examples/<name>/<name>.sch])` | `.subckt <name>` | the design **as drawn** |
| `x2` | `<name>_routed` (+ `spice_sym_def`) | `.subckt <name>_routed` | the same design **as routed** |

One stimulus and one set of rails feed both, so the only difference
between `out_drawn` and `out_routed` is the chip. This is the same
`spice_sym_def` swap-in used to compare a schematic against a post-layout
extraction; here the "extraction" is `mosbius simulate`'s output.

`x2`'s netlist lives in `build/`, which is generated and therefore absent
from a fresh clone. Ctrl-click **generate routed spice** on any testbench
sheet, or from the repo root:

```bash
sh tools/regenerate_routed.sh examples/inverter/inverter.sch
```

Then press Netlist again to pick it up. Netlist the testbench without
doing this first and `xschemrc`'s `mosbius_routed_include` says so in the
netlist and in a dialog, rather than leaving you to decode an ngspice
error two steps later.

### Net names

A net **shared** between the two instances carries no suffix, because it
is physically one net (`in`, `set`, `reset`, `inp`, `inm`). A net that
differs per instance carries `_drawn` or `_routed`. Package pins a design
does not use keep their pin name (`ua5_drawn`, `ua5_routed`), having no
role to name them after. So the suffix tells you something real at a
glance: no suffix means one net feeding both halves, a suffix means one
per half.

## Capacitive loading

Each testbench hangs one capacitor on each output, `Cload_drawn` and
`Cload_routed`, both valued `'cload'` with `.param cload=10p` in the
sheet's ngspice block. That single parameter turns out to be the largest
lever on the conclusion a reader takes away, so it is worth spelling out.

**The capacitor is the bench, not the chip.** It stands for the scope
probe and PCB trace you would measure through -- a 10x probe is around
10pF. It is a *controlled variable*, held identical on both instances so
that the only difference between the two outputs is the chip itself. That
identity is what makes subtracting one from the other mean anything.

What each side then contains:

| | contains |
|---|---|
| `x1`, as drawn | the FETs, ideal wires, probe straight on the drain |
| `x2`, as routed | switch matrix + row coupling + bus-wire capacitance + `pad_model` (2pF board, 1 ohm + 1nH package, 3pF pad, the analog mux gate on plus 15 deselected ones), probe outside the pad |

The probe lands on a different node in each -- on the drain in `x1`,
outside the pad in `x2`. That asymmetry is correct: it is the same point
on a real bench, and `x1` has no pad for the probe to sit outside of.
`x1`'s missing pad is part of what is being measured, so it must not be
compensated for by inflating `Cload_drawn`. For the same reason
`Cload_routed` is not zero -- zero would mean measuring with no probe
attached, leaving `out_routed` a node nobody could observe.

Per-instance estimates (drawn carrying probe + PCB + pad + package,
routed carrying probe only) would each be a better standalone prediction
of the bench, and the difference between them would mean nothing, because
you would have compensated the drawn side for the very effect the
comparison exists to show.

**The value changes the story, not just the numbers.** The inverter,
measured at both loads:

| load | `trise_drawn` | `trise_routed` | ratio |
|---|---|---|---|
| 100pF | 88.43 ns | 130.33 ns | 1.47 |
| 10pF | 8.90 ns | 24.63 ns | 2.77 |

A purely resistive difference would hold the ratio constant across loads
and a purely capacitive one would shrink it at the larger load, so it is
both: roughly 10.8pF of extra capacitance on the routed output plus a
series switch resistance around 33% of the drive resistance. At 100pF the
chip appears to cost 47%; at 10pF it costs 180%. Same circuit, same
routing.

That extra capacitance is dominated by the **bond pad**, not the switch
matrix. Row coupling (~43fF per switch) and bus-wire capacitance (~900fF
per row) are genuinely swamped by a heavy external load -- but a pad an
order of magnitude larger than either sits in the path too, and an earlier
version of the inverter's analysis missed it by measuring at 100pF.

Which effect dominates depends on the circuit, and the examples cover both
regimes. The inverter is pad-and-load-dominated: it drives a package pin
into a probe. The ring oscillator is switch-matrix-dominated: its stages
drive each other, with no pad between them. The diff amp is neither --
its gain is unchanged to within 0.5% between drawn and routed, because at
DC no current flows into a capacitor and series resistance drops no
voltage, so the matrix costs it **bandwidth, not gain**.

**A load inside a feedback path is not a probe model.** `tb_ring.sch`
deliberately has no capacitor on its loop nodes: 100pF there stops the
drawn ring oscillating outright, and even 1pF drags it from 2.5GHz to
1.5GHz. That is why the ring has a buffer stage -- so the probe load lands
outside the loop, on a node where it models a probe again.

**Give the circuit time to settle before you measure it.** The diff amp's
output is a ~20 MOhm node, so 10pF alone gives it a ~200ns time constant
as drawn and ~470ns as routed. An earlier version of that example held
each input level for 100ns and reported gains between 0.03 and 7.8 V/V,
all of them samples taken before the output had arrived, and all of them
made the slower routed branch look like a worse amplifier when it is an
equally good one. The tell was in the raw file: a measurement that is
still moving while you take it is not a measurement.

## The bias reference

`ibias` (pin `ua[0]`) is a **current input**, not a voltage. On silicon it
feeds one diode-connected NMOS -- `mirror_n`'s reference leg -- and every
programmable mirror leg, differential-pair tail bank and the OTA's tail is
a *slave* copying that one gate voltage. The PMOS side gets its own node,
`ibias_p`, made by copying the reference 1:1 with an NMOS and pushing it
through a PMOS diode. One reference per chip, two gate nodes, one per
polarity.

The design sheets model that directly. `mini_mosbius.sch` -- and so every
design copied from it -- carries a three-transistor **bias generator**
sized from the chip's own schematics: an NMOS reference (L=1 W=10 nf=2),
a 1:1 NMOS copy, and a PMOS diode (L=1 W=30 nf=4). It is part of the
silicon rather than part of your circuit, which is why it sits off to one
side of the sheet with nothing wired to it by hand.

**Keep exactly one.** Two generators would halve the reference current;
none leaves `ibias` with no DC path at all, which does not simulate.
Nothing else about it needs your attention -- the device symbols find it
by net name.

What that buys you is that the settings mean what they say: `ratio=N` on a
`mosbius_nsink`/`mosbius_psource` is N x `ibias`, and `tail=N` on a
`mosbius_ntail`/`mosbius_ptail`/`mosbius_ota` is N x `ibias`, which is
also what the hardware's own 2/4/6/8 cycler encoding means. At the
testbench default of 100 uA, `tail=4` is 400 uA.

Two consequences worth knowing. Each instance in a testbench needs **its
own** bias source: the sheets carry `Ibias_drawn` and `Ibias_routed`, both
`'ibias_amps'`, for the same reason both load capacitors are `'cload'` --
one source shared between two chips gets divided between them, and the
split depends on their input impedances, so both branches move. And
sweeping `ibias_amps` scales every mirror, tail and OTA on the sheet at
once, which is a first-class experiment rather than a nuisance: the
demoboard's bias source is programmable from the same host that loads the
bitstream (`mosbius program --ibias`).

This was got wrong until 2026-08-28, in a way worth recognising if you
meet an old sheet: each device symbol used to carry its *own* copy of the
reference diode, so N devices split the reference N ways, and
`mosbius_psource` referenced the NMOS node instead of `ibias_p`. Symptoms
were currents that came out at 1/N of the request, or a lone
`mosbius_psource` delivering picoamps.

## Gotchas

These have each cost someone a day.

**Launch xschem from the repo root.** It looks for `xschemrc` in its
current working directory only -- not the schematic's directory, and it
does not search upwards. From the repo root you get sky130A and
`xschem/mosbius_lib` on the symbol path, the PDK variant pinned, and
netlists in `build/`. From anywhere else you get the container's defaults:
netlists in `simulations/`, and every device replaced by
`* M1 - mosbius_nmos IS MISSING !!!!` -- a deck with no transistors that
ngspice runs perfectly happily.

**`schematic=` resolves relative to the *symbol's* directory, and a failed
lookup falls back silently.** `mini_mosbius.sym` lives in
`xschem/mosbius_lib/`, so `schematic=inverter` or `schematic=inverter.sch`
on an instance looks for a file that is not there and falls back to the
symbol's own empty body, emitting `.subckt inverter` with nothing in it.
Use the absolute form,
`schematic="tcleval([file normalize examples/inverter/inverter.sch])"`.
The subcircuit name always follows the `schematic=` file, not the symbol.

**A bare `"` inside a `code`/`code_shown` symbol's `value="..."` truncates
the netlist there,** silently: the rest of your prose, the `.option`, the
whole `.control` block, every `.meas`. The failure surfaces two steps
later as ngspice's `no control job`. Quote prose with `'single quotes'` or
escape as `\"`.

**`Vgnd VGND 0 0` is not optional.** xschem emits ground as a named global
net and never as SPICE node 0, so without that line the whole circuit
floats. `.option rshunt` papers over it, but then the absolute level is
set by shunt currents: one debugging session had the entire circuit
floating at about -277kV with the real signals riding on top.

**A `w=` on a diff-pair half is ignored.** Those halves have no width bits
-- their geometry is fixed at the equivalent of `w=4`. A circuit drawn at
`w=1` throughout can therefore route as 1x/1x/4x while looking symmetric
on screen. The router warns (`R1`) and reports the width every device is
actually built at; read that, do not assume the schematic.

**Diff-pair and OTA inputs reach only bus rows 1-3;** everything else
reaches all six. Since `ua3`→`bus_A[5]` and `ua5`→`bus_B[4]` are outside
that range, a gate on either cannot land on a half. Internal nets spanning
both bus sides are forced onto row 6, which a diff-pair input can never
reach. The router says which pins would have worked instead of failing
opaquely.

**A net is a package pin only if it is *named* one.** `ua1`..`ua5` are
recognised by name; anything else, `out` included, is an ordinary internal
net that simulates fine and is unobservable on silicon. Drawing an
`iopin` on it does not change that.

**Which hardware slot each device gets is the allocator's choice,** and it
is not stable against unrelated edits. Read the roles from the route
output rather than assuming.

**Budget two minutes for the model load.** sky130A's combined library
takes ~2 minutes to parse regardless of circuit size, so a simulation is
not hung just because nothing has happened yet. `.spiceinit` at the repo
root has the small free speedups; copy it wherever ngspice actually runs,
since it only reads that file from its own working directory. Setting
`reltol=0.01` took the inverter testbench from ~110s to ~35s and moved
both rise times by under 0.1%. Never set `ngbehavior=hsa`: it breaks bin
selection for the PDK's binned HV FET models, and every instance then
fails with "could not find a valid modelname".

## Building your own

[`TUTORIAL.md`](../TUTORIAL.md) has the click-by-click version of what
follows; this is the same path at reference speed.

Copy `xschem/mosbius_lib/mini_mosbius.sch` to a new file **in the same
directory** -- schematics refer to symbols by bare name, so they resolve
only while the file sits somewhere on xschem's library path. It arrives
with the nine pins already placed, and with the chip's bias generator off
to one side (above). Wire your circuit to the pins; there is nothing else
to wire to, and no body or bias pin to draw, since those are hard-wired on
silicon and supplied by the symbols themselves.

Netlist with xschem's Netlist button. Then, from the host:

```bash
python3 -m mosbius.cli route build/my_design.spice --out build/my_design.mosbius.json
```

`--out` persists the routing decision, so re-running on an unchanged
design reuses it verbatim rather than re-solving -- an unrelated edit
elsewhere cannot silently relocate this circuit's rows and change its
parasitics. Routing is deterministic, so deleting `build/` and starting
again reproduces the same bitstream.

**Then leave watch mode running while you draw:**

```bash
python3 -m mosbius.cli watch build/my_design.spice
```

Every time you press Netlist, the watcher notices (it polls mtime, so it
works across the Docker bind mount) and reprints the route and safety
report within about a second. Draw, netlist, glance at the terminal, fix
anything DANGEROUS or IMPOSSIBLE, repeat. This is where the iteration
actually happens; running `route` by hand after every edit is the slow
path.

To simulate as routed, copy `tb_template.sch` next to your design and
replace `my_design.sch` and `my_design_routed` throughout with your own
names. It ships without any `.meas` lines on purpose -- what is worth
measuring depends on your circuit. Add them to the `.control` block,
ctrl-click **generate routed spice**, and Netlist again.

Finally, with a demoboard connected:

```bash
pip install mpremote   # once
python3 -m mosbius.cli program <bitstream>
```

which refuses to upload if the safety checker found an ERROR. Add
`--verify` to shift the bits back out and confirm the readback, at least
once when setting up a new board.
