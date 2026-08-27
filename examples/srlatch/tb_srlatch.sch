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
x2=4e-07
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
T {The same SR latch twice: x1 as drawn (ideal wires, no switch matrix)} -530 -680 0 0 0.25 0.25 {}
T {and x2 as routed onto the real chip. Both are mini_mosbius.sym --} -530 -650 0 0 0.25 0.25 {}
T {schematic= is what says which one an instance stands for.} -530 -620 0 0 0.25 0.25 {}
T {ua1=SET, ua2=RESET (shared, drive both branches identically), ua3=Q} -530 -590 0 0 0.25 0.25 {}
T {(out_drawn/out_routed here, one per branch, per examples/srlatch/README.md).} -530 -560 0 0 0.25 0.25 {}
T {x2 needs build/srlatch_routed.spice, which is generated -- ctrl-click -generate routed spice-, then Netlist again.} -530 -530 0 0 0.25 0.25 {}
C {mini_mosbius.sym} -450 -120 0 0 {name=x1
schematic="tcleval([file normalize examples/srlatch/srlatch.sch])"}
C {mini_mosbius.sym} -60 -120 0 0 {name=x2
schematic=srlatch_routed
spice_sym_def="tcleval([mosbius_routed_include build/srlatch_routed.spice])"
tclcommand="textwindow [file normalize build/srlatch_routed.spice]"}
C {devices/lab_pin.sym} -350 -40 2 0 {name=p1 sig_type=std_logic lab=Ibias}
C {devices/lab_wire.sym} -550 -200 0 0 {name=p6 sig_type=std_logic lab=ua1}
C {devices/lab_wire.sym} -550 -160 0 0 {name=p7 sig_type=std_logic lab=ua2}
C {devices/lab_wire.sym} -550 -120 0 0 {name=p8 sig_type=std_logic lab=out_drawn}
C {devices/lab_wire.sym} -550 -80 0 0 {name=p9 sig_type=std_logic lab=ua4_drawn}
C {devices/lab_wire.sym} -550 -40 0 0 {name=p10 sig_type=std_logic lab=ua5_drawn}
C {devices/lab_pin.sym} -350 -220 2 0 {name=pv1 sig_type=std_logic lab=VAPWR}
C {devices/lab_pin.sym} -350 -160 2 0 {name=pv2 sig_type=std_logic lab=VDPWR}
C {devices/lab_pin.sym} -350 -100 2 0 {name=pv3 sig_type=std_logic lab=VGND}
C {devices/lab_pin.sym} 40 -40 2 0 {name=p1b sig_type=std_logic lab=Ibias}
C {devices/lab_wire.sym} -160 -200 0 0 {name=p6b sig_type=std_logic lab=ua1}
C {devices/lab_wire.sym} -160 -160 0 0 {name=p7b sig_type=std_logic lab=ua2}
C {devices/lab_wire.sym} -160 -120 0 0 {name=p8b sig_type=std_logic lab=out_routed}
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
C {devices/vsource.sym} -130 160 0 0 {name=Vset value="PULSE(0 3.3 60n 1n 1n 40n 1000n)"}
C {devices/lab_pin.sym} -130 130 1 0 {name=pin1 sig_type=std_logic lab=ua1}
C {devices/gnd.sym} -130 190 0 0 {name=lvin lab=VGND}
C {devices/vsource.sym} -30 160 0 0 {name=Vreset value="PULSE(0 3.3 220n 1n 1n 40n 1000n)"}
C {devices/lab_pin.sym} -30 130 1 0 {name=pin2 sig_type=std_logic lab=ua2}
C {devices/gnd.sym} -30 190 0 0 {name=lvin2 lab=VGND}
C {devices/capa.sym} -300 -390 0 0 {name=Cload_drawn m=1 value="'cload'" footprint=1206 device="ceramic capacitor"}
C {devices/lab_pin.sym} -300 -420 1 0 {name=pc1 sig_type=std_logic lab=out_drawn}
C {devices/gnd.sym} -300 -360 0 0 {name=lc1 lab=VGND}
C {devices/capa.sym} -210 -390 0 0 {name=Cload_routed m=1 value="'cload'" footprint=1206 device="ceramic capacitor"}
C {devices/lab_pin.sym} -210 -420 1 0 {name=pc2 sig_type=std_logic lab=out_routed}
C {devices/gnd.sym} -210 -360 0 0 {name=lc2 lab=VGND}
C {sky130_fd_pr/corner.sym} -530 -460 0 0 {name=CORNER only_toplevel=true corner=tt}
C {devices/code_shown.sym} 130 -660 0 0 {name=NGSPICE only_toplevel=true value="
* SET/RESET response of the same SR latch as drawn (out_drawn, x1) and as
* routed onto the real chip (out_routed, x2). SET pulses ua1 high 60-100ns,
* RESET pulses ua2 high 220-260ns (examples/srlatch/README.md's own
* PULSE() values) -- both shared across x1/x2, so the only difference
* between out_drawn and out_routed is as-drawn vs as-routed fidelity.
* Power-up state is arbitrary (no stable fixed point before either pulse
* arrives, same reasoning as the ring oscillator's free-running loop), so
* the meaningful measurements are AFTER each forcing pulse, not before.
* Vgnd is what gives ngspice its node 0. xschem emits ground as a named
* global net (VGND, plus .GLOBAL VGND), never as SPICE node 0, so without
* it nothing in this deck connects to 0 and the whole circuit floats.
* .option rshunt used to hide that by strapping every node to 0 through a
* huge resistor -- solvable, but the absolute level was then set only by
* the balance of those shunt currents, so any current with no DC return
* path dragged the entire circuit thousands of volts away from 0 with the
* real signals riding on top. Ground it properly instead; rshunt is then
* unnecessary. See examples/ringosc/tb_ring.sch for the worked case.

Vgnd VGND 0 0

.param cload=10p

.option reltol=0.01
.control
  save all
  tran 100p 400n
  meas tran qd_after_set FIND v(out_drawn) AT=110n
  meas tran qr_after_set FIND v(out_routed) AT=110n
  meas tran qd_after_reset FIND v(out_drawn) AT=280n
  meas tran qr_after_reset FIND v(out_routed) AT=280n
  meas tran treset_drawn TRIG v(ua2) VAL=1.65 RISE=1 TARG v(out_drawn) VAL=1.65 FALL=1
  meas tran treset_routed TRIG v(ua2) VAL=1.65 RISE=1 TARG v(out_routed) VAL=1.65 FALL=1
  wrdata srlatch_tb_ua1.txt v(ua1)
  wrdata srlatch_tb_ua2.txt v(ua2)
  wrdata srlatch_tb_out_drawn.txt v(out_drawn)
  wrdata srlatch_tb_out_routed.txt v(out_routed)
  write tb_srlatch.raw

.endc
"}
C {devices/launcher.sym} 210 -280 0 0 {name=h5
descr="load waves"
tclcommand="xschem raw_read $netlist_dir/tb_srlatch.raw tran"
}
C {devices/launcher.sym} 210 -240 0 0 {name=h6
descr="generate routed spice"
tclcommand="execute 1 sh tools/regenerate_routed.sh examples/srlatch/srlatch.sch"
}
