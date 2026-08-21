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
drain there, not a gate.

**Internal nets that span both bus sides.** The free rows are `A{2,4,6}`
and `B{1,3,5,6}`, so the only row free on *both* sides is 6 -- which means
an internal net touching devices on both sides is forced onto row 6, and a
diff-pair input can never reach it. `net1` here is exactly such a net, and
it gates `XM3`/`XM4`.

This circuit routes because the allocator hands out the independent slots
in netlist order, so `XM2` and `XM4` take them and the halves fall to
`XM5`/`XM6`, whose gates are on `ua1` and `ua2`. That is luck, not design:
relist the same six devices in a different order and `XM4` takes a half,
its gate on `net1` needs row 6, and the router dies with a bare
`KeyError: ('cfgb_dpn_inm', 6)` rather than an explanation. `TODO.md` §5
covers both halves of the fix -- raise a real `RouteError`, and allocate by
constraint rather than by line order.

If you hit an unexplained crash from `route()` on your own design, rather
than a `RouteError` with a diagnosis, this is very likely what it is.

## Routing

```
$ python3 -m mosbius.cli route examples/srlatch/simulation/srlatch.spice
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

![SR latch waveform: Q powers up high, SET pulse has no visible effect since Q is already high, RESET pulse drives Q low and it stays low](srlatch.png)

The plot predates this schematic and uses the earlier pin assignment --
`ua1` (SET) and `ua4` (RESET) against `ua2` (Q), where the schematic above
uses `ua1`, `ua2` and `ua3`. Same six transistors, same topology, same
behaviour; only which package pin carries which signal differs, so the
waveform still shows what it says it shows. It has not been re-simulated
against the current file. What it demonstrates: at power-up, with neither SET nor RESET driven,
the latch starts at an undefined operating point (`Q` sits around 1.5V --
neither rail -- since with both pull-downs off the cross-coupled pair has
no external push toward either state) and resolves to `Q=HIGH` within
about 20ns, before the SET pulse even arrives at t~61ns. That's a real,
if slightly unlucky, property of this exact circuit, not a simulation
bug: an SR latch's power-up state is inherently arbitrary, decided by
whichever tiny asymmetry the solver's numerics happen to amplify first --
this run happened to resolve high, so SET's pulse (t~61ns) has no visible
effect (`Q` was already where SET would have driven it). RESET's pulse
(t~221-261ns) is the one that's unambiguous: `Q` drops to 0V exactly when
RESET goes high, and -- this is the actual point of a *latch* rather than
a combinational gate -- **stays at 0V after RESET releases**, held there
by the cross-coupled feedback rather than by anything actively driving it.

Unlike the inverter, there's no single published trise number to compare
against for this circuit -- the blog post describes the same topology and
behavior (SET/RESET pulses flipping the stored state) rather than a timing
measurement. The comparison here is topological and behavioral: the
circuit this project independently arrived at, via the router's own
transistor-budget constraints, is the same 6-transistor cross-coupled
topology tnt built and described, and it demonstrates the same core
property (a pulse forces a state that then persists after the pulse ends).
