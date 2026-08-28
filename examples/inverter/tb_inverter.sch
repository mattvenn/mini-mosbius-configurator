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
in"
color="12 14 10"
dataset=-1
unitx=1
logx=0
logy=0
}
T {CMOS inverter
 
x1 as drawn - ideal wires, no switch matrix
x2 as routed on the chip including analog mux and pads 

in=IN, ua2=OUT} -640 -730 0 0 0.5 0.5 {}
C {mini_mosbius.sym} -450 -120 0 0 {name=x1
schematic="tcleval([file normalize examples/inverter/inverter.sch])"}
C {mini_mosbius.sym} -60 -120 0 0 {name=x2
schematic=inverter_routed
spice_sym_def="tcleval([mosbius_routed_include build/inverter_routed.spice])"
tclcommand="textwindow [file normalize build/inverter_routed.spice]"}
C {devices/lab_pin.sym} -350 -40 2 0 {name=p1 sig_type=std_logic lab=ibias_drawn}
C {devices/lab_wire.sym} -550 -200 0 0 {name=p6 sig_type=std_logic lab=in}
C {devices/lab_wire.sym} -550 -160 0 0 {name=p7 sig_type=std_logic lab=out_drawn}
C {devices/lab_wire.sym} -550 -120 0 0 {name=p8 sig_type=std_logic lab=ua3_drawn}
C {devices/lab_wire.sym} -550 -80 0 0 {name=p9 sig_type=std_logic lab=ua4_drawn}
C {devices/lab_wire.sym} -550 -40 0 0 {name=p10 sig_type=std_logic lab=ua5_drawn}
C {devices/lab_pin.sym} -350 -220 2 0 {name=pv1 sig_type=std_logic lab=VAPWR}
C {devices/lab_pin.sym} -350 -160 2 0 {name=pv2 sig_type=std_logic lab=VDPWR}
C {devices/lab_pin.sym} -350 -100 2 0 {name=pv3 sig_type=std_logic lab=VGND}
C {devices/lab_pin.sym} 40 -40 2 0 {name=p1b sig_type=std_logic lab=ibias_routed}
C {devices/lab_wire.sym} -160 -200 0 0 {name=p6b sig_type=std_logic lab=in}
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
C {devices/isource.sym} -240 170 2 1 {name=Ibias_drawn value="'ibias_amps'"}
C {devices/lab_pin.sym} -240 140 1 0 {name=p4 sig_type=std_logic lab=ibias_drawn}
C {devices/gnd.sym} -240 200 0 0 {name=l3 lab=VGND}
C {devices/isource.sym} -240 300 2 1 {name=Ibias_routed value="'ibias_amps'"}
C {devices/lab_pin.sym} -240 270 1 0 {name=p4b sig_type=std_logic lab=ibias_routed}
C {devices/gnd.sym} -240 330 0 0 {name=l3b lab=VGND}
C {devices/vsource.sym} -130 160 0 0 {name=Vin value="PULSE(3.3 0 10n 1n 1n 250n 500n)"}
C {devices/lab_pin.sym} -130 130 1 0 {name=pin1 sig_type=std_logic lab=in}
C {devices/gnd.sym} -130 190 0 0 {name=lvin lab=VGND}
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
C {devices/code_shown.sym} 130 -660 0 0 {name=NGSPICE only_toplevel=true value="
Vgnd VGND 0 0

.param ibias_amps=100u
.param rprobe=10meg
.param cprobe=10p

.option reltol=0.01
.control
  save all

* DC transfer curve, for comparison against the same circuit measured on
* silicon (examples/inverter/README.md). The probe resistor is what makes
* VOH land below the rail here, exactly as it does on the bench.
  dc Vin 0 3.3 0.005
  meas dc voh_drawn  FIND v(out_drawn)  AT=0
  meas dc voh_routed FIND v(out_routed) AT=0
  meas dc vol_drawn  FIND v(out_drawn)  AT=3.3
  meas dc vol_routed FIND v(out_routed) AT=3.3
  wrdata inverter_dc_drawn.txt v(out_drawn)
  wrdata inverter_dc_routed.txt v(out_routed)

  tran 1n 500n
  meas tran trise_drawn TRIG v(out_drawn) VAL=0.33 RISE=1 TARG v(out_drawn) VAL=2.97 RISE=1
  meas tran trise_routed TRIG v(out_routed) VAL=0.33 RISE=1 TARG v(out_routed) VAL=2.97 RISE=1
  wrdata inverter_tb_in.txt v(in)
  wrdata inverter_tb_out_drawn.txt v(out_drawn)
  wrdata inverter_tb_out_routed.txt v(out_routed)
  write tb_inverter.raw

.endc
"}
C {devices/launcher.sym} 210 -280 0 0 {name=h5
descr="load waves" 
tclcommand="xschem raw_read $netlist_dir/tb_inverter.raw tran"
}
C {devices/launcher.sym} 210 -240 0 0 {name=h6
descr="generate routed spice"
tclcommand="execute 1 sh tools/regenerate_routed.sh examples/inverter/inverter.sch"
}
