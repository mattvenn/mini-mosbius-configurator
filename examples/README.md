# Working with the examples

Seven circuits share one workflow, one testbench idiom and one set of
traps. This page is the common ground; each example's own README covers
only what is particular to that circuit.
[`TUTORIAL.md`](../TUTORIAL.md) walks the inverter through from a blank
sheet.

| Example | Circuit | What it is for |
|---|---|---|
| [`inverter/`](inverter/) | Two FETs | The whole pipeline end to end, and the sharpest as-drawn against as-routed comparison. Start here. |
| [`srlatch/`](srlatch/) | Six FETs | State, plus a routing constraint that bites: which devices can take diff-pair halves. |
| [`diffamp/`](diffamp/) | Five FETs + tail bank | Drawing a differential pair as a pair, with a real tail current. |
| [`pdiffamp/`](pdiffamp/) | Five FETs + PMOS tail bank | The diff amp in the opposite polarity, and the only example that places a `mosbius_ptail`. |
| [`currentsource/`](currentsource/) | Two mirror legs | `ibias` itself, and the only example that measures a current. |
| [`otabuf/`](otabuf/) | OTA: five FETs + tail bank | A feedback loop closed through the switch matrix, and the only example that uses `mosbius_ota`. |
| [`ringosc/`](ringosc/) | Eight FETs | Every usable single FET on the chip at once, and how close the routed model gets to silicon. |

## Three things a number can be

**As drawn** is the schematic simulated directly: the real sky130 device
sizing behind each `mosbius_*` symbol, wired net to net. No switch matrix,
no bus rows, no pads. It is what the circuit does electrically, and it is
optimistic.

**As routed** is the same design through `mosbius route` and then
`mosbius simulate`, which writes a self-contained `<name>_routed.spice`
holding the configured switch matrix, its row-coupling and bus-wire
capacitance, and a pad model on every package pin the design uses. It
exposes the same nine pins as a hand-drawn design, so it drops into a
testbench in place of the ideal block.

**Measured on silicon** is a number from real hardware, taken here on a
ttsky25a part with an Analog Discovery 3. All seven examples have one.

The expected ordering is as drawn faster than as routed faster than
silicon: the drawn model omits the most, the routed model omits less, the
chip omits nothing. An example that violates it says so.

Net names follow the same words: `out_drawn` and `out_routed`,
`trise_drawn` and `trise_routed`.

## The testbench

Every testbench has the same shape, and
`xschem/mosbius_lib/tb_template.sch` is that shape with the
circuit-specific parts removed. Two instances of one symbol --
`mini_mosbius.sym`, the chip as a nine-pin block -- differ only in what
each stands for:

| instance | `schematic=` | netlists as | is |
|---|---|---|---|
| `x1` | `tcleval([file normalize examples/<name>/<name>.sch])` | `.subckt <name>` | the design as drawn |
| `x2` | `<name>_routed` (+ `spice_sym_def`) | `.subckt <name>_routed` | the same design as routed |

One stimulus and one set of rails feed both, so the only difference
between `out_drawn` and `out_routed` is the chip. A net shared between the
two instances carries no suffix; one that differs per instance carries
`_drawn` or `_routed`.

`x2`'s netlist lives in `build/`, which is generated and so absent from a
fresh clone. Ctrl-click **generate routed spice** on the testbench sheet,
or run:

```bash
sh tools/regenerate_routed.sh examples/inverter/inverter.sch
```

Then press Netlist again to pick it up. Netlist the testbench without
doing this and `xschemrc`'s `mosbius_routed_include` says so in the
netlist and in a dialog, rather than leaving an ngspice error two steps
later to be decoded.

## The probe

Each testbench hangs `Cprobe_drawn` / `Rprobe_drawn` and `Cprobe_routed` /
`Rprobe_routed` on the outputs, valued `'cprobe'` and `'rprobe'`. The
meter is part of the circuit, and unlike the pads -- which every user of
this chip has, and which are therefore baked into the generated netlist --
nobody has the same probe, so it is a parameter:

| instrument | `rprobe` | `cprobe` |
|---|---|---|
| 10x passive probe (the default) | 10meg | 10p |
| Analog Discovery 3 flywires | 1meg | 24p |
| 1x passive probe | 1meg | 100p |

Every published number in these READMEs is at the default. A figure taken
at `cprobe=10p` is not comparable to a bench reading through a 24 pF
instrument: the difference halves an expected slew rate and doubles an
expected settling time constant, which is large enough to look like a
disagreement with silicon.

Capacitance is the half that matters. Nothing here drives a node stiffer
than about 50 kOhm, so 10 MOhm against 1 MOhm costs a couple of percent,
while the capacitance sets every rise time on the sheet. The resistor
earns its place anyway: without it an output is an open circuit, VOH lands
exactly on the rail, and the sheet cannot reproduce a bench measurement of
a level at all.

Both values are held identical on the two instances. That is what makes
the difference between the two outputs mean something.

The routed side's extra delay is dominated by the bond pad rather than by
the matrix: on the inverter it is about 10.8 pF of additional
capacitance, against ~43 fF per switch of row coupling and ~0.9 pF per
row of bus wiring. Which effect dominates depends on the circuit. The
inverter drives a package pin into a probe; the ring oscillator's stages
drive each other with no pad between them; the amplifiers lose bandwidth
rather than gain, since at DC no current flows into a capacitor and series
resistance drops no voltage.

A load inside a feedback path is not a probe model. `tb_ring.sch` has no
capacitor on its loop nodes: 100 pF there stops the drawn ring
oscillating, and even 1 pF drags it from 2.5 GHz to 1.5 GHz. That is what
the ring's buffer stage is for.

## The bias reference

`ibias` (pin `ua[0]`) is a current input, not a voltage. On silicon it
feeds one diode-connected NMOS, and every mirror leg, tail bank and the
OTA's tail is a slave copying that gate voltage. The PMOS side gets its
own node, `ibias_p`, made by copying the reference 1:1 and pushing it
through a PMOS diode. One reference per chip, one gate node per polarity.

Every design sheet carries one `mosbius_bias` block wired to the `ibias`
pin, holding the chip's own three transistors at the sizes its schematics
use. It is part of the silicon rather than part of the circuit, which is
why it sits off to one side with a single wire, and why `ibias_p` never
appears on the sheet.

Keep exactly one. Two generators halve the reference current between them,
so every `ratio=` and `tail=` comes out at half; none leaves every mirror
gate wherever the DC solver puts it. `mosbius route` counts them and
refuses a design with none or two (`B1`).

What that buys is that the settings mean what they say: `ratio=N` and
`tail=N` are both N x `ibias`, which is what the hardware's 2/4/6/8 cycler
encoding means. At the testbench default of 100 uA, `tail=4` is 400 uA.
Each instance needs its own bias source -- the sheets carry `Ibias_drawn`
and `Ibias_routed` -- because one source shared between two chips divides
between them according to their input impedances, moving both branches.

### Feeding it by hand, when the board can't

The RP2350-controlled circuit that makes this current arrived on the later
ETR demoboards. On an older one `tt.analog_current_source` is `None` and
there is no bias current at all: the bits are still correct, but every
mirror, tail and OTA in the design references a current that is not there.
A design of plain FETs neither notices nor cares.

The workaround is a bench supply and one resistor into the bias pad. What
is controlled is a voltage and the pin wants a current, so the resistor
converts one to the other:

    V+  ---[ R ]--- ibias pad          I = (V+ - V_pad) / R

Pick the resistor large, so that most of the supply drops across it and
the part not chosen -- what the pad settles at -- matters proportionally
less. At 100 uA through 20 kOhm the resistor takes 2.0 V and the pad about
1.28 V, so being 50 mV wrong about the pad is a 2.5% error in the current;
through 4.7 kOhm the same 50 mV is 10.6%.

`tools/ad3/measure_ibias_clamp_ad3.py` sweeps the supply and reads both ends
of the resistor, so the current is a difference between two measurements
rather than a number derived from the supply's own idea of its output. It
also identifies the pad, which a single-point measurement cannot: a pad
that follows the supply 1:1 is connected to nothing, one pinned at 0 V is
one of the header letters tied to ground, and one that holds its own
voltage while the supply moves by volts is the reference. Measured on a
ttsky25a part, that sweep fits a square law to an rms of 3.5 mV across a
24x range of current, which is a diode-connected FET and not an ESD
structure or a leakage path.

With 20 kOhm, set the supply to 3.28 V for the nominal 100 uA; 5.0 V
reaches about 178 uA, the ceiling with that resistor. `tail=` and `ratio=`
multiply on the chip, so the pad never carries the multiplied current.

## Gotchas

These have each cost someone a day.

- **Launch xschem from the repo root.** It looks for `xschemrc` in its
  current working directory only, and does not search upwards. From
  anywhere else the netlists land in `simulations/` and every device comes
  out as `* M1 - mosbius_nmos IS MISSING !!!!` -- a deck with no
  transistors that ngspice runs perfectly happily.
- **`schematic=` resolves relative to the symbol's directory, and a failed
  lookup falls back silently** to the symbol's own empty body, emitting
  `.subckt <name>` with nothing in it. Use the absolute form,
  `schematic="tcleval([file normalize examples/inverter/inverter.sch])"`.
  The subcircuit name always follows the `schematic=` file.
- **A bare `"` inside a `code`/`code_shown` symbol's `value="..."`
  truncates the netlist there,** silently, taking the `.option`, the whole
  `.control` block and every `.meas` with it. It surfaces two steps later
  as ngspice's `no control job`. Quote prose with `'single quotes'`.
- **`Vgnd VGND 0 0` is not optional.** xschem emits ground as a named
  global net and never as SPICE node 0, so without that line the whole
  circuit floats.
- **VDPWR powers nothing you draw.** Every device the chip offers is a
  3.3 V `g5v0d10v5` FET on VAPWR, so a transistor you place never sees
  1.8 V. VDPWR reaches only the switch matrix, where one 1.8 V inverter
  per switch shifts a config bit up to a 3.3 V pass-gate drive. `mosbius
  simulate` ties all 192 config pins to VDPWR or VGND, so a routed deck
  without that rail is 192 open switches; the as-drawn instance never
  connects it at all.
- **A `w=` on a diff-pair half is ignored.** Those halves have no width
  bits; their geometry is fixed at the equivalent of `w=4`. A circuit
  drawn at `w=1` throughout can route as 1x/1x/4x while looking symmetric
  on screen. The router warns (`R1`) and reports the width every device is
  actually built at.
- **Diff-pair and OTA inputs reach only bus rows 1-3;** everything else
  reaches all six. Since `ua3` and `ua5` are outside that range, a gate on
  either cannot land on a half, and an internal net spanning both bus
  sides is forced onto row 6, which an input can never reach.
- **A net is a package pin only if it is named one.** `ua1`..`ua5` are
  recognised by name; anything else, `out` included, is an internal net
  that simulates fine and is unobservable on silicon. Drawing an `iopin`
  on it does not change that.
- **A tag reading "implicit port" is not a loose end.** Those nets leave
  the block through xschem's `extra` attribute, which its connectivity
  check cannot see; without the tag every netlist reported `undriven node:
  ibias` on designs that were correct.
- **A differential pair's shared source can carry nothing else.** That
  node has no switch onto the bus, so a third device on it -- or naming it
  `ua4` to measure the tail -- cannot be built. What may sit there is
  nothing (with the net named `VGND`/`VAPWR`, which uses the pair's free
  rail tie) or a `mosbius_ntail`/`mosbius_ptail`.
- **A pair's tail current has no off state.** The bank's smallest setting
  is one always-on transistor, so the chip sinks 2 x `ibias` out of the
  shared source whatever the schematic says. Tying the source to its rail
  shorts the bank out and hides this; left on an internal net it is real,
  the as-drawn simulation does not have it, and the router warns (`R3`).
- **Which hardware slot each device gets is the allocator's choice,** and
  it is not stable against unrelated edits. Read the roles from the route
  output.
- **Budget two minutes for the model load.** sky130A's combined library
  takes that long to parse regardless of circuit size. `.spiceinit` at the
  repo root has the free speedups; copy it wherever ngspice runs, since it
  reads that file only from its own working directory. Never set
  `ngbehavior=hsa`: it breaks bin selection for the PDK's binned HV FET
  models, and every instance then fails with "could not find a valid
  modelname".

## Building your own

Copy `xschem/mosbius_lib/mini_mosbius.sch` to a new file in the same
directory -- schematics refer to symbols by bare name, so they resolve
only while the file sits on xschem's library path. It arrives with the
nine pins placed and the bias generator off to one side. Wire the circuit
to those pins; there is nothing else to wire to, and no body or bias pin
to draw.

Netlist with xschem's Netlist button, then from the host:

```bash
mosbius route build/my_design.spice --out build/my_design.mosbius.json
mosbius watch build/my_design.spice
```

`--out` persists the routing decision, so an unchanged design reuses it
verbatim rather than re-solving, and an unrelated edit elsewhere cannot
silently relocate this circuit's rows. Watch mode reprints the route and
safety report about a second after every Netlist press, which is where the
iteration actually happens.

To simulate as routed, copy `tb_template.sch` next to the design and
replace `my_design.sch` and `my_design_routed` throughout. It ships
without `.meas` lines on purpose. Then, with a demoboard connected:

```bash
pip install mpremote   # once
mosbius program <bitstream>
```

which refuses to upload if the safety checker found an error. Add
`--verify` to shift the bits back out and confirm the readback, at least
once when setting up a new board.
