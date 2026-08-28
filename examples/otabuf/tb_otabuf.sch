v {xschem version=3.4.8RC file_version=1.2}
G {}
K {}
V {}
S {}
F {}
E {}
B 2 180 -180 980 220 {flags=graph
y1=0.011
y2=3.1
ypos1=0
ypos2=2
divy=5
subdivy=1
unity=1
x1=0
x2=1.5e-05
divx=5
subdivx=1
xlabmag=1.0
ylabmag=1.0
node="in
out_drawn
out_routed"
color="4 12 14"
dataset=-1
unitx=1
logx=0
logy=0
}
T {OTA unity-gain follower

x1 as drawn - ideal wires, no switch matrix
x2 as routed on the chip including analog mux and pads

in = input (shared), ua2 = output (outm, fed back to inm),
ua3 = outp, the OTA-s diode-connected mirror node.

The 1u..11u ramp is the input range sweep; the step at 13u is
the slew rate measurement.} -620 -830 0 0 0.5 0.5 {}
C {mini_mosbius.sym} -480 -120 0 0 {name=x1
schematic="tcleval([file normalize examples/otabuf/otabuf.sch])"}
C {mini_mosbius.sym} -60 -120 0 0 {name=x2
schematic=otabuf_routed
spice_sym_def="tcleval([mosbius_routed_include build/otabuf_routed.spice])"
tclcommand="textwindow [file normalize build/otabuf_routed.spice]"}
C {devices/lab_pin.sym} -380 -40 2 0 {name=p1 sig_type=std_logic lab=ibias_drawn}
C {devices/lab_wire.sym} -580 -200 0 0 {name=p6 sig_type=std_logic lab=in}
C {devices/lab_wire.sym} -580 -160 0 0 {name=p7 sig_type=std_logic lab=out_drawn}
C {devices/lab_wire.sym} -580 -120 0 0 {name=p8 sig_type=std_logic lab=mirror_drawn}
C {devices/lab_wire.sym} -580 -80 0 0 {name=p9 sig_type=std_logic lab=ua4_drawn}
C {devices/lab_wire.sym} -580 -40 0 0 {name=p10 sig_type=std_logic lab=ua5_drawn}
C {devices/lab_pin.sym} -380 -220 2 0 {name=pv1 sig_type=std_logic lab=VAPWR}
C {devices/lab_pin.sym} -380 -160 2 0 {name=pv2 sig_type=std_logic lab=VDPWR}
C {devices/lab_pin.sym} -380 -100 2 0 {name=pv3 sig_type=std_logic lab=VGND}
C {devices/lab_pin.sym} 40 -40 2 0 {name=p1b sig_type=std_logic lab=ibias_routed}
C {devices/lab_wire.sym} -160 -200 0 0 {name=p6b sig_type=std_logic lab=in}
C {devices/lab_wire.sym} -160 -160 0 0 {name=p7b sig_type=std_logic lab=out_routed}
C {devices/lab_wire.sym} -160 -120 0 0 {name=p8b sig_type=std_logic lab=mirror_routed}
C {devices/lab_wire.sym} -160 -80 0 0 {name=p9b sig_type=std_logic lab=ua4_routed}
C {devices/lab_wire.sym} -160 -40 0 0 {name=p10b sig_type=std_logic lab=ua5_routed}
C {devices/lab_pin.sym} 40 -220 2 0 {name=pv1b sig_type=std_logic lab=VAPWR}
C {devices/lab_pin.sym} 40 -160 2 0 {name=pv2b sig_type=std_logic lab=VDPWR}
C {devices/lab_pin.sym} 40 -100 2 0 {name=pv3b sig_type=std_logic lab=VGND}
C {devices/vsource.sym} -560 250 0 0 {name=VAPWR value=3.3}
C {devices/lab_pin.sym} -560 220 1 0 {name=pva sig_type=std_logic lab=VAPWR}
C {devices/gnd.sym} -560 280 0 0 {name=l1 lab=VGND}
C {devices/vsource.sym} -460 250 0 0 {name=VDPWR value=1.8}
C {devices/lab_pin.sym} -460 220 1 0 {name=pvd sig_type=std_logic lab=VDPWR}
C {devices/gnd.sym} -460 280 0 0 {name=l2 lab=VGND}
C {devices/isource.sym} -360 250 2 1 {name=Ibias_drawn value="'ibias_amps'"}
C {devices/lab_pin.sym} -360 220 1 0 {name=p4 sig_type=std_logic lab=ibias_drawn}
C {devices/gnd.sym} -360 280 0 0 {name=l3 lab=VGND}
C {devices/isource.sym} -220 250 2 1 {name=Ibias_routed value="'ibias_amps'"}
C {devices/lab_pin.sym} -220 220 1 0 {name=p4b sig_type=std_logic lab=ibias_routed}
C {devices/gnd.sym} -220 280 0 0 {name=l3b lab=VGND}
C {devices/vsource.sym} -90 250 0 0 {name=Vin value="PWL(0 0.2 1u 0.2 11u 3.1 11.001u 1.0 13u 1.0 13.001u 2.3 15u 2.3)"}
C {devices/lab_pin.sym} -90 220 1 0 {name=pin1 sig_type=std_logic lab=in}
C {devices/gnd.sym} -90 280 0 0 {name=lvin lab=VGND}
C {devices/capa.sym} -350 -420 0 0 {name=Cprobe_drawn m=1 value="'cprobe'" footprint=1206 device="ceramic capacitor"}
C {devices/lab_pin.sym} -350 -450 2 0 {name=pc1 sig_type=std_logic lab=out_drawn}
C {devices/gnd.sym} -350 -390 0 0 {name=lc1 lab=VGND}
C {devices/res.sym} -230 -420 0 0 {name=Rprobe_drawn value="'rprobe'" footprint=1206 device=resistor m=1}
C {devices/lab_pin.sym} -230 -450 2 0 {name=pr_drawn sig_type=std_logic lab=out_drawn}
C {devices/gnd.sym} -230 -390 0 0 {name=lr_drawn lab=VGND}
C {devices/capa.sym} -80 -420 0 0 {name=Cprobe_routed m=1 value="'cprobe'" footprint=1206 device="ceramic capacitor"}
C {devices/lab_pin.sym} -80 -450 2 0 {name=pc2 sig_type=std_logic lab=out_routed}
C {devices/gnd.sym} -80 -390 0 0 {name=lc2 lab=VGND}
C {devices/res.sym} 30 -420 0 0 {name=Rprobe_routed value="'rprobe'" footprint=1206 device=resistor m=1}
C {devices/lab_pin.sym} 30 -450 2 0 {name=pr_routed sig_type=std_logic lab=out_routed}
C {devices/gnd.sym} 30 -390 0 0 {name=lr_routed lab=VGND}
C {sky130_fd_pr/corner.sym} -530 -460 0 0 {name=CORNER only_toplevel=true corner=tt}
C {devices/code_shown.sym} 420 -990 0 0 {name=NGSPICE only_toplevel=true value="
Vgnd VGND 0 0

.param ibias_amps=100u
.param rprobe=10meg
.param cprobe=10p

.option reltol=0.01
.control
  save all
  tran 5n 15u
  meas tran vin_lo         FIND v(in)          AT=3.76u
  meas tran vout_drawn_lo  FIND v(out_drawn)   AT=3.76u
  meas tran vout_routed_lo FIND v(out_routed)  AT=3.76u
  meas tran vin_mid         FIND v(in)         AT=6u
  meas tran vout_drawn_mid  FIND v(out_drawn)  AT=6u
  meas tran vout_routed_mid FIND v(out_routed) AT=6u
  meas tran vin_hi         FIND v(in)          AT=8.93u
  meas tran vout_drawn_hi  FIND v(out_drawn)   AT=8.93u
  meas tran vout_routed_hi FIND v(out_routed)  AT=8.93u
  let off_drawn_lo   = vout_drawn_lo  - vin_lo
  let off_drawn_mid  = vout_drawn_mid - vin_mid
  let off_drawn_hi   = vout_drawn_hi  - vin_hi
  let off_routed_lo  = vout_routed_lo  - vin_lo
  let off_routed_mid = vout_routed_mid - vin_mid
  let off_routed_hi  = vout_routed_hi  - vin_hi
  print off_drawn_lo off_drawn_mid off_drawn_hi
  print off_routed_lo off_routed_mid off_routed_hi
  meas tran t1_drawn  WHEN v(out_drawn)=1.3  RISE=1 TD=13u
  meas tran t2_drawn  WHEN v(out_drawn)=2.0  RISE=1 TD=13u
  meas tran t1_routed WHEN v(out_routed)=1.3 RISE=1 TD=13u
  meas tran t2_routed WHEN v(out_routed)=2.0 RISE=1 TD=13u
  let slew_rate_drawn  = 0.7/(t2_drawn - t1_drawn)
  let slew_rate_routed = 0.7/(t2_routed - t1_routed)
  print slew_rate_drawn slew_rate_routed
  wrdata otabuf_tb.txt v(in) v(out_drawn) v(out_routed)
  write tb_otabuf.raw

.endc
"}
C {devices/launcher.sym} 210 -280 0 0 {name=h5
descr="load waves"
tclcommand="xschem raw_read $netlist_dir/tb_otabuf.raw tran"
}
C {devices/launcher.sym} 210 -240 0 0 {name=h6
descr="generate routed spice"
tclcommand="execute 1 sh tools/regenerate_routed.sh examples/otabuf/otabuf.sch"
}
