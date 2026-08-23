v {xschem version=3.4.8RC file_version=1.2}
G {}
K {}
V {}
S {}
F {}
E {}
B 2 110 -170 910 230 {flags=graph
y1=0.012
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
node="out_l1
out_l2"
color="4 5"
dataset=-1
unitx=1
logx=0
logy=0
}
T {Level-1 (x1, ideal) vs Level-2 (x2, real silicon via mosbius_mosbius/data} -450 -680 0 0 0.25 0.25 {}
T {mosbius_device_library.spice) comparison for the inverter example.} -450 -650 0 0 0.25 0.25 {}
T {x2's spice_sym_def points at build/inverter_mosbius.spice -- regenerate it with:} -450 -620 0 0 0.25 0.25 {}
T {mosbius route build/inverter.spice --out build/inverter.mosbius.json} -450 -590 0 0 0.25 0.25 {}
T {mosbius simulate build/inverter.mosbius.json --out build/inverter_mosbius.spice} -450 -560 0 0 0.25 0.25 {}
C {examples/inverter/inverter.sym} -360 -120 0 0 {name=x1}
C {examples/inverter/inverter.sym} -60 -130 0 0 {name=x2
schematic=inverter_mosbius
spice_sym_def="tcleval(.include [file normalize build/inverter_mosbius.spice])"
tclcommand="textwindow [file normalize build/inverter_mosbius.spice]"}
C {devices/lab_pin.sym} -460 -220 1 0 {name=p1 sig_type=std_logic lab=Ibias}
C {devices/lab_wire.sym} -460 -180 1 0 {name=p6 sig_type=std_logic lab=ua1}
C {devices/lab_wire.sym} -460 -140 1 0 {name=p7 sig_type=std_logic lab=out_l1}
C {devices/lab_wire.sym} -460 -100 1 0 {name=p8 sig_type=std_logic lab=ua3}
C {devices/lab_wire.sym} -460 -60 1 0 {name=p9 sig_type=std_logic lab=ua4}
C {devices/lab_wire.sym} -460 -20 1 0 {name=p10 sig_type=std_logic lab=ua5}
C {devices/lab_pin.sym} -260 -220 1 0 {name=pv1 sig_type=std_logic lab=VAPWR}
C {devices/lab_pin.sym} -260 -140 1 0 {name=pv2 sig_type=std_logic lab=VDPWR}
C {devices/lab_pin.sym} -260 -60 1 0 {name=pv3 sig_type=std_logic lab=VGND}
C {devices/lab_pin.sym} -160 -230 1 0 {name=p1b sig_type=std_logic lab=Ibias}
C {devices/lab_wire.sym} -160 -190 1 0 {name=p6b sig_type=std_logic lab=ua1}
C {devices/lab_wire.sym} -160 -150 1 0 {name=p7b sig_type=std_logic lab=out_l2}
C {devices/lab_wire.sym} -160 -110 1 0 {name=p8b sig_type=std_logic lab=ua3b}
C {devices/lab_wire.sym} -160 -70 1 0 {name=p9b sig_type=std_logic lab=ua4b}
C {devices/lab_wire.sym} -160 -30 1 0 {name=p10b sig_type=std_logic lab=ua5b}
C {devices/lab_pin.sym} 40 -230 1 0 {name=pv1b sig_type=std_logic lab=VAPWR}
C {devices/lab_pin.sym} 40 -150 1 0 {name=pv2b sig_type=std_logic lab=VDPWR}
C {devices/lab_pin.sym} 40 -70 1 0 {name=pv3b sig_type=std_logic lab=VGND}
C {devices/vsource.sym} -440 170 0 0 {name=VAPWR value=3.3}
C {devices/lab_pin.sym} -440 140 1 0 {name=pva sig_type=std_logic lab=VAPWR}
C {devices/gnd.sym} -440 200 0 0 {name=l1 lab=VGND}
C {devices/vsource.sym} -340 170 0 0 {name=VDPWR value=1.8}
C {devices/lab_pin.sym} -340 140 1 0 {name=pvd sig_type=std_logic lab=VDPWR}
C {devices/gnd.sym} -340 200 0 0 {name=l2 lab=VGND}
C {devices/isource.sym} -240 170 2 1 {name=Ibias value=100u}
C {devices/lab_pin.sym} -240 140 1 0 {name=p4 sig_type=std_logic lab=Ibias}
C {devices/gnd.sym} -240 200 0 0 {name=l3 lab=VGND}
C {devices/vsource.sym} -130 160 0 0 {name=Vin value="PULSE(3.3 0 10n 1n 1n 200n 400n)"}
C {devices/lab_pin.sym} -130 130 1 0 {name=pin1 sig_type=std_logic lab=ua1}
C {devices/gnd.sym} -130 190 0 0 {name=lvin lab=VGND}
C {devices/capa.sym} -220 -390 0 0 {name=Cload1 m=1 value=100p footprint=1206 device="ceramic capacitor"}
C {devices/lab_pin.sym} -220 -420 1 0 {name=pc1 sig_type=std_logic lab=out_l1}
C {devices/gnd.sym} -220 -360 0 0 {name=lc1 lab=VGND}
C {devices/capa.sym} -130 -390 0 0 {name=Cload2 m=1 value=100p footprint=1206 device="ceramic capacitor"}
C {devices/lab_pin.sym} -130 -420 1 0 {name=pc2 sig_type=std_logic lab=out_l2}
C {devices/gnd.sym} -130 -360 0 0 {name=lc2 lab=VGND}
C {sky130_fd_pr/corner.sym} -450 -460 0 0 {name=CORNER only_toplevel=true corner=tt}
C {devices/code_shown.sym} 130 -660 0 0 {name=NGSPICE only_toplevel=true value="
* Level-1 (out_l1, x1) vs Level-2 (out_l2, x2) inverter rise-time comparison.
* Vin pulses ua1 high->low at t=10n; the inverter output responds with a
* rising edge (examples/inverter/README.md's existing Level-1 methodology,
* now driven from a real xschem testbench instead of a hand-patched netlist).
.option rshunt=1e11
.control
  save all
  tran 1n 400n
  meas tran trise_l1 TRIG v(out_l1) VAL=0.33 RISE=1 TARG v(out_l1) VAL=2.97 RISE=1
  meas tran trise_l2 TRIG v(out_l2) VAL=0.33 RISE=1 TARG v(out_l2) VAL=2.97 RISE=1
  wrdata inverter_tb_ua1.txt v(ua1)
  wrdata inverter_tb_out_l1.txt v(out_l1)
  wrdata inverter_tb_out_l2.txt v(out_l2)
  write tb_inverter.raw

.endc
"}
C {devices/launcher.sym} 210 -280 0 0 {name=h5
descr="load waves" 
tclcommand="xschem raw_read $netlist_dir/tb_inverter.raw tran"
}
