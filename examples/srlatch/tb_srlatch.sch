v {xschem version=3.4.8RC file_version=1.2}
G {}
K {}
V {}
S {}
F {}
E {}
B 2 180 -180 980 220 {flags=graph
y1=-0.015
y2=3.4
ypos1=0
ypos2=2
divy=5
subdivy=1
unity=1
x1=0
x2=2.8e-06
divx=5
subdivx=1
xlabmag=1.0
ylabmag=1.0
node="out_drawn
out_routed
set
reset"
color="12 14 11 18"
dataset=-1
unitx=1
logx=0
logy=0
}
T {SR latch
 
x1 as drawn - ideal wires, no switch matrix
x2 as routed on the chip including analog mux and pads 

set=SET, reset=RESET} -640 -730 0 0 0.5 0.5 {}
C {mini_mosbius.sym} -450 -120 0 0 {name=x1
schematic="tcleval([file normalize examples/srlatch/srlatch.sch])"}
C {mini_mosbius.sym} -60 -120 0 0 {name=x2
schematic=srlatch_routed
spice_sym_def="tcleval([mosbius_routed_include build/srlatch_routed.spice])"
tclcommand="textwindow [file normalize build/srlatch_routed.spice]"}
C {devices/lab_pin.sym} -350 -40 2 0 {name=p1 sig_type=std_logic lab=ibias_drawn}
C {devices/lab_wire.sym} -550 -200 0 0 {name=p6 sig_type=std_logic lab=set}
C {devices/lab_wire.sym} -550 -160 0 0 {name=p7 sig_type=std_logic lab=reset}
C {devices/lab_wire.sym} -550 -120 0 0 {name=p8 sig_type=std_logic lab=out_drawn}
C {devices/lab_wire.sym} -550 -80 0 0 {name=p9 sig_type=std_logic lab=ua4_drawn}
C {devices/lab_wire.sym} -550 -40 0 0 {name=p10 sig_type=std_logic lab=ua5_drawn}
C {devices/lab_pin.sym} -350 -220 2 0 {name=pv1 sig_type=std_logic lab=VAPWR}
C {devices/lab_pin.sym} -350 -160 2 0 {name=pv2 sig_type=std_logic lab=VDPWR}
C {devices/lab_pin.sym} -350 -100 2 0 {name=pv3 sig_type=std_logic lab=VGND}
C {devices/lab_pin.sym} 40 -40 2 0 {name=p1b sig_type=std_logic lab=ibias_routed}
C {devices/lab_wire.sym} -160 -200 0 0 {name=p6b sig_type=std_logic lab=set}
C {devices/lab_wire.sym} -160 -160 0 0 {name=p7b sig_type=std_logic lab=reset}
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
C {devices/isource.sym} -240 170 2 1 {name=Ibias_drawn value="'ibias_amps'"}
C {devices/lab_pin.sym} -240 140 1 0 {name=p4 sig_type=std_logic lab=ibias_drawn}
C {devices/gnd.sym} -240 200 0 0 {name=l3 lab=VGND}
C {devices/isource.sym} -240 300 2 1 {name=Ibias_routed value="'ibias_amps'"}
C {devices/lab_pin.sym} -240 270 1 0 {name=p4b sig_type=std_logic lab=ibias_routed}
C {devices/gnd.sym} -240 330 0 0 {name=l3b lab=VGND}
C {devices/vsource.sym} -130 160 0 0 {name=Vset value="PWL(0 0 60n 0 61n 3.3 101n 3.3 102n 0 400n 0 1400n 3.3 1450n 3.3 1451n 0 2800n 0)"}
C {devices/lab_pin.sym} -130 130 1 0 {name=pin1 sig_type=std_logic lab=set}
C {devices/gnd.sym} -130 190 0 0 {name=lvin lab=VGND}
C {devices/vsource.sym} -30 160 0 0 {name=Vreset value="PWL(0 0 220n 0 221n 3.3 261n 3.3 262n 0 1600n 0 2600n 3.3 2650n 3.3 2651n 0 2800n 0)"}
C {devices/lab_pin.sym} -30 130 1 0 {name=pin2 sig_type=std_logic lab=reset}
C {devices/gnd.sym} -30 190 0 0 {name=lvin2 lab=VGND}
C {devices/capa.sym} -320 -410 0 0 {name=Cprobe_drawn m=1 value="'cprobe'" footprint=1206 device="ceramic capacitor"}
C {devices/lab_pin.sym} -320 -440 2 0 {name=pc1 sig_type=std_logic lab=out_drawn}
C {devices/gnd.sym} -320 -380 0 0 {name=lc1 lab=VGND}
C {devices/res.sym} -200 -410 0 0 {name=Rprobe_drawn value="'rprobe'" footprint=1206 device=resistor m=1}
C {devices/lab_pin.sym} -200 -440 2 0 {name=pr_drawn sig_type=std_logic lab=out_drawn}
C {devices/gnd.sym} -200 -380 0 0 {name=lr_drawn lab=VGND}
C {devices/capa.sym} -80 -410 0 0 {name=Cprobe_routed m=1 value="'cprobe'" footprint=1206 device="ceramic capacitor"}
C {devices/lab_pin.sym} -80 -440 2 0 {name=pc2 sig_type=std_logic lab=out_routed}
C {devices/gnd.sym} -80 -380 0 0 {name=lc2 lab=VGND}
C {devices/res.sym} 40 -410 0 0 {name=Rprobe_routed value="'rprobe'" footprint=1206 device=resistor m=1}
C {devices/lab_pin.sym} 40 -440 2 0 {name=pr_routed sig_type=std_logic lab=out_routed}
C {devices/gnd.sym} 40 -380 0 0 {name=lr_routed lab=VGND}
C {sky130_fd_pr/corner.sym} -530 -460 0 0 {name=CORNER only_toplevel=true corner=tt}
C {devices/code_shown.sym} 170 -720 0 0 {name=NGSPICE only_toplevel=true value="
Vgnd VGND 0 0

.param ibias_amps=100u
.param rprobe=10meg
.param cprobe=10p
.ic v(out_drawn)=0 v(out_routed)=0

.option reltol=0.01
.control
* Save the four nodes this sheet plots and measures, not every node in
* the circuit. `save all` is fine for a 300ns run, but the routed
* subcircuit carries the whole switch matrix -- hundreds of internal
* nodes -- and the write-threshold ramps made this a 2.8us run, at which
* point storing all of them ran the container out of memory and ngspice
* was killed with no error of its own (the log simply stops after the
* solver banner).
  save v(set) v(reset) v(out_drawn) v(out_routed)
  tran 100p 2800n
  meas tran qd_after_set FIND v(out_drawn) AT=110n
  meas tran qr_after_set FIND v(out_routed) AT=110n
  meas tran qd_after_reset FIND v(out_drawn) AT=280n
  meas tran qr_after_reset FIND v(out_routed) AT=280n
  meas tran treset_drawn TRIG v(reset) VAL=1.65 RISE=1 TARG v(out_drawn) VAL=1.65 FALL=1
  meas tran treset_routed TRIG v(reset) VAL=1.65 RISE=1 TARG v(out_routed) VAL=1.65 FALL=1
* The write thresholds. Everything above is a transient the bench cannot
* see -- these edges are nanoseconds wide. These four are static: ramp one
* input slowly and read the level at which the latch gives way, which is a
* contest between the pull-down being driven and the keeper PMOS holding
* the node, so it is a ratio and an oscilloscope can measure it. The pulse
* phase has already used the first rise and the first fall of each output,
* so the ramps are the second of each.
  meas tran vset_drawn FIND v(set) WHEN v(out_drawn)=1.65 RISE=2
  meas tran vset_routed FIND v(set) WHEN v(out_routed)=1.65 RISE=2
  meas tran vreset_drawn FIND v(reset) WHEN v(out_drawn)=1.65 FALL=2
  meas tran vreset_routed FIND v(reset) WHEN v(out_routed)=1.65 FALL=2
* The stored high level, read at the end of the set ramp with both inputs
* back at 0 -- this is the one static level the routed matrix moves, and
* it moves with the probe resistance, so it is what a real probe changes.
  meas tran voh_drawn FIND v(out_drawn) AT=1550n
  meas tran voh_routed FIND v(out_routed) AT=1550n
  wrdata srlatch_tb_set.txt v(set)
  wrdata srlatch_tb_reset.txt v(reset)
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
