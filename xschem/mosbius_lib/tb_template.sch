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
x2=5e-07
divx=5
subdivx=1
xlabmag=1.0
ylabmag=1.0
node="out_drawn
out_routed
ua1"
color="12 14 10"
dataset=-1
unitx=1
logx=0
logy=0
}
T {Copy this next to your design, then replace my_design.sch and} -530 -680 0 0 0.25 0.25 {}
T {my_design_routed everywhere below with your own names. Paths are} -530 -650 0 0 0.25 0.25 {}
T {relative to the repo root, where you launched xschem.} -530 -620 0 0 0.25 0.25 {}
T {x1 is your design as drawn, x2 the same design as routed onto the chip.} -530 -590 0 0 0.25 0.25 {}
T {x2 needs a generated file: ctrl-click -generate routed spice-, then} -530 -560 0 0 0.25 0.25 {}
T {press Netlist again. See examples/inverter/ for a worked version.} -530 -530 0 0 0.25 0.25 {}
C {mini_mosbius.sym} -450 -120 0 0 {name=x1
schematic="tcleval([file normalize my_design.sch])"}
C {mini_mosbius.sym} -60 -120 0 0 {name=x2
schematic=my_design_routed
spice_sym_def="tcleval([mosbius_routed_include build/my_design_routed.spice])"
tclcommand="textwindow [file normalize build/my_design_routed.spice]"}
C {devices/lab_pin.sym} -350 -40 2 0 {name=p1 sig_type=std_logic lab=Ibias}
C {devices/lab_wire.sym} -550 -200 0 0 {name=p6 sig_type=std_logic lab=ua1}
C {devices/lab_wire.sym} -550 -160 0 0 {name=p7 sig_type=std_logic lab=out_drawn}
C {devices/lab_wire.sym} -550 -120 0 0 {name=p8 sig_type=std_logic lab=ua3_drawn}
C {devices/lab_wire.sym} -550 -80 0 0 {name=p9 sig_type=std_logic lab=ua4_drawn}
C {devices/lab_wire.sym} -550 -40 0 0 {name=p10 sig_type=std_logic lab=ua5_drawn}
C {devices/lab_pin.sym} -350 -220 2 0 {name=pv1 sig_type=std_logic lab=VAPWR}
C {devices/lab_pin.sym} -350 -160 2 0 {name=pv2 sig_type=std_logic lab=VDPWR}
C {devices/lab_pin.sym} -350 -100 2 0 {name=pv3 sig_type=std_logic lab=VGND}
C {devices/lab_pin.sym} 40 -40 2 0 {name=p1b sig_type=std_logic lab=Ibias}
C {devices/lab_wire.sym} -160 -200 0 0 {name=p6b sig_type=std_logic lab=ua1}
C {devices/lab_wire.sym} -160 -160 0 0 {name=p7b sig_type=std_logic lab=out_routed}
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
C {devices/vsource.sym} -130 160 0 0 {name=Vin value="PULSE(3.3 0 10n 1n 1n 250n 500n)"}
C {devices/lab_pin.sym} -130 130 1 0 {name=pin1 sig_type=std_logic lab=ua1}
C {devices/gnd.sym} -130 190 0 0 {name=lvin lab=VGND}
C {devices/capa.sym} -300 -390 0 0 {name=Cprobe_drawn m=1 value="'cprobe'" footprint=1206 device="ceramic capacitor"}
C {devices/lab_pin.sym} -300 -420 1 0 {name=pc1 sig_type=std_logic lab=out_drawn}
C {devices/gnd.sym} -300 -360 0 0 {name=lc1 lab=VGND}
C {devices/res.sym} -260 -410 0 0 {name=Rprobe_drawn value="'rprobe'" footprint=1206 device=resistor m=1}
C {devices/lab_pin.sym} -260 -440 2 0 {name=pr_drawn sig_type=std_logic lab=out_drawn}
C {devices/gnd.sym} -260 -380 0 0 {name=lr_drawn lab=VGND}
C {devices/capa.sym} -210 -390 0 0 {name=Cprobe_routed m=1 value="'cprobe'" footprint=1206 device="ceramic capacitor"}
C {devices/lab_pin.sym} -210 -420 1 0 {name=pc2 sig_type=std_logic lab=out_routed}
C {devices/gnd.sym} -210 -360 0 0 {name=lc2 lab=VGND}
C {devices/res.sym} -80 -410 0 0 {name=Rprobe_routed value="'rprobe'" footprint=1206 device=resistor m=1}
C {devices/lab_pin.sym} -80 -440 2 0 {name=pr_routed sig_type=std_logic lab=out_routed}
C {devices/gnd.sym} -80 -380 0 0 {name=lr_routed lab=VGND}
C {sky130_fd_pr/corner.sym} -530 -460 0 0 {name=CORNER only_toplevel=true corner=tt}
C {devices/code_shown.sym} 130 -660 0 0 {name=NGSPICE only_toplevel=true value="
* Vgnd is not optional: xschem never emits SPICE node 0, so without it the
* whole circuit floats. cprobe/rprobe are one scope probe; keep both instances on it.

Vgnd VGND 0 0

* Your meter is part of the circuit, so it is modelled here, in the
* testbench, where the rest of the bench lives -- never inside the design
* block, and never in the generated <name>_routed.spice, because which
* instrument you own is a fact about your bench and not about the chip.
* Set these to what you actually measure with:
*    10x passive probe     rprobe=10meg   cprobe=10p    (the default)
*    Analog Discovery 3    rprobe=1meg    cprobe=24p
*    1x passive probe      rprobe=1meg    cprobe=100p
* The default is a 10x probe because that is the commonest instrument and
* every published number in these READMEs was measured with it. This
* repo's own silicon comparisons use the AD3 line instead, and say so.
* Resistance is the cheap half here: none of these examples drives a node
* stiffer than ~50 kOhm, so even 1 MOhm costs a couple of percent, while
* the capacitance is what sets every rise time on the sheet.
.param rprobe=10meg
.param cprobe=10p

.option reltol=0.01
.control
  save all
  tran 1n 500n
  write tb_template.raw

.endc
"}
C {devices/launcher.sym} 210 -280 0 0 {name=h5
descr="load waves"
tclcommand="xschem raw_read $netlist_dir/tb_template.raw tran"
}
C {devices/launcher.sym} 210 -240 0 0 {name=h6
descr="generate routed spice"
tclcommand="execute 1 sh tools/regenerate_routed.sh my_design.sch"
}
