v {xschem version=3.4.8RC file_version=1.2}
G {}
K {}
V {}
S {}
F {}
E {}
B 2 180 -180 980 20 {flags=graph
y1=0.46377558
y2=2.7920956
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
dataset=0
unitx=1
logx=0
logy=0
color="9 12"
node="out_drawn

loop_drawn"}
B 2 180 60 980 260 {flags=graph
y1=1.1e-06
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
color="9 12"
node="out_routed
loop_routed"}
T {Ring oscillator
 
x1 as drawn - ideal wires, no switch matrix
x2 as routed on the chip including analog mux and pads 

loop - an internal node of the loop
out - the buffered output of the ring} -640 -730 0 0 0.5 0.5 {}
C {mini_mosbius.sym} -450 -120 0 0 {name=x1
schematic="tcleval([file normalize examples/ringosc/ring.sch])"}
C {mini_mosbius.sym} -60 -120 0 0 {name=x2
schematic=ring_routed
spice_sym_def="tcleval([mosbius_routed_include build/ring_routed.spice])"
tclcommand="textwindow [file normalize build/ring_routed.spice]"}
C {devices/lab_pin.sym} -350 -40 2 0 {name=p1 sig_type=std_logic lab=Ibias}
C {devices/lab_wire.sym} -550 -200 0 0 {name=p6 sig_type=std_logic lab=loop2_drawn}
C {devices/lab_wire.sym} -550 -160 0 0 {name=p7 sig_type=std_logic lab=loop_drawn}
C {devices/lab_wire.sym} -550 -120 0 0 {name=p8 sig_type=std_logic lab=out_drawn}
C {devices/lab_wire.sym} -550 -80 0 0 {name=p9 sig_type=std_logic lab=ua4_drawn}
C {devices/lab_wire.sym} -550 -40 0 0 {name=p10 sig_type=std_logic lab=ua5_drawn}
C {devices/lab_pin.sym} -350 -220 2 0 {name=pv1 sig_type=std_logic lab=VAPWR}
C {devices/lab_pin.sym} -350 -160 2 0 {name=pv2 sig_type=std_logic lab=VDPWR}
C {devices/lab_pin.sym} -350 -100 2 0 {name=pv3 sig_type=std_logic lab=VGND}
C {devices/lab_pin.sym} 40 -40 2 0 {name=p1b sig_type=std_logic lab=Ibias}
C {devices/lab_wire.sym} -160 -200 0 0 {name=p6b sig_type=std_logic lab=loop2_routed}
C {devices/lab_wire.sym} -160 -160 0 0 {name=p7b sig_type=std_logic lab=loop_routed}
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
C {devices/isource.sym} -140 170 2 1 {name=Ikickd value="PULSE(0 2m 1n 20p 20p 2n 1)"}
C {devices/lab_pin.sym} -140 140 1 0 {name=pk1 sig_type=std_logic lab=loop_drawn}
C {devices/gnd.sym} -140 200 0 0 {name=lk1 lab=VGND}
C {devices/isource.sym} -40 170 2 1 {name=Ikickr value="PULSE(0 2m 1n 100p 100p 5n 1)"}
C {devices/lab_pin.sym} -40 140 1 0 {name=pk2 sig_type=std_logic lab=loop_routed}
C {devices/gnd.sym} -40 200 0 0 {name=lk2 lab=VGND}
C {devices/capa.sym} -320 -410 0 0 {name=Cload_drawn m=1 value="'cload'" footprint=1206 device="ceramic capacitor"}
C {devices/lab_pin.sym} -320 -440 2 0 {name=pc1 sig_type=std_logic lab=out_drawn}
C {devices/gnd.sym} -320 -380 0 0 {name=lc1 lab=VGND}
C {devices/capa.sym} -140 -410 0 0 {name=Cload_routed m=1 value="'cload'" footprint=1206 device="ceramic capacitor"}
C {devices/lab_pin.sym} -140 -440 2 0 {name=pc2 sig_type=std_logic lab=out_routed}
C {devices/gnd.sym} -140 -380 0 0 {name=lc2 lab=VGND}
C {sky130_fd_pr/corner.sym} -530 -460 0 0 {name=CORNER only_toplevel=true corner=tt}
C {devices/code_shown.sym} 160 -690 0 0 {name=NGSPICE only_toplevel=true value="
Vgnd VGND 0 0

.param cload=10p

.option reltol=0.01
.control
  save v(out_drawn) v(out_routed) v(loop_drawn) v(loop_routed)

  tran 5p 40n UIC
  meas tran period_drawn TRIG v(loop_drawn) VAL=1.5 RISE=5 TARG v(loop_drawn) VAL=1.5 RISE=6
  let freq_drawn = 1/period_drawn
  print freq_drawn

  tran 100p 600n UIC
  meas tran period_routed TRIG v(loop_routed) VAL=1.5 RISE=3 TARG v(loop_routed) VAL=1.5 RISE=4
  let freq_routed = 1/period_routed
  print freq_routed

  write tb_ring.raw tran1.all tran2.all
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
