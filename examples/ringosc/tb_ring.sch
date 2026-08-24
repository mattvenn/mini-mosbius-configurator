v {xschem version=3.4.8RC file_version=1.2}
G {}
K {}
V {}
S {}
F {}
E {}
B 2 180 -180 980 220 {flags=graph
y1=-0.0034
y2=3.3
ypos1=0
ypos2=2
divy=5
subdivy=1
unity=1
x1=0
x2=2e-07
divx=5
subdivx=1
xlabmag=1.0
ylabmag=1.0
node="out_drawn
out_routed"
color="12 14"
dataset=-1
unitx=1
logx=0
logy=0
}
T {The same 3-stage ring oscillator twice: x1 as drawn (ideal wires, no switch matrix)} -530 -680 0 0 0.25 0.25 {}
T {and x2 as routed onto the real chip. Both are mini_mosbius.sym --} -530 -650 0 0 0.25 0.25 {}
T {schematic= is what says which one an instance stands for.} -530 -620 0 0 0.25 0.25 {}
T {No input pin: ring.sch's loop closes through ua1, so ua1 IS out_drawn/out_routed here.} -530 -590 0 0 0.25 0.25 {}
T {tran ... UIC starts both at 0V -- an odd number of inversions has no fixed point, so each free-runs.} -530 -560 0 0 0.25 0.25 {}
T {x2 needs build/ring_routed.spice, which is generated -- ctrl-click -generate routed spice-, then Netlist again.} -530 -530 0 0 0.25 0.25 {}
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
C {devices/capa.sym} -300 -390 0 0 {name=Cload1 m=1 value=100p footprint=1206 device="ceramic capacitor"}
C {devices/lab_pin.sym} -300 -420 1 0 {name=pc1 sig_type=std_logic lab=out_drawn}
C {devices/gnd.sym} -300 -360 0 0 {name=lc1 lab=VGND}
C {devices/capa.sym} -210 -390 0 0 {name=Cload2 m=1 value=100p footprint=1206 device="ceramic capacitor"}
C {devices/lab_pin.sym} -210 -420 1 0 {name=pc2 sig_type=std_logic lab=out_routed}
C {devices/gnd.sym} -210 -360 0 0 {name=lc2 lab=VGND}
C {sky130_fd_pr/corner.sym} -530 -460 0 0 {name=CORNER only_toplevel=true corner=tt}
C {devices/code_shown.sym} 130 -660 0 0 {name=NGSPICE only_toplevel=true value="
* Free-running period of the same 3-stage ring oscillator as drawn
* (out_drawn, x1) and as routed onto the real chip (out_routed, x2).
* ring.sch has no input pin -- its loop closes back through ua1, which is
* what out_drawn/out_routed actually is here. As of 2026-08-24 ring.sch
* builds the SAME topology as the bitstream measured at ~30MHz on real
* silicon (380088...0014, examples/ringosc/README.md): nmos_a/pmos_a is
* the first inverting stage, ndiffpair+/pdiffpair+ and ndiffpair-/
* pdiffpair- (standalone-tied, no mosbius_ntail/ptail drawn) are the
* other two, loop ua2 -> ua1 -> ua4 -> ua2. Routing ring.sch reproduces
* that design's device roles and wiring exactly, but NOT its literal
* bitstream -- see ring.sch's own header comment for why (a real router
* allocator limitation, not a drawing mistake) and README.md's "Exact
* comparison" for how to simulate the literal measured bitstream instead.
* UIC skips the DC operating point and starts both branches at 0V: an odd
* number of inversions around a loop has no stable fixed point, so each
* free-runs from there on its own -- no separate stimulus needed.
* RISE=2/3 skips the first, asymmetric startup edge and measures one
* period once each branch has settled into steady oscillation.
*
* NOT YET RUN against this topology -- the 200ns window, and Cload1/
* Cload2's placement, are carried over from the OLD topology's numbers
* and need re-checking once this actually runs (build/ dev host OOMs on
* the full switch matrix, see CLAUDE.md/[[ring_oscillator_l2_sim]]; run
* on a higher-RAM machine). Two known open questions to check when it
* does run:
*  1. Cload1/Cload2's 100pF came from tb_inverter.sch, where it models an
*     external probe hanging off an output pad -- appropriate there
*     because that pad is NOT in the feedback loop. Here out_drawn/
*     out_routed (ua1) IS the loop's own feedback node, so 100pF sitting
*     there may swamp the real switch-matrix parasitics and dominate the
*     measured frequency rather than modeling real probe loading. Worth
*     checking with a smaller value (or none) once it runs.
*  2. out_drawn (x1, ideal wires, no switch matrix) may not oscillate at
*     all for the same reason it didn't under the old topology: with
*     Cload1 sitting inside a zero-delay ideal loop, the as-drawn branch
*     can end up a comparator with instant feedback and no hysteresis,
*     latching at the switching threshold instead of swinging rail to
*     rail. If so, out_drawn's .meas line below will simply fail --
*     that is a real limitation of comparing ideal-wire and real-switch-
*     matrix rings in one transient, not a bug to chase.

.option rshunt=1e11 reltol=0.01
.control
  save all
  tran 0.5n 200n UIC
  meas tran period_drawn TRIG v(out_drawn) VAL=1.65 RISE=2 TARG v(out_drawn) VAL=1.65 RISE=3
  meas tran period_routed TRIG v(out_routed) VAL=1.65 RISE=2 TARG v(out_routed) VAL=1.65 RISE=3
  let freq_routed = 1/period_routed
  print freq_routed
  let freq_drawn = 1/period_drawn
  print freq_drawn
  wrdata ring_tb_out_drawn.txt v(out_drawn)
  wrdata ring_tb_out_routed.txt v(out_routed)
  write tb_ring.raw

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
