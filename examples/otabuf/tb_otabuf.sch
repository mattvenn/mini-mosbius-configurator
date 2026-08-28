v {xschem version=3.4.8RC file_version=1.2}
G {}
K {}
V {}
S {}
F {}
E {}
B 2 180 -180 980 220 {flags=graph
y1=-0.1
y2=3.4
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
the slew rate measurement.} -640 -860 0 0 0.5 0.5 {}
C {mini_mosbius.sym} -450 -120 0 0 {name=x1
schematic="tcleval([file normalize examples/otabuf/otabuf.sch])"}
C {mini_mosbius.sym} -60 -120 0 0 {name=x2
schematic=otabuf_routed
spice_sym_def="tcleval([mosbius_routed_include build/otabuf_routed.spice])"
tclcommand="textwindow [file normalize build/otabuf_routed.spice]"}
C {devices/lab_pin.sym} -350 -40 2 0 {name=p1 sig_type=std_logic lab=ibias_drawn}
C {devices/lab_wire.sym} -550 -200 0 0 {name=p6 sig_type=std_logic lab=in}
C {devices/lab_wire.sym} -550 -160 0 0 {name=p7 sig_type=std_logic lab=out_drawn}
C {devices/lab_wire.sym} -550 -120 0 0 {name=p8 sig_type=std_logic lab=mirror_drawn}
C {devices/lab_wire.sym} -550 -80 0 0 {name=p9 sig_type=std_logic lab=ua4_drawn}
C {devices/lab_wire.sym} -550 -40 0 0 {name=p10 sig_type=std_logic lab=ua5_drawn}
C {devices/lab_pin.sym} -350 -220 2 0 {name=pv1 sig_type=std_logic lab=VAPWR}
C {devices/lab_pin.sym} -350 -160 2 0 {name=pv2 sig_type=std_logic lab=VDPWR}
C {devices/lab_pin.sym} -350 -100 2 0 {name=pv3 sig_type=std_logic lab=VGND}
C {devices/lab_pin.sym} 40 -40 2 0 {name=p1b sig_type=std_logic lab=ibias_routed}
C {devices/lab_wire.sym} -160 -200 0 0 {name=p6b sig_type=std_logic lab=in}
C {devices/lab_wire.sym} -160 -160 0 0 {name=p7b sig_type=std_logic lab=out_routed}
C {devices/lab_wire.sym} -160 -120 0 0 {name=p8b sig_type=std_logic lab=mirror_routed}
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
C {devices/vsource.sym} -130 160 0 0 {name=Vin value="PWL(0 0.2 1u 0.2 11u 3.1 11.001u 1.0 13u 1.0 13.001u 2.3 15u 2.3)"}
C {devices/lab_pin.sym} -130 130 1 0 {name=pin1 sig_type=std_logic lab=in}
C {devices/gnd.sym} -130 190 0 0 {name=lvin lab=VGND}
C {devices/capa.sym} -320 -410 0 0 {name=Cprobe_drawn m=1 value="'cprobe'" footprint=1206 device="ceramic capacitor"}
C {devices/lab_pin.sym} -320 -440 2 0 {name=pc1 sig_type=std_logic lab=out_drawn}
C {devices/gnd.sym} -320 -380 0 0 {name=lc1 lab=VGND}
C {devices/res.sym} -260 -410 0 0 {name=Rprobe_drawn value="'rprobe'" footprint=1206 device=resistor m=1}
C {devices/lab_pin.sym} -260 -440 2 0 {name=pr_drawn sig_type=std_logic lab=out_drawn}
C {devices/gnd.sym} -260 -380 0 0 {name=lr_drawn lab=VGND}
C {devices/capa.sym} -140 -410 0 0 {name=Cprobe_routed m=1 value="'cprobe'" footprint=1206 device="ceramic capacitor"}
C {devices/lab_pin.sym} -140 -440 2 0 {name=pc2 sig_type=std_logic lab=out_routed}
C {devices/gnd.sym} -140 -380 0 0 {name=lc2 lab=VGND}
C {devices/res.sym} -80 -410 0 0 {name=Rprobe_routed value="'rprobe'" footprint=1206 device=resistor m=1}
C {devices/lab_pin.sym} -80 -440 2 0 {name=pr_routed sig_type=std_logic lab=out_routed}
C {devices/gnd.sym} -80 -380 0 0 {name=lr_routed lab=VGND}
C {sky130_fd_pr/corner.sym} -530 -460 0 0 {name=CORNER only_toplevel=true corner=tt}
C {devices/code_shown.sym} 140 -860 0 0 {name=NGSPICE only_toplevel=true value="
Vgnd VGND 0 0

.param ibias_amps=100u

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
  let sr_drawn  = 0.7/(t2_drawn - t1_drawn)
  let sr_routed = 0.7/(t2_routed - t1_routed)
  print sr_drawn sr_routed
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
