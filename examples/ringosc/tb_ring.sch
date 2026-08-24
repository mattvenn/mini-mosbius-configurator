v {xschem version=3.4.8RC file_version=1.2}
G {}
K {}
V {}
S {}
F {}
E {}
B 2 180 -180 980 20 {flags=graph
y1=-0.04
y2=3.6
ypos1=0
ypos2=2
divy=5
subdivy=1
unity=1
x1=5e-14
x2=4e-08
divx=5
subdivx=1
xlabmag=1.0
ylabmag=1.0
node=tran1.v(out_drawn)
color=12
dataset=0
unitx=1
logx=0
logy=0
}
B 2 180 60 980 260 {flags=graph
y1=6.9e-06
y2=3
ypos1=0
ypos2=2
divy=5
subdivy=1
unity=1
x1=1e-12
x2=6e-07
divx=5
subdivx=1
xlabmag=1.0
ylabmag=1.0
dataset=1
unitx=1
logx=0
logy=0
color=12
node=tran1.v(out_drawn)}
T {The same 3-stage ring oscillator twice: x1 as drawn (ideal wires, no switch} -530 -680 0 0 0.25 0.25 {}
T {matrix, no parasitics at all) and x2 as routed onto the real chip (real switch} -530 -650 0 0 0.25 0.25 {}
T {matrix, row coupling, bus wire caps, pads). Both are mini_mosbius.sym --} -530 -620 0 0 0.25 0.25 {}
T {schematic= is what says which one an instance stands for.} -530 -590 0 0 0.25 0.25 {}
T {No input pin: ring.sch loops back through ua1, so ua1 IS out_drawn/out_routed.} -530 -560 0 0 0.25 0.25 {}
T {They run ~70x apart, so each branch gets its own tran -- see the NGSPICE block.} -530 -530 0 0 0.25 0.25 {}
T {x2 needs build/ring_routed.spice: ctrl-click -generate routed spice-, then Netlist.} -530 -500 0 0 0.25 0.25 {}
C {mini_mosbius.sym} -450 -120 0 0 {name=x1
schematic="tcleval([file normalize examples/ringosc/ring.sch])"}
C {mini_mosbius.sym} -60 -120 0 0 {name=x2
schematic=ring_routed
spice_sym_def="tcleval([mosbius_routed_include build/ring_routed.spice])"
tclcommand="textwindow [file normalize build/ring_routed.spice]"}
C {devices/lab_pin.sym} -350 -40 2 0 {name=p1 sig_type=std_logic lab=Ibias}
C {devices/lab_wire.sym} -550 -200 0 0 {name=p6 sig_type=std_logic lab=out_drawn}
C {devices/lab_wire.sym} -550 -160 0 0 {name=p7 sig_type=std_logic lab=ua2_drawn}
C {devices/lab_wire.sym} -550 -120 0 0 {name=p8 sig_type=std_logic lab=ua3_drawn}
C {devices/lab_wire.sym} -550 -80 0 0 {name=p9 sig_type=std_logic lab=ua4_drawn}
C {devices/lab_wire.sym} -550 -40 0 0 {name=p10 sig_type=std_logic lab=ua5_drawn}
C {devices/lab_pin.sym} -350 -220 2 0 {name=pv1 sig_type=std_logic lab=VAPWR}
C {devices/lab_pin.sym} -350 -160 2 0 {name=pv2 sig_type=std_logic lab=VDPWR}
C {devices/lab_pin.sym} -350 -100 2 0 {name=pv3 sig_type=std_logic lab=VGND}
C {devices/lab_pin.sym} 40 -40 2 0 {name=p1b sig_type=std_logic lab=Ibias}
C {devices/lab_wire.sym} -160 -200 0 0 {name=p6b sig_type=std_logic lab=out_routed}
C {devices/lab_wire.sym} -160 -160 0 0 {name=p7b sig_type=std_logic lab=ua2_routed}
C {devices/lab_wire.sym} -160 -120 0 0 {name=p8b sig_type=std_logic lab=ua3_routed}
C {devices/lab_wire.sym} -160 -80 0 0 {name=p9b sig_type=std_logic lab=ua4_routed}
C {devices/lab_wire.sym} -160 -40 0 0 {name=p10b sig_type=std_logic lab=ua5_routed}
C {devices/lab_pin.sym} 40 -220 2 0 {name=pv1b sig_type=std_logic lab=VAPWR}
C {devices/lab_pin.sym} 40 -160 2 0 {name=pv2b sig_type=std_logic lab=VDPWR}
C {devices/lab_pin.sym} 40 -100 2 0 {name=pv3b sig_type=std_logic lab=VGND}
C {devices/vsource.sym} -440 170 0 0 {name=VAPWR value=3.3}
C {devices/lab_pin.sym} -440 140 1 0 {name=pva sig_type=std_logic lab=VAPWR}
C {devices/gnd.sym} -440 200 0 0 {name=l1 lab=VGND}
C {devices/vsource.sym} -340 170 0 0 {name=VDPWR value=1.8}
C {devices/lab_pin.sym} -340 140 1 0 {name=pvd sig_type=std_logic lab=VDPWR}
C {devices/gnd.sym} -340 200 0 0 {name=l2 lab=VGND}
C {devices/isource.sym} -240 170 2 1 {name=Ibias value=100u}
C {devices/lab_pin.sym} -240 140 1 0 {name=p4 sig_type=std_logic lab=Ibias}
C {devices/gnd.sym} -240 200 0 0 {name=l3 lab=VGND}
C {devices/isource.sym} -140 170 2 1 {name=Ikickd value="PULSE(0 2m 1n 20p 20p 2n 1)"}
C {devices/lab_pin.sym} -140 140 1 0 {name=pk1 sig_type=std_logic lab=out_drawn}
C {devices/gnd.sym} -140 200 0 0 {name=lk1 lab=VGND}
C {devices/isource.sym} -40 170 2 1 {name=Ikickr value="PULSE(0 2m 1n 100p 100p 5n 1)"}
C {devices/lab_pin.sym} -40 140 1 0 {name=pk2 sig_type=std_logic lab=out_routed}
C {devices/gnd.sym} -40 200 0 0 {name=lk2 lab=VGND}
C {sky130_fd_pr/corner.sym} -530 -460 0 0 {name=CORNER only_toplevel=true corner=tt}
C {devices/code_shown.sym} 1030 -700 0 0 {name=NGSPICE only_toplevel=true value="
* Two free-running 3-stage rings measured in one deck:
*   x1  as drawn  -- ideal wires, no switch matrix, no parasitics at all
*   x2  as routed -- real switch matrix, row coupling, bus wire caps, pads
*
* They oscillate ~70x apart (GHz vs tens of MHz), so no single tran serves
* both: a step fine enough to resolve x1 makes x2's window enormous, and a
* window long enough for x2 leaves x1 aliased. ngspice allows several tran
* runs in one .control block -- each makes its own plot (tran1, tran2, ...)
* and a .meas placed right after a tran measures THAT run. So each branch
* gets a tran sized for it, and the two graphs above read dataset 0 and 1.
*
* Startup. A real ring starts from noise. ngspice is noiseless, and a
* symmetric ring has a perfectly good stable solution with every node
* parked at the switching threshold -- from a 0V UIC start both branches
* just sit there forever. Ikickd/Ikickr inject a brief current pulse to
* break that symmetry. That is stimulus, not load.
*
* No load capacitors, deliberately. out_drawn/out_routed is the loop's own
* feedback node, not an output pad, so a cap there changes the oscillator
* rather than modelling a probe. Measured on this circuit: 100pF stops x1
* oscillating outright (it latches at ~1.6V), and even 1pF drags it from
* 2.5GHz to 1.5GHz with the swing already collapsing. x2 carries its own
* real parasitics and needs nothing added. This is why tb_inverter.sch's
* 100pF did NOT belong here: there the loaded pad sits outside any
* feedback path, so it models a probe and only sets the observed rise time.
*
* Vgnd below is what gives ngspice its node 0. xschem emits ground as a
* named global net (VGND, plus .GLOBAL VGND), never as SPICE node 0, so
* without Vgnd nothing in this deck connects to 0 at all and the whole
* circuit floats. .option rshunt, which the other testbenches here carry,
* papers over that by strapping every node to 0 through a huge resistor:
* enough to make the matrix solvable, but the absolute level is then set
* only by the balance of those shunt currents. That is a real hazard --
* with x2 deleted for debugging, the 100uA Ibias source lost its only DC
* return path and the entire circuit floated to about -277kV, with the
* real signals riding on top of it. Every node reading -277777.xx meant a
* floating reference, not a broken circuit. Vgnd fixes it at the source.
*
* rshunt is then unnecessary here and merely costs solve time on x2 --
* measured 1m54 without it, 2m40 with, same answer to 7 digits. But do
* NOT delete it from tb_inverter.sch or tb_diffamp.sch: those have no
* Vgnd line, so rshunt is the only thing making them solvable at all.

Vgnd VGND 0 0

.option reltol=0.01
.control
  save v(out_drawn) v(out_routed)

  tran 5p 40n UIC
  meas tran period_drawn TRIG v(out_drawn) VAL=1.5 RISE=5 TARG v(out_drawn) VAL=1.5 RISE=6
  let freq_drawn = 1/period_drawn
  print freq_drawn

  tran 100p 600n UIC
  meas tran period_routed TRIG v(out_routed) VAL=1.5 RISE=3 TARG v(out_routed) VAL=1.5 RISE=4
  let freq_routed = 1/period_routed
  print freq_routed

  write tb_ring.raw tran1.v(out_drawn) tran2.v(out_routed)
.endc
"}
C {devices/launcher.sym} 210 -280 0 0 {name=h5
descr="load waves"
tclcommand="xschem raw_read $netlist_dir/tb_ring.raw tran"
}
C {devices/launcher.sym} 210 -240 0 0 {name=h6
descr="generate routed spice"
tclcommand="execute 1 sh tools/regenerate_routed.sh examples/ringosc/ring.sch"
}
