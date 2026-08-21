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

This circuit routes because the allocator hands out the independent slots
in netlist order, so `XM2` and `XM4` take them and the halves fall to
`XM5`/`XM6`, whose gates are on `ua1` and `ua2`. That is luck, not design:
relist the same six devices in a different order and `XM4` takes a half,
its gate on `net1` needs row 6, and the design does not route.

It does at least say so. Since 2026-08-21 that failure is a `RouteError`
naming the device, the terminal, the rows it can reach and the rows a
two-sided net has available:

```
DOESN'T FIT -- 'net1' spans both bus sides and no row can join them

  'net1' connects:
    ...
    XM4's gate (ndiffpair-.g) -- reaches only bus rows 1, 2 and 3
    ...
```

It used to be a bare `KeyError: ('cfgb_dpn_inm', 6)`. What is still open is
the other half: allocating by constraint rather than by line order, so that
the devices whose gates need rows 1-3 are the ones that get the halves.
`TODO.md` §3 covers it.

## Routing

```
$ python3 -m mosbius.cli route build/srlatch.spice
WARNING -- XM5's w=1 was ignored: ndiffpair+ has a fixed width
WARNING -- XM6's w=1 was ignored: ndiffpair- has a fixed width

Device roles:
  XM1          -> pmos_a        w=1
  XM2          -> nmos_a        w=1
  XM3          -> pmos_b        w=1
  XM4          -> nmos_b        w=1
  XM5          -> ndiffpair+    w=4 (fixed)
  XM6          -> ndiffpair-    w=4 (fixed)

Bitstream: 0c008000c020008808000000008821000220200800000038
```

No errors. The two warnings are the set and reset pull-downs landing on
diff-pair halves, which have no width bits, so their `w=1` cannot be
programmed and they are built at the fixed `w=4` instead. Benign here, and
arguably what you want: a pull-down that forces the latch has to overpower
the inverter's PMOS. But it is the sort of thing that used to be dropped
in silence, so draw them knowing they are four times the width the
schematic says.

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
§3.1b's Level-1 "ideal" result -- real sky130 device sizing, direct
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
  "SR latch (Level-1): SET on ua1, RESET on ua2, Q on ua3" \
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
