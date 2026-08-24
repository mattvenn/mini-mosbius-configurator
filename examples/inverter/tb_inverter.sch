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
T {The same inverter twice: x1 as drawn (ideal wires, no switch matrix)} -530 -680 0 0 0.25 0.25 {}
T {and x2 as routed onto the real chip. Both are mini_mosbius.sym --} -530 -650 0 0 0.25 0.25 {}
T {schematic= is what says which one an instance stands for.} -530 -620 0 0 0.25 0.25 {}
T {x2 needs build/inverter_routed.spice, which is generated, so it is not in} -530 -590 0 0 0.25 0.25 {}
T {a fresh clone. Ctrl-click the -generate routed spice- arrow to build it,} -530 -560 0 0 0.25 0.25 {}
T {then press Netlist again. Netlisting without it tells you the same thing.} -530 -530 0 0 0.25 0.25 {}
C {mini_mosbius.sym} -450 -120 0 0 {name=x1
schematic="tcleval([file normalize examples/inverter/inverter.sch])"}
C {mini_mosbius.sym} -60 -120 0 0 {name=x2
schematic=inverter_routed
spice_sym_def="tcleval([mosbius_routed_include build/inverter_routed.spice])"
tclcommand="textwindow [file normalize build/inverter_routed.spice]"}
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
C {devices/vsource.sym} -130 160 0 0 {name=Vin value="PULSE(3.3 0 10n 1n 1n 200n 400n)"}
C {devices/lab_pin.sym} -130 130 1 0 {name=pin1 sig_type=std_logic lab=ua1}
C {devices/gnd.sym} -130 190 0 0 {name=lvin lab=VGND}
C {devices/capa.sym} -300 -390 0 0 {name=Cload1 m=1 value=100p footprint=1206 device="ceramic capacitor"}
C {devices/lab_pin.sym} -300 -420 1 0 {name=pc1 sig_type=std_logic lab=out_drawn}
C {devices/gnd.sym} -300 -360 0 0 {name=lc1 lab=VGND}
C {devices/capa.sym} -210 -390 0 0 {name=Cload2 m=1 value=100p footprint=1206 device="ceramic capacitor"}
C {devices/lab_pin.sym} -210 -420 1 0 {name=pc2 sig_type=std_logic lab=out_routed}
C {devices/gnd.sym} -210 -360 0 0 {name=lc2 lab=VGND}
C {sky130_fd_pr/corner.sym} -530 -460 0 0 {name=CORNER only_toplevel=true corner=tt}
C {devices/code_shown.sym} 130 -660 0 0 {name=NGSPICE only_toplevel=true value="
* Rise time of the same inverter as drawn (out_drawn, x1) and as routed
* onto the real chip (out_routed, x2).
* Vin pulses ua1 high->low at t=10n; the inverter output responds with a
* rising edge (examples/inverter/README.md's existing as-drawn methodology,
* now driven from a real xschem testbench instead of a hand-patched netlist).

.option rshunt=1e11 reltol=0.01
.control
  save all
  tran 1n 400n
  meas tran trise_drawn TRIG v(out_drawn) VAL=0.33 RISE=1 TARG v(out_drawn) VAL=2.97 RISE=1
  meas tran trise_routed TRIG v(out_routed) VAL=0.33 RISE=1 TARG v(out_routed) VAL=2.97 RISE=1
  wrdata inverter_tb_ua1.txt v(ua1)
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
