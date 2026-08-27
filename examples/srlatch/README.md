# Example: SR latch

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

`Cload_drawn` and `Cload_routed` are both `'cload'`, with
`.param cload=10p` in the sheet's ngspice block -- one scope probe's worth
of load, held identical on both instances so the only difference between
`out_drawn` and `out_routed` is the chip. `examples/inverter/README.md`'s
"What the two load capacitors are" section explains why they are equal,
why the routed one is not 0, and why the value matters.

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
the inverter's result and is not yet explained. A latch's reset delay
depends on the state it starts from, and the two instances need not power
up in the same one, so this may not be a like-for-like comparison at all.
Do not read it as the routed chip being quicker than the ideal circuit
until someone has checked the starting states.

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

