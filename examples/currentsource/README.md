# Example: programmable current source and sink

*Shared background for all six examples -- as drawn vs as routed, the
testbench idiom, the bias reference, the common gotchas -- is in
[`../README.md`](../README.md).*

The only example whose subject is `ibias` itself rather than the bias
being a detail of something else, and the only one that measures a
current rather than a voltage. Getting it right took a correction to the
ideal device library that this example is what found -- see "The bug this
example found" below.

Two devices, one property each:

```
XI1 ua2 ibias VAPWR mosbius_psource ratio=2
XI2 ua3 ibias VGND  mosbius_nsink   ratio=2
```

`I1` sources current out of `ua2`, down from `VAPWR`; `I2` sinks current
into `ua3`, down to `VGND`. Neither has a drawn bias pin -- `ibias` is
supplied implicitly by the symbol, the same way the body ties are -- so
the sheet has exactly two wires on it. `ratio` is the only property either
symbol has: 1 to 4, in multiples of the chip's reference current.

It is the only example that uses `mosbius_psource` or `mosbius_nsink`.

## Routing

```
$ python3 -m mosbius.cli route build/currentsource.spice
OK -- no errors or warnings (1 info note hidden, use --verbose).

Device roles:
  XI1          -> psource_a     ratio=2
  XI2          -> nsink_a       ratio=2

Bus rows:
  ua2      bus_A[3]   package pin ua2 -- bond pad + analog mux
  ua3      bus_A[5]   package pin ua3 -- bond pad + analog mux

Bitstream: 000400400000000000010000000000008000000000000000
```

Both outputs have to be on package pins: a current you cannot connect an
ammeter to is a current you cannot measure. Neither leg is a diff-pair
input, so neither is restricted to bus rows 1-3.

## The testbench measures current, not voltage

`tb_currentsource.sch` departs from the other testbenches in three ways,
each for a reason.

**One swept voltage source, four ammeters.** `Vsweep` holds a single node
at a voltage the `dc` analysis sweeps from 0 to 3.3V, and each of the four
legs (source and sink, drawn and routed) reaches that node through its own
0V voltage source acting as an ammeter. Every leg therefore sees exactly
the same output voltage -- the same controlled-variable logic the load
capacitors use elsewhere -- while its current is read separately as
`i(vam_...)`. The sign convention follows from the wiring: positive means
current leaving the chip pin, so the source leg reads positive and the
sink leg negative.

**A `dc` sweep, not a transient.** This is the first deck here that is not
`tran`. What the example is about is an I-V curve: how much current comes
out, and how close to the rail it holds before the mirror leaves
saturation.

**No load capacitors.** They model a scope probe, and at DC there is
nothing for a probe capacitance to do. The reason they exist elsewhere
(see `../README.md`) does not apply here.

**Two bias sources, one per instance.** `Ibias_drawn` and `Ibias_routed`
are separate current sources, both `'ibias_amps'` with
`.param ibias_amps=100u`. Every testbench here does that now, and this
example is why it changed: two chips in parallel on one reference current
get roughly half each, and the split depends on the two instances' input
impedances, so the operating point of *both* branches moves. Held equal but separate, the
only difference between the branches stays the chip. Measured here: the
routed source leg reads 209 uA with separate sources against 482 uA
sharing one.

## What running it shows

At `Vsweep=1.65V`, `ratio=2`, `ibias_amps=100u`, measured 2026-08-28:

| leg | as drawn | as routed | expected |
|---|---|---|---|
| `psource_a` (source) | +209.9 uA | +209.3 uA | +200 uA |
| `nsink_a` (sink) | -201.3 uA | -203.9 uA | -200 uA |

Both legs deliver `ratio x ibias`, and the two branches agree within 1.3%
-- as they should, since a current mirror's output current is set by its
gate voltage, and the switch matrix's series resistance changes the
*voltage* at the pin, not the current through it. That is the same
"resistance costs speed, not accuracy" result the diff amp gives for gain,
measured on the DC quantity instead.

## The whole curve, and where it stops being a current source

That mid-rail number is one point on an I-V curve, and the sweep is the
reason to run this example rather than trust the label. The source leg
across the whole supply, as drawn:

| pin voltage | 0.0 V | 1.0 V | 1.65 V | 2.5 V | 2.9 V | 3.0 V | 3.2 V | 3.3 V |
|---|---|---|---|---|---|---|---|---|
| `psource_a` | 224.6 uA | 216.7 | 209.9 | 195.2 | 178.5 | 166.6 | 83.0 | 0.0 |

Three separate effects live in that one row, and telling them apart is
what the example is for.

**The gentle slope from 0 to 2.5 V is finite output resistance,** not a
flat region: 11.8 uA/V, about 85 kOhm. Taking the mid-rail value as
nominal, the current is within 5% only between about 0.575 V and 2.325 V
-- bounded at *both* ends, which is the part that surprises. A mirror leg
is not an ideal current source, and "200 uA" as a label hides a curve
that moves by 13% before anything has gone wrong.

**Above about 2.5 V the PMOS leaves saturation** and the slope tears
away: 57 uA/V up to 3.0 V, then 555 uA/V beyond it, reaching zero at
VAPWR where there is no drain-source voltage left to work with. That knee
is the compliance limit, and it is why the symbol is drawn as a
transistor rather than as an ideal-source circle -- the glyph would
promise behaviour the hardware does not have.

**209.9 uA rather than exactly 200 is the classic mirror error.** The
slave sits at a different drain-source voltage from the diode-connected
reference it copies, and the one with more voltage across it passes more.
The curve crosses 200 uA at about 2.3 V of pin voltage, which is
therefore where the slave's |Vsd| matches the reference's -- putting the
reference at roughly 1.0 V. That last step is inferred from where the
curves cross, not read off a probe on the bias node.

**The routed curve tracks the drawn one within 0.5% until the knee,**
then degrades slightly faster: at 3.0 V the drawn leg is down 20.6% from
its mid-rail value and the routed one 22.8%. Read as a voltage instead of
a current, the routed leg behaves like the drawn one biased 24.3 mV
lower, which at 162 uA is on the order of 150 Ohm of series resistance in
the matrix and the pad. That is arithmetic on two simulated curves rather
than a measured resistance. It is also the same lesson the other examples
give from the other side: at DC the matrix costs you nothing until you
are close to a rail, and there the tens of millivolts it eats are the
difference between working and not.

## The bug this example found

The first version of this measurement read +501 uA and -707 uA as drawn
against the routed branch's correct +209/-204 uA. Both faults were in the
ideal device library, and both are fixed as of 2026-08-28.

**Every device carried its own copy of the chip's bias reference.** Each
`mosbius_nsink`/`mosbius_psource`/`mosbius_ntail`/`mosbius_ptail` held a
diode-connected reference transistor on the shared `ibias` net as well as
its slave. Silicon has exactly one reference: pin `ua[0]` feeds
`mirror_n`'s reference leg and every programmable leg is a slave off that
one gate voltage. Replicating it meant N devices split the one reference
current N ways -- measured, two `mosbius_nsink ratio=2` gave -99 uA each
where -200 uA was right, while one alone gave the correct -201 uA.

**And `mosbius_psource` referenced the wrong node.** Its reference was a
PMOS diode from `ibias` up to `VAPWR`, but `ibias` is the NMOS-referenced
node: current is pushed *into* it and is meant to flow *down* through an
NMOS diode. A lone psource therefore delivered **1.65 pA** -- the injected
current had nowhere to go and the node floated up to the rail. Put an
nsink beside it and the two diodes formed a conducting chain across the
supply, pinning `ibias` where they balanced: that is where +501 uA and
-707 uA came from.

The fix is one bias generator per design, reproducing the chip's own
`ua[0]` -> `mirror_n` -> `ibias_p` -> `mirror_p` chain at those
schematics' device sizes (NMOS reference L=1 W=10 nf=2, a 1:1 NMOS copy,
PMOS diode L=1 W=30 nf=4). The device symbols keep only their slave legs,
and `mosbius_psource` now references `ibias_p`, which is what
`mosbius_ptail.sym`'s template had been asking for all along against a net
nothing generated.

**Where that generator lives is a symbol of its own.** This sheet places
one `mosbius_bias` from `xschem/mosbius_lib`, wired to the `ibias` pin --
which is an ordinary `devices/iopin.sym` like the other eight. Descend
into the symbol and you see the chip's three transistors drawn; on the
sheet it is one block, drawn as a current sink because that is what it is
from the pin's side. Only its `ibias` pin is drawn: `ibias_p` and the two
rails ride in on `extra`, the same way a FET's body tie does, so
`ibias_p` is an ordinary net of your design's subcircuit -- created by the
block, picked up by `mosbius_psource` through its template, never drawn.

**Exactly one per design**, and `mosbius route` enforces it (`B1`): none
leaves every mirror gate wherever the DC solver puts it, and two share the
demoboard's current between them so every `ratio=` and `tail=` comes out
at half. The check also counts the older hand-drawn form -- an NMOS with
its gate and drain both on `ibias` -- so a sheet predating 2026-08-28
still passes, though every design sheet in this repo now uses the symbol.

`examples/diffamp/`'s numbers moved with it -- its tail bank had been
running at half the current `tail=4` means on silicon. The inverter, SR
latch and ring oscillator were re-measured and are unchanged to the last
digit, since none of them uses a bias-referenced device.

## Still to do

- Sweep `ratio` 1 to 4: four bitstreams, four currents, checking the
  spacing is even. `ratio` is a device property, so this is four netlist
  and route runs, not one deck.
- Sweep `ibias_amps` in one run, as a nested `dc` sweep, for the family of
  curves.

## On the bench

The same two sweeps, with real hardware:

**Ratio linearity** is immune to the demoboard's uncalibrated bias source,
because a ratio of two measured currents cancels the calibration error.
Four bitstreams at `ratio=1..4`, one current measurement each, into a
current meter or across a sense resistor sized for about a 0.3V drop
(roughly 3 kOhm at these currents). If the four come out evenly spaced,
the mirror-ratio bits mean what the bit map says they mean -- which
nothing in this project has yet confirmed against silicon.

**`ibias` calibration** is the reverse experiment and the more valuable
one: one bitstream, `mosbius program --ibias` stepped across the source's
range, current measured at each step. `program.py`'s level-to-amps
constant is marked in its own source as approximate ("0 - 0xffff, up to
~250 uA"), so this sweep is what turns it into a real number -- and every
other analog measurement on this chip depends on it.

**Compliance** is the pin-voltage sweep: hold the output pin at a series
of voltages and watch where the current falls away.
