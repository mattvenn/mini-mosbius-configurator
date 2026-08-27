# Example: CMOS inverter

The simplest circuit that exercises the whole pipeline: two transistors,
gates tied together as the input, drains tied together as the output. This
is also [the first circuit tnt built](https://www.tinytapeout.com/news/mini-mosbius/)
when bringing up the real mini-MOSbius silicon, so it's a genuine point of
comparison, not just a convenient toy.

`inverter.sch` was drawn by hand in xschem on 2026-08-21, replacing an
earlier machine-generated version built against the pre-redraw symbol
geometry. It is built on `mini_mosbius.sch` from
`mosbius_nmos.sym`/`mosbius_pmos.sym`, wired to `ua1` (input), `ua2`
(output), `VGND` and `VAPWR` -- which is exactly what `TUTORIAL.md` walks
you through drawing, so this is the finished article for that walkthrough
rather than a machine-made stand-in.

```
XM1 ua1 ua2 VGND VGND mosbius_nmos w=1
XM2 ua1 ua2 VAPWR VAPWR mosbius_pmos w=1
```

Watch the pin order when you draw it: `mosbius_nmos` has its **drain** at
the top and its source at the bottom, and `mosbius_pmos` is the other way
up -- source at the top, drain at the bottom. So the two devices in an
inverter are not drawn the same way up, and flipping both the same
direction leaves exactly one of them reversed. That is not a circuit that
fails to route -- it routes clean and passes the safety checker -- it just
quietly costs a bus row, because only the *source* terminal has a free tie
to its rail (`ctrl_nfeta_source`/`ctrl_pfeta_source`).

`check.py`'s `D2` warns about exactly this shape -- drain on the rail the
body is tied to, source on a net -- but only when that source is an
*internal* net, not when it is a `ua[]` pin. In this inverter the output is
`ua2`, a pin, so a reversed device here still routes without a word. The
narrow rule is deliberate: with a package pin involved there are circuits
that legitimately look like this. Draw it carefully rather than relying on
the check.

## Routing

```
$ python3 -m mosbius.cli route build/inverter.spice
OK -- no errors or warnings (1 info note hidden, use --verbose).

Device roles:
  XM1          -> nmos_a        w=1
  XM2          -> pmos_a        w=1

Bitstream: 080000004010000001000000000000000040000400000000
```

Verified two ways beyond "the checker didn't complain": `mosbius decode` on
that bitstream reads back the exact same circuit (gates tied together on
`ua[1]`, drains tied together on `ua[2]`, sources tied to their own rails),
and it matches `tests/conftest.py`'s `make_inverter_config()` -- a
completely independent, hand-built-from-the-bit-map reference from M1,
before the router existed.

## Simulation

`inverter.sch` netlists to the *same real sky130 transistor sizing* as the
hardware block it stands in for, just without the switch-matrix overhead in
between (the design as drawn -- ideal wires, no switch matrix, SPEC.md Sec 3.1b) -- so this is what
the circuit does electrically, with the real switch-matrix parasitics left
out.

![Inverter w=1 waveform: ua1 pulses, ua2 responds inverted with a visibly slow rising edge](inverter_w1.png)

At `w=1` on both transistors (the schematic above) with a 100pF load,
10-90% rise time is **84.4 ns**. That 100pF is a heavy load -- see "What
the two load capacitors are" below; the testbench further down uses 10pF,
and these two figures and their waveform images are the only numbers on
this page still taken at 100pF. tnt's own hardware bring-up of the same
circuit -- real silicon, not simulation -- [reported "about a 50ns rise
time"](https://www.tinytapeout.com/news/mini-mosbius/) at the same starting
configuration, then "around 25ns" after widening the PMOS to `w=4` ("P
mosfets are weaker than N mosfets, and one way to compensate is by
increasing their width").

`inverter_w4.sch` is the same circuit with `M2`'s width raised to 4 --
the only difference between the two files is that one property --
reproducing that second measurement:

![Inverter w=4 waveform: same input pulse, output rises noticeably faster](inverter_w4.png)

At `w=4`, rise time is **21.1 ns** -- about 4x faster than the `w=1` case,
tracking the published ~50ns -> ~25ns improvement (a 2x change) reasonably
well in direction and roughly in magnitude, if not exactly: this
simulation's absolute numbers run somewhat higher than the published ones
(84ns vs ~50ns at `w=1`). That gap is the load, not the model. An as-drawn
model leaves out the chip's parasitic resistance and capacitance, which
makes it *faster* than silicon, not slower -- so omission cannot explain a
number above the measurement, and the 100pF load used here, heavier than
whatever tnt probed with, can. At the 10pF the testbench below uses, the
same as-drawn model gives 8.9ns and the ordering comes out right: as drawn
is faster than as routed, which is faster than silicon. See "What this does
and doesn't prove" below.

## What this does and doesn't prove

The **published trise numbers are real silicon**, from tnt's own hardware
bring-up -- not from this project's simulation, and not something this
project's own hardware has confirmed (see M4 status in the root README: no
demoboard was available in this environment). What the numbers above show
is that this project's as-drawn ideal simulation, run through the actual
toolchain (draw -> netlist -> route -> check, all verified against real
xschem/ngspice), lands in the same regime and responds to the same `w=1`
vs `w=4` change in the same direction -- a real, if partial, cross-check of
the device models in `xschem/mosbius_lib/`. Confirming the *routed* config
(as routed, with real switch parasitics) behaves the same way on *this
project's own* hardware bring-up is still open -- SPEC.md Sec 8.4's
`--verify` exit criterion.

## As drawn vs as routed, side by side: `tb_inverter.sch`

Everything above was the as-drawn model only, produced by netlisting `inverter.sch`
directly and hand-patching stimulus into the resulting SPICE text -- not a
real xschem testbench. `tb_inverter.sch` replaces that with the workflow
`mosbius simulate` (SPEC.md Sec 3.7) is actually meant for:
a real top-level testbench with two instances of the same design, `x1`
(ideal, ordinary hierarchy) and `x2` (a duplicate, its `spice_sym_def`
instance property pointing at a real, silicon-accurate netlist), sharing
one stimulus and one set of rails, so the *only* difference between
`out_drawn` (x1's output) and `out_routed` (x2's output) is as-drawn vs as-routed
fidelity. This is the same `spice_sym_def` swap-in mechanism used in
[github.com/mattvenn/tt08-analog-ring-osc's `tb_ring.sch`](https://github.com/mattvenn/tt08-analog-ring-osc/blob/main/xschem/tb_ring.sch)
to compare an ideal schematic against a post-layout extraction -- here the
"extraction" is `mosbius simulate`'s output instead of a magic PEX run.

Both `x1` and `x2` are the same symbol, `xschem/mosbius_lib/mini_mosbius.sym`
-- the mini-MOSbius chip as a block, nine real pins and nothing else, which
is identical for every design. What makes an instance stand for a
*particular* design is its `schematic=` attribute, not a symbol of its own:

| instance | `schematic=` | netlists as | is |
|---|---|---|---|
| `x1` | `tcleval([file normalize examples/inverter/inverter.sch])` | `.subckt inverter` | the inverter **as drawn** -- ideal wires, no switch matrix |
| `x2` | `inverter_routed` (+ `spice_sym_def`) | `.subckt inverter_routed` | the same inverter **as routed** onto the chip, from `mosbius simulate` |

The subcircuit name follows the `schematic=` file, which is why `x1` comes
out as `inverter` and not as `mini_mosbius`.

`x1`'s absolute `tcleval([file normalize ...])` form is load-bearing and is
not decoration. `schematic=` is resolved relative to the *symbol's* own
directory, and this symbol lives in `xschem/mosbius_lib/`, so both
`schematic=inverter` and `schematic=inverter.sch` look for a file that
isn't there and quietly fall back to the symbol's own empty body. You then
get `.subckt inverter` containing no transistors at all -- a netlist that
runs, and measures nothing. Verified both ways 2026-08-24.
`xschem/mosbius_lib/tb_template.sch` uses the same absolute form for the
same reason, so copying it to your own directory keeps working.

### Stimulus and ground

`Vin` pulses `ua1` from 3.3V down to 0 at t=10ns, shared by both
instances. The *input* falls, so the inverter's output *rises* -- which is
why both measurements are `RISE` edges on `out_drawn`/`out_routed` while
the thing driving them is a falling edge. Everything above this section
was produced by hand-patching stimulus into a netlist; this is the same
methodology driven from a real xschem testbench instead.

`Vgnd VGND 0 0` in the ngspice block is not optional -- xschem never emits
SPICE node 0, so without it the whole circuit floats. Every testbench here
carries it; `examples/ringosc/README.md`'s "How `tb_ring.sch` is set up"
has the full story, including what happens when it is missing.

### Regenerating `build/inverter_routed.spice`

`x2`'s `spice_sym_def` points at `build/inverter_routed.spice`. Everything
in `build/` is generated, so that file is never in a fresh clone, and the
testbench cannot simulate without it.

You do not have to remember any of this. With `tb_inverter.sch` open,
ctrl-click the **generate routed spice** arrow on the sheet: it netlists
`inverter.sch`, routes it, and writes the routed netlist, reporting each
step in xschem's process window. Press Netlist again afterwards to pick it
up.

The same thing from a shell at the top of the repo, for any design:

```bash
sh tools/regenerate_routed.sh examples/inverter/inverter.sch
```

which is just these three steps:

```bash
xschem -n -q examples/inverter/inverter.sch
python3 -m mosbius.cli route build/inverter.spice --out build/inverter.mosbius.json
python3 -m mosbius.cli simulate build/inverter.mosbius.json
```

No `PDK=sky130A` export is needed any more: the repo's own `xschemrc`
pins the variant (it used to be possible to netlist with sky130A's symbols
but a `.lib` path pointing into `ihp-sg13g2`, which produces a netlist that
looks perfect and cannot simulate).

The routed bitstream should still read
`080000004010000001000000000000000040000400000000`, matching the "Routing"
section above -- if it doesn't, something about the drawn circuit has
changed. Routing is deterministic for an unchanged schematic, so deleting
`build/` and starting again reproduces exactly this bitstream.

If you netlist the testbench *without* generating it first, you are told
so at that moment rather than left to decode a SPICE error two steps later:
`xschemrc`'s `mosbius_routed_include` puts the explanation and the commands
into the netlist as comments, and raises one dialog in the GUI. The
`.include` is still emitted, so ngspice stops rather than quietly
simulating a comparison with nothing on one side.

`build/tb_inverter.spice` is then a complete, self-contained deck --
`.control` already has a real `tran`, two `.meas` rise-time measurements
(`trise_drawn`, `trise_routed`), and `wrdata` output for
`ua1`/`out_drawn`/`out_routed`.

### What running it shows

Re-measured 2026-08-27 at `cload=10p`, on the routing the router produces
today (`0800000040100000...`):

```
trise_drawn  =  8.90ns
trise_routed = 24.63ns
```

As routed is **2.8x slower** than as drawn. Both are faster than tnt's
~50ns silicon measurement, which is the ordering you want: the drawn model
omits the most, the routed model omits less, real silicon omits nothing.

The same testbench at the old 100pF gives 88.43ns and 130.33ns -- a ratio
of only 1.47. Those two runs together separate the two effects:

| load | `trise_drawn` | `trise_routed` | ratio |
|---|---|---|---|
| 100pF | 88.43ns | 130.33ns | 1.47 |
| 10pF | 8.90ns | 24.63ns | 2.77 |

A purely resistive difference would hold the ratio constant across loads
and a purely capacitive one would shrink it at the larger load, so it is
both. Solving the two measurements together puts roughly **10.8pF of extra
capacitance** on the routed output and a series switch resistance of about
**33%** of the drive resistance. The capacitance figure is a good match for
what `mosbius simulate` actually instantiates on a used package pin: the
pad model in `mosbius/data/mosbius_device_library.spice` carries `2p` at the
pin and `3p` behind its bond inductance, on top of the drain/source
capacitance of a 60um NMOS and 180um PMOS ESD pair.

So the dominant thing the routed model adds here is the **bond pad**, not
the switch matrix. Row coupling (~43fF/switch) and bus-wire capacitance
(~900fF/row) really are swamped by a 100pF load, as an earlier version of
this section said -- that reasoning was right, it was just measuring the
wrong quantity, because a pad an order of magnitude bigger than either was
sitting in the path too. And note what the load choice did to the
conclusion: at 100pF the chip appears to cost 47%, at 10pF it costs 180%.
The load is the single biggest lever on the number a reader takes away
from this example, which is why it is now a named parameter with a stated
justification rather than a round figure.

Read together with the ring oscillator, the two examples cross-check
`mosbius simulate` in the two regimes a real design can be in:
switch-matrix-dominated (ring oscillator, no external load, no pad in the
signal path between stages) and pad-and-load-dominated (this inverter,
driving a real package pin into a probe).

### What the two load capacitors are

`tb_inverter.sch` hangs one capacitor on each output, `Cload_drawn` and
`Cload_routed`, both `'cload'`, with `.param cload=10p` in the sheet's
ngspice block. Same value on both, deliberately, and the reasoning is
worth spelling out because two identical caps side by side invite the
wrong reading.

**The cap is the bench, not the chip.** It stands for the scope probe and
the PCB trace you would measure through -- a 10x probe is around 10pF.
It is a *controlled variable*: held identical on both instances so that
the only difference between `out_drawn` and `out_routed` is the chip
itself. That is what makes subtracting one from the other mean anything.

What each side contains, then:

| | contains |
|---|---|
| `x1`, as drawn | two FETs, ideal wires, probe straight on the drain |
| `x2`, as routed | switch matrix + row coupling + bus-wire capacitance + `pad_model` (2p board, 1 ohm + 1nH package, 3p pad, the analog mux gate on plus 15 deselected ones), probe outside the pad |

The difference between the two numbers is therefore exactly everything the
chip inserts between the transistor drain and the package pin.

The probe lands on a different node in each -- on the drain in `x1`,
outside the pad in `x2`. That asymmetry is correct: it is the same point
on a real bench, and `x1` has no pad for it to sit outside of. `x1`'s
missing pad is part of what is being measured, so it must not be
compensated for by inflating `Cload_drawn`.

**Why `Cload_routed` is not 0**, even though `pad_model` already carries
board and pad capacitance of its own: 0 would mean measuring with no probe
attached, and `out_routed` would then be a node nobody could observe. The
2pF `pad_model` holds at its pin node is package and board, not a probe.
The small overlap between that 2pF and the 10pF probe figure is a rounding
error next to getting the concept right.

**Why not per-instance estimates** -- `Cload_drawn` carrying
probe + PCB + pad + package because its model has none of that, and
`Cload_routed` carrying probe only because `pad_model` has the rest? Each
number would be a better standalone prediction of the bench, but the
difference between them would mean nothing, because you would have
deliberately compensated the drawn side for the effect the example exists
to show.

`tb_diffamp.sch` and `tb_srlatch.sch` use the same parameter and the same
value for the same reasons. `tb_ring.sch` deliberately has no load caps at
all: its observed node is the oscillator's own feedback node rather than
an output pad, so a cap there changes the circuit instead of modelling a
probe -- 100pF stops the drawn ring oscillating outright, and even 1pF
drags it from 2.5GHz to 1.5GHz. That is the same lesson from the other
end. Both examples are missing capacitance in the as-drawn model; the ring
shows it plainly, and the inverter used to bury it under a load ten times
heavier than the effect.

**Runtime.** About 35s in the IIC-OSIC-TOOLS container, of which ~13s is
sky130 library parsing and ~20s is building the circuit and solving the DC
operating point -- the transient itself is about a second. The `.option`
line sets `reltol=0.01` rather than ngspice's `1e-3` default, which is what
buys that: it took the run from ~110s to ~35s and moved both rise times by
under 0.1%. The operating point converges only after dynamic and true gmin
stepping both fail and ngspice falls back to source stepping, which is
where most of the remaining time goes; `rshunt` and `gmin` adjustments did
not help that.

An earlier version of this section said running both branches together
needed a higher-RAM machine and OOMed at ~1.9GB on the usual dev host.
That is no longer true and has been removed: it runs here repeatedly,
in well under a minute. The full-matrix decks in `tools/` that hit that
ceiling are much larger than what `mosbius simulate` emits for one design.
