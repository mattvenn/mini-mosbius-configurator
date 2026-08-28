v {xschem version=3.4.8RC file_version=1.2}
G {}
K {}
V {}
S {}
F {}
E {}
B 2 180 -180 980 220 {flags=graph
y1=1.4
y2=2.5
ypos1=0
ypos2=2
divy=5
subdivy=1
unity=1
x1=0
x2=3e-07
divx=5
subdivx=1
xlabmag=1.0
ylabmag=1.0
node="out_drawn
out_routed
inp
inm"
color="12 14 4 10"
dataset=-1
unitx=1
logx=0
logy=0
}
T {Differential amplifier
 
x1 as drawn - ideal wires, no switch matrix
x2 as routed on the chip including analog mux and pads 

inp/inm = inputs (shared), ua4=OUT} -640 -730 0 0 0.5 0.5 {}
C {mini_mosbius.sym} -450 -120 0 0 {name=x1
schematic="tcleval([file normalize examples/diffamp/diffamp.sch])"}
C {mini_mosbius.sym} -60 -120 0 0 {name=x2
schematic=diffamp_routed
spice_sym_def="tcleval([mosbius_routed_include build/diffamp_routed.spice])"
tclcommand="textwindow [file normalize build/diffamp_routed.spice]"}
C {devices/lab_pin.sym} -350 -40 2 0 {name=p1 sig_type=std_logic lab=ibias_drawn}
C {devices/lab_wire.sym} -550 -200 0 0 {name=p6 sig_type=std_logic lab=inp}
C {devices/lab_wire.sym} -550 -160 0 0 {name=p7 sig_type=std_logic lab=inm}
C {devices/lab_wire.sym} -550 -120 0 0 {name=p8 sig_type=std_logic lab=ua3_drawn}
C {devices/lab_wire.sym} -550 -80 0 0 {name=p9 sig_type=std_logic lab=out_drawn}
C {devices/lab_wire.sym} -550 -40 0 0 {name=p10 sig_type=std_logic lab=ua5_drawn}
C {devices/lab_pin.sym} -350 -220 2 0 {name=pv1 sig_type=std_logic lab=VAPWR}
C {devices/lab_pin.sym} -350 -160 2 0 {name=pv2 sig_type=std_logic lab=VDPWR}
C {devices/lab_pin.sym} -350 -100 2 0 {name=pv3 sig_type=std_logic lab=VGND}
C {devices/lab_pin.sym} 40 -40 2 0 {name=p1b sig_type=std_logic lab=ibias_routed}
C {devices/lab_wire.sym} -160 -200 0 0 {name=p6b sig_type=std_logic lab=inp}
C {devices/lab_wire.sym} -160 -160 0 0 {name=p7b sig_type=std_logic lab=inm}
C {devices/lab_wire.sym} -160 -120 0 0 {name=p8b sig_type=std_logic lab=ua3_routed}
C {devices/lab_wire.sym} -160 -80 0 0 {name=p9b sig_type=std_logic lab=out_routed}
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
C {devices/isource.sym} -550 170 2 1 {name=Ibias_routed value="'ibias_amps'"}
C {devices/lab_pin.sym} -550 140 1 0 {name=p4b sig_type=std_logic lab=ibias_routed}
C {devices/gnd.sym} -550 200 0 0 {name=l3b lab=VGND}
C {devices/vsource.sym} -130 160 0 0 {name=Vinp value="PWL(0 1.5 999n 1.5 1000n 1.54 3499n 1.54 3500n 1.46 5999n 1.46 6000n 1.5)"}
C {devices/lab_pin.sym} -130 130 1 0 {name=pin1 sig_type=std_logic lab=inp}
C {devices/gnd.sym} -130 190 0 0 {name=lvin lab=VGND}
C {devices/vsource.sym} -30 160 0 0 {name=Vinm value=1.5}
C {devices/lab_pin.sym} -30 130 1 0 {name=pin2 sig_type=std_logic lab=inm}
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
C {devices/code_shown.sym} 140 -810 0 0 {name=NGSPICE only_toplevel=true value="
Vgnd VGND 0 0

.param ibias_amps=100u
.param rprobe=10meg
.param cprobe=10p

.option reltol=0.01
.control
  save all
  tran 5n 6.5u
  meas tran vout_drawn_base FIND v(out_drawn) AT=995n
  meas tran vout_drawn_pos FIND v(out_drawn) AT=3495n
  meas tran vout_drawn_neg FIND v(out_drawn) AT=5995n
  meas tran vout_routed_base FIND v(out_routed) AT=995n
  meas tran vout_routed_pos FIND v(out_routed) AT=3495n
  meas tran vout_routed_neg FIND v(out_routed) AT=5995n
  let gain_drawn_pos  = (vout_drawn_pos - vout_drawn_base)/0.04
  let gain_drawn_neg  = (vout_drawn_base - vout_drawn_neg)/0.04
  let gain_routed_pos = (vout_routed_pos - vout_routed_base)/0.04
  let gain_routed_neg = (vout_routed_base - vout_routed_neg)/0.04
  print gain_drawn_pos gain_drawn_neg gain_routed_pos gain_routed_neg
  wrdata diffamp_tb_inp.txt v(inp)
  wrdata diffamp_tb_out_drawn.txt v(out_drawn)
  wrdata diffamp_tb_out_routed.txt v(out_routed)
  write tb_diffamp.raw

.endc
"}
C {devices/launcher.sym} 210 -280 0 0 {name=h5
descr="load waves"
tclcommand="xschem raw_read $netlist_dir/tb_diffamp.raw tran"
}
C {devices/launcher.sym} 210 -240 0 0 {name=h6
descr="generate routed spice"
tclcommand="execute 1 sh tools/regenerate_routed.sh examples/diffamp/diffamp.sch"
}
