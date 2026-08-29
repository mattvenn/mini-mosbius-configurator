# Example: SR latch

*Shared background for all six examples -- as drawn vs as routed, the
testbench idiom, capacitive loading, the common gotchas -- is in
[`../README.md`](../README.md).*

Six transistors: two cross-coupled inverters holding state (`XM1`-`XM4`)
plus two independent pull-down transistors (`XM5`, `XM6`) that force the
state. This reproduces [the second circuit tnt built](https://www.tinytapeout.com/news/mini-mosbius/)
bringing up real mini-MOSbius silicon -- "6 of the 8 mosfets to build 2
inverters to store the data and 2 pull down switches for set and reset" is
exactly this topology, independently arrived at here from the router's own
transistor-budget constraints rather than copied from the post.

```
XM1 ua3  net1 VAPWR VAPWR mosbius_pmos w=1
XM2 ua3  net1 VGND  VGND  mosbius_nmos w=1
XM3 net1 ua3  VAPWR VAPWR mosbius_pmos w=1
XM4 net1 ua3  VGND  VGND  mosbius_nmos w=1
XM5 ua1  net1 VGND  VGND  mosbius_nmos w=1
XM6 ua2  ua3  VGND  VGND  mosbius_nmos w=1
```

`XM1`/`XM2` form one inverter (input `ua3`, output `net1`); `XM3`/`XM4` form
the other (input `net1`, output `ua3`) -- cross-coupled, so each holds the
other's output through positive feedback once nothing is actively driving
it. `XM5` pulls `net1` low (forcing `ua3`/Q high); `XM6` pulls `ua3` low
directly (forcing Q low).

So the four external connections are **`ua1` = SET, `ua2` = RESET, `ua3` =
Q**, and `net1` is Qb, internal to the chip -- there is no fourth pin
carrying it, which matters for the routing constraint below.

## A routing constraint this example ran into

Six devices, four of them NMOS all sourced on `VGND` (`XM2`, `XM4`, `XM5`,
`XM6`). The chip has only two independent NMOS slots, so **two of those
four necessarily take diff-pair halves** -- and CLAUDE.md's traps list is
explicit that diff-pair *inputs* reach only bus rows 1-3, where every other
terminal reaches all six. So whichever two land on halves must have their
gates on a net that lives in rows 1-3.

That rules out two things, and the second is much harder to see than the
first.

**Package pins outside rows 1-3.** The pin-to-row map straddles both bus
sides: `ua1`->`bus_A[1]`, `ua2`->`bus_A[3]`, `ua4`->`bus_B[2]` are inside
the range; `ua3`->`bus_A[5]` and `ua5`->`bus_B[4]` are not. An earlier
version of this circuit used `ua3` as the reset *input* and could not
route. Note `ua3` is fine as Q, which is what this version does -- it is a
drain there, not a gate. The router now says which pins would have worked:

```
DOESN'T FIT -- XM5's gate (ndiffpair+.g) cannot reach bus_A[5]
  ...
  To fix: move this signal to a pin bonded to a row this terminal can
  reach (ua1, ua2 or ua4), or arrange for the restricted device not to be
  the one sitting on this net.
```

**Internal nets that span both bus sides.** The free rows are `A{2,4,6}`
and `B{1,3,5,6}`, so the only row free on *both* sides is 6 -- which means
an internal net touching devices on both sides is forced onto row 6, and a
diff-pair input can never reach it. `net1` here is exactly such a net, and
it gates `XM3`/`XM4`.

This circuit routes with `XM2` and `XM4` on the independent slots and the
halves falling to `XM5`/`XM6`, whose gates are on `ua1` and `ua2`. Until
2026-08-22 that was luck, not design: relisting the same six devices in a
different order handed `XM4` a half instead, its gate on `net1` needing
row 6 -- and the design would not route, even though nothing about the
circuit itself had changed. Since 2026-08-21 that failure was at least a
`RouteError` naming the device, the terminal, the rows it can reach and
the rows a two-sided net has available (it used to be a bare
`KeyError: ('cfgb_dpn_inm', 6)`):

```
DOESN'T FIT -- 'net1' spans both bus sides and no row can join them

  'net1' connects:
    ...
    XM4's gate (ndiffpair-.g) -- reaches only bus rows 1, 2 and 3
    ...
```

`TODO.md`'s device-allocation item (closed 2026-08-22) fixed the cause
rather than just the message: `allocate_devices()` now searches orderings
and keeps one where no diff-pair gate lands on a net it can't reach, so
relisting these same six devices in *any* order now produces this exact
same routing. `tests/test_route.py`'s `REORDERED_SR_LATCH` is that
relisted order, asserted to match.

## Routing

```
$ python3 -m mosbius.cli route build/srlatch.spice
WARNING -- XM5 and XM6 had their w=1 ignored: ndiffpair+ and ndiffpair-
           have a fixed width

Device roles:
  XM1          -> pmos_a        w=1
  XM2          -> nmos_a        w=1
  XM3          -> pmos_b        w=1
  XM4          -> nmos_b        w=1
  XM5          -> ndiffpair+    w=4 (fixed)
  XM6          -> ndiffpair-    w=4 (fixed)

Bitstream: 0c008000c020008808000000008821000220200800000038
```

No errors. The warning is the set and reset pull-downs landing on
diff-pair halves, which have no width bits, so their `w=1` cannot be
programmed and they are built at the fixed `w=4` instead. Benign here, and
arguably what you want: a pull-down that forces the latch has to overpower
the inverter's PMOS. But it is the sort of thing that used to be dropped
in silence, so draw them knowing they are four times the width the
schematic says.

(This used to be two near-identical 23-line warnings, one per device, 21
of those lines word-for-word the same -- `merge_findings` (TODO.md was
§3, closed 2026-08-22) now prints the shared explanation once, naming
both devices in the headline.)

This example used to also report five W2 warnings on crosspoints touching
the internal node, "no DC path to a rail or a package pin". Those were
false alarms -- a bistable node held by feedback looks unbiased to a
checker that sees closed switches but not transistor conduction -- and W2
now follows transistor channels, so they are gone.

## Simulation

![SR latch waveform: Q powers up at about 1.5V and resolves high within a
couple of ns, the SET pulse at 60-100ns has no visible effect since Q is
already high, the RESET pulse at 220-260ns drives Q to 0V and it stays there
after RESET releases](srlatch.png)

Re-simulated 2026-08-21 against the schematic above, so the pin labels are
this circuit's: **`ua1` = SET, `ua2` = RESET, `ua3` = Q.** This is SPEC.md
§3.1b's as-drawn result -- real sky130 device sizing, direct
net-to-net wiring, no switch matrix in between -- with no load on `ua3`
beyond the circuit itself.

Three things it shows, in order:

**Power-up is arbitrary, and this run resolved high.** At t=0 `Q` sits at
**1.46V** -- neither rail. With both pull-downs off, the cross-coupled pair
has nothing pushing it toward either state, so it starts at the balanced
operating point the DC solver finds. It falls off that balance almost
immediately, reaching 3.3V within about **1.4ns**, decided by whichever tiny
asymmetry the numerics happen to amplify first. That is a real property of an
SR latch, not a simulation artefact: power-up state is inherently undefined,
which is exactly why a latch needs a SET or RESET to be useful.

**SET does nothing visible here, and that is expected.** The pulse arrives at
**t=60.5ns** and `Q` is already high, so there is nothing for it to change.
Unlucky for a demo, honest about the circuit.

**RESET is the unambiguous one.** The pulse crosses mid-rail at
**t=220.6ns** and `Q` is below 0.1V by **t=221.4ns**. RESET releases at
**t=261.6ns** -- and this is the whole point of a *latch* rather than a
combinational gate -- **`Q` stays at 0V**, still 0V at the end of the run at
400ns, held by the cross-coupled feedback rather than by anything actively
driving it.

### Reproducing it

Two steps, both in the IIC-OSIC-TOOLS container, because neither xschem nor
ngspice is installed natively (CLAUDE.md). Netlist the schematic **from the
repo root**, so xschem reads the repo's `xschemrc` -- that is what puts both
sky130A and `xschem/mosbius_lib` on the symbol path. Run it from anywhere
else and the netlist comes out with every device replaced by
`IS MISSING !!!!`, a deck with no transistors that ngspice runs happily:

```bash
docker run --rm -v "$PWD:/work" -w /work hpretl/iic-osic-tools:latest \
  --skip bash -lc 'xschem -n -q examples/srlatch/srlatch.sch'
```

Then prepend stimulus and append the analysis to that netlist (strip its
trailing `.end` first), and run it:

```spice
.lib /foss/pdks/sky130A/libs.tech/ngspice/sky130.lib.spice tt
Vapwr  VAPWR 0 3.3
Vgnd   VGND  0 0
Vset   ua1 0 PULSE(0 3.3 60n 1n 1n 40n 1000n)
Vreset ua2 0 PULSE(0 3.3 220n 1n 1n 40n 1000n)
* ... netlist body ...
.tran 100p 400n
.control
run
wrdata srlatch_tb.txt v(ua1) v(ua2) v(ua3)
.endc
```

```bash
python3 tools/plot_tb.py build/srlatch_tb.txt examples/srlatch/srlatch.png \
  "SR latch (as drawn): SET on ua1, RESET on ua2, Q on ua3" \
  "ua1 (SET):0" "ua2 (RESET):1" "ua3 (Q):2"
```

The run itself took 54s, nearly all of it the sky130A model load, which is
fixed cost regardless of circuit size.

Unlike the inverter, there's no single published trise number to compare
against for this circuit -- the blog post describes the same topology and
behavior (SET/RESET pulses flipping the stored state) rather than a timing
measurement. The comparison here is topological and behavioral: the
circuit this project independently arrived at, via the router's own
transistor-budget constraints, is the same 6-transistor cross-coupled
topology tnt built and described, and it demonstrates the same core
property (a pulse forces a state that then persists after the pulse ends).

## Load capacitors in `tb_srlatch.sch`

The usual pair, both `'cprobe'` (plus a matching `'rprobe'`) with `.param cprobe=10p` -- see
[`../README.md`](../README.md) for why they are equal and why the value
matters.

Dropping it from 100pF to 10pF fixed a measurement that had never worked.
At 100pF, `treset_drawn`/`treset_routed` both reported
`trig(TARG) : out of interval` -- the falling edge through 1.65V simply
did not happen inside the measurement window, because the load was slow
enough to stretch the reset past it. At 10pF, re-run 2026-08-27:

```
qd_after_set     =  3.300V     qr_after_set     =  3.110V
qd_after_reset   = -0.0000V    qr_after_reset   = -0.0026V
treset_drawn     = 18.79ns
treset_routed    = 10.94ns
```

The stored-state measurements are unchanged in meaning: SET drives the
output to the rail, RESET returns it to ground, and both survive the pulse
ending.

`treset_routed` coming out *faster* than `treset_drawn` is the opposite of
the inverter's result, and it is explained: `XM5` and `XM6` are drawn
`w=1` where the differential-pair halves they land on are fixed at `w=4`
in silicon, so the as-drawn deck resets through write transistors four
times too weak. Widen those two and `treset_drawn` becomes 1.82 ns, faster
than the routed 10.94 as expected. See "Timing the reset" below, where the
same comparison is made against silicon. (An earlier guess here -- that
the two instances might power up in different states -- was wrong, and the
`.ic` lines in the sheet rule it out anyway.)

## On the bench

Measured 2026-08-29 on a TTDBv3 [3.2] demoboard with a ttsky25a chip, with
a calibrated Analog Discovery 3: `python3 tools/measure_srlatch_ad3.py`
loads this example's bitstream, walks the latch through the same sequence
the testbench simulates -- SET, release, RESET, release -- and reads the
output at each step. The pad letters come out of `mosbius/pads.py`
(**C** = `ua1` SET, **J** = `ua2` RESET, **D** = `ua3` Q); W1 and W2 drive
the two inputs and scope channel 2 watches Q.

![SR latch measured on silicon beside the same circuit simulated: on the
left, Q captured over 200 ms rising when SET is held and staying high
after SET is released, then falling when RESET is held and staying low
after RESET is released; on the right, the same sequence simulated as
drawn and as routed over 300 ns](srlatch_three_ways.png)

The shaded bands are the intervals when SET and then RESET are actually
held high. The flat stretches to the right of each band, with nothing
driving Q, are the stored state -- that is the measurement, and a plot of
Q alone would not show it, since high-while-driven is what any gate does.
The two time axes differ by six orders of magnitude because the bench
drives at milliseconds and the sheet pulses at nanoseconds. Every edge in
the left panel is the generator's DC offset slewing, not the latch
switching -- that is how the levels are driven, and "Timing the reset"
below is the measurement that does capture the latch's own edge. Redraw
it with `python3 tools/plot_srlatch_comparison.py`.

| | as drawn | as routed | on silicon |
|---|---|---|---|
| Q holding a 1, once settled | 3.2999 V | 3.2998 V | 3.3079 V |
| Q holding a 0, once settled | 0.0000 V | -0.0003 V | 0.0000 V (reference) |

**The latch works, and holds.** Both states survive their writing pulse
ending, and each held reading is the mean of 4000 samples over 40 ms that
is flat to about 5 mV peak-to-peak -- so a stored level decaying while it
was held would have shown as a slope rather than being averaged away. It
holds far longer than that: the second run of the script did not
reprogram the chip and found the latch still holding the 0 the first run
had left in it minutes earlier. That is the property this example exists
to demonstrate, it is the one none of the other five examples can show,
and the routed switch matrix does not lose it.

**The silicon column is a swing, not two levels.** A held-low output is a
pull-down with nothing drawing on it (the probe is 10 MOhm), so the chip
really is at ground there, and whatever the scope reads instead is that
channel's residual offset -- -17 mV on this run. Subtracting it is the
only offset correction a two-reading measurement affords, and it is worth
doing: across three runs the raw high reading wandered 5.2 mV (3.2856 to
3.2908 V) while the corrected swing moved 0.5 mV (3.3077 to 3.3082 V), so
the wander is the instrument drifting common-mode and the swing is real.
The swing lands 8 mV above a nominal 3.3 V rail, which is the instrument's
own accuracy and the rail's actual value between them, not a measurement
of anything in the circuit.

**The two decks agree here, so this separates nothing -- and the reason is
worth following.** `tools/check_srlatch_sim.py`'s references have
`qr_after_set` at 3.110 V against `qd_after_set` at 3.300 V, a 190 mV
drawn-versus-routed gap that looks like exactly the sort of thing a bench
measurement should adjudicate. It is not a level. The sheet samples at
110 ns, 9 ns after SET releases, and at that instant the routed instance
is still charging its 10 pF probe through the matrix's pass gates: it
reads 3.110 V there, 3.2238 V at 120 ns and 3.2998 V by 200 ns. So the
gap is a settling *time*, and the two models predict the same steady
state to within 0.1 mV. A reading taken 50 ms after the pulse can only see
that steady state. It confirms both models -- a matrix that dropped a
volt would have shown up plainly -- and tells them apart not at all.

**What state it comes up in.** Immediately after programming, Q read
-0.0176 V -- a stored 0. That is one observation of something the
simulation says is genuinely undefined, so it is recorded rather than
concluded: the chip was not power-cycled, only reconfigured, and one
sample of an arbitrary state says nothing about the next one.

### Timing the reset

`tools/measure_srlatch_edge_ad3.py` times RESET crossing mid-rail to Q
crossing it -- `tb_srlatch.sch`'s `treset`, measured on the chip. It needs
the orange **1+** lead moved onto pad **J** alongside W2, so the stimulus
is measured where it arrives at the chip rather than where it is
commanded.

![the reset transition on a nanosecond axis: RESET rising through mid-rail
at t=0, Q on silicon crossing mid-rail at about 24 ns, the as-routed deck
at about 21 ns and the as-drawn deck at about 41 ns, all four traces
aligned on RESET's own crossing](srlatch_reset_edge.png)

| | as drawn | as routed | on silicon |
|---|---|---|---|
| `treset`, `tt` | 49.14 ns | 19.89 ns | 24.46 ns |
| `treset`, `ss` | 40.70 ns | **21.30 ns** | **24.46 ns** |

**The as-routed model wins this by a factor of two.** Silicon lands 3.2 ns
from as-routed at `ss` (13%) and 16 ns from as-drawn (66%). That is the
third independent confirmation of `mosbius simulate`'s switch matrix on
this chip, after the inverter's trip point and the ring's frequency, and
the first one that is a delay rather than a level or a rate. `ss` is the
corner this chip measured at; see `examples/ringosc/README.md` for the
two-circuit argument that establishes it. It moves the routed number the
right way but only from 19% low to 13% low, so unlike the ring it does not
close the gap on its own.

**As drawn is slow because it is not the same circuit, and that is now
measured rather than suspected.** The router warns that `XM5` and `XM6`
land on differential-pair halves, whose geometry is fixed in silicon at
`w=4` while the sheet draws `w=1` -- so the as-drawn deck resets through
write transistors four times weaker than the ones the chip builds. Widen
just those two and the same deck, same stimulus, same corner, gives
**9.07 ns** instead of 40.70. Nearly all of as-drawn's error was that one
discrepancy, and with it removed the three numbers order themselves the
way every other example here does: as drawn 9.07 ns, as routed 21.30 ns,
silicon 24.46 ns -- ideal wiring fastest, the matrix's parasitics next,
silicon slowest. Reproduce with `sh tools/run_srlatch_measured_edge.sh ss
--drawn-w4`. Whether the schematic should be changed to match is a
separate decision, since it moves published numbers; `TODO.md` holds it.

**That also explains the anomaly this example has carried since it was
written.** `treset_routed` coming out *faster* than `treset_drawn` --
10.94 ns against 18.79 ns on the sheet's own stimulus, the opposite of the
inverter's result -- was recorded here and in `tools/check_srlatch_sim.py`
as unexplained, with a guess about the two instances powering up in
different states. It was the width mismatch: at `w=4` the sheet's own deck
gives `treset_drawn` = 1.82 ns, comfortably faster than the routed 10.94,
so the ordering was never wrong, the drawn circuit was just crippled.

**Why the numbers here are not the sheet's 18.79 and 10.94 ns.** Those are
under a 1 ns RESET step, which no signal generator can produce. The Analog
Discovery's edge measured 20.2 ns 10%-90% at the pad, and a latch driven
by a 20 ns ramp does not switch when one driven by a 1 ns step does -- so
`tools/run_srlatch_measured_edge.sh` re-runs both decks with a PULSE whose
`tr` reproduces the measured edge (25.3 ns, since a PULSE's `tr` is the
full 0-100% transition and 10%-90% is 0.8 of it) and with the flywires'
1 MOhm / 24 pF in place of the sheet's 10x probe. The committed sheet is
untouched and still publishes its own numbers; this is a netlist rewrite,
in the manner of `tools/sweep_corners.sh`.

**A trap that produced a completely believable wrong answer.** The first
attempt at this drove RESET by changing a wavegen's DC offset, which is
how the levels script works. An Analog Discovery slews an offset change
over *milliseconds*, so the latch was being dragged down a ramp thousands
of times slower than the event being timed. Nothing failed: the captures
were clean, the shape was plausible, and the delays came out scattered
across +/-70 ns. The tells were that the stimulus channel never reached
either rail anywhere in the buffer, and that both channels were still
moving at both ends of it. Drive an edge as a waveform -- a square wave,
a pulse, a custom shape -- and let the generator clock it out.

**The spread is not the accuracy.** Twenty captures agree to 0.05 ns
standard deviation, which looks far better than a 10 ns sample interval
should allow, and it is not a measure of how right the number is: the
generator and the scope share one clock inside the instrument, so every
capture samples the same event at the same phase and the quantisation
error repeats rather than averaging away. Interpolating each crossing
between its two straddling samples is what buys real resolution here; the
residual systematic is a few nanoseconds, which is the same size as the
gap to the as-routed model. Reading the 3.2 ns as physics would be
over-reading it.

**Reproducing it**

```bash
python3 tools/measure_srlatch_edge_ad3.py            # on the host, needs USB
docker run --rm -v "$PWD:/work" -w /work hpretl/iic-osic-tools:latest \
    --skip bash -lc 'sh tools/run_srlatch_measured_edge.sh ss'
python3 tools/plot_srlatch_comparison.py             # draws both figures
```

## Power-up state

Before either pulse arrives the latch is in its hold state, which has three
DC solutions: output high, output low, and the balanced one where both
inverters sit at their own switching threshold. ngspice is noiseless and
`x1` is perfectly symmetric, so the operating-point solver used to land on
that balanced solution -- `out_drawn` starting at **1.497V**, just under
half of 3.3V because the NMOS is stronger than the PMOS.

It does not stay there. Timestep truncation error provides a tiny
asymmetry and the latch's own positive feedback amplifies it: measured in
`build/tb_srlatch.raw`, it held 1.49731V flat to five decimals until
~13ns, then ran away exponentially -- 1.44V at 18ns, 0.66V at 21.7ns,
under 1mV by 39ns, fully settled before SET arrives at 60ns. The ~5ns from
visible to resolved is the real regeneration time constant; the 13ns
before it is just how long the numerical perturbation took to grow.

`x2` never had the problem: the routed instance is not symmetric -- different
bus rows, different row-coupling capacitance, pads on some nets and not
others -- so its operating point lands on a real stable state immediately.

The sheet now carries `.ic v(out_drawn)=0 v(out_routed)=0`, which pins both
branches to the state they were reaching anyway. Measurements are unchanged
to five significant figures, but they no longer depend on truncation error
resolving in time -- a tolerance change, a timestep change or an ngspice
version could have moved that, and a late escape would have corrupted the
first measurement. `tb_ring.sch` has the same symmetry problem and solves it
with current-pulse kicks instead; see that README's "How `tb_ring.sch` is
set up".

## Testbench net names

`tb_srlatch.sch` follows the shared convention -- no suffix for a net shared
between the two instances, `_drawn`/`_routed` for one that differs per
instance. See [`../README.md`](../README.md).
