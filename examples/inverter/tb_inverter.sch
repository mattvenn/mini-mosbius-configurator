v {xschem version=3.4.8RC file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {Level-1 (x1, ideal) vs Level-2 (x2, real silicon via mosbius_mosbius/data} -600 -700 0 0 0.25 0.25 {}
T {mosbius_device_library.spice) comparison for the inverter example.} -600 -670 0 0 0.25 0.25 {}
T {x2's spice_sym_def points at build/inverter_mosbius.spice -- regenerate it with:} -600 -640 0 0 0.25 0.25 {}
T {mosbius route build/inverter.spice --out build/inverter.mosbius.json} -600 -610 0 0 0.25 0.25 {}
T {mosbius simulate build/inverter.mosbius.json --out build/inverter_mosbius.spice} -600 -580 0 0 0.25 0.25 {}
C {examples/inverter/inverter.sym} 0 -50 0 0 {name=x1}
C {examples/inverter/inverter.sym} 800 -50 0 0 {name=x2
schematic=inverter_mosbius
spice_sym_def="tcleval(.include [file normalize build/inverter_mosbius.spice])"
tclcommand="textwindow [file normalize build/inverter_mosbius.spice]"}
C {devices/lab_pin.sym} -100 -150 1 0 {name=p1 sig_type=std_logic lab=Ibias}
C {devices/lab_wire.sym} -100 -110 1 0 {name=p6 sig_type=std_logic lab=ua1}
C {devices/lab_wire.sym} -100 -70 1 0 {name=p7 sig_type=std_logic lab=out_l1}
C {devices/lab_wire.sym} -100 -30 1 0 {name=p8 sig_type=std_logic lab=ua3}
C {devices/lab_wire.sym} -100 10 1 0 {name=p9 sig_type=std_logic lab=ua4}
C {devices/lab_wire.sym} -100 50 1 0 {name=p10 sig_type=std_logic lab=ua5}
C {devices/lab_pin.sym} 100 -150 1 0 {name=pv1 sig_type=std_logic lab=VAPWR}
C {devices/lab_pin.sym} 100 -70 1 0 {name=pv2 sig_type=std_logic lab=VDPWR}
C {devices/lab_pin.sym} 100 10 1 0 {name=pv3 sig_type=std_logic lab=VGND}
C {devices/lab_pin.sym} 700 -150 1 0 {name=p1b sig_type=std_logic lab=Ibias}
C {devices/lab_wire.sym} 700 -110 1 0 {name=p6b sig_type=std_logic lab=ua1}
C {devices/lab_wire.sym} 700 -70 1 0 {name=p7b sig_type=std_logic lab=out_l2}
C {devices/lab_wire.sym} 700 -30 1 0 {name=p8b sig_type=std_logic lab=ua3b}
C {devices/lab_wire.sym} 700 10 1 0 {name=p9b sig_type=std_logic lab=ua4b}
C {devices/lab_wire.sym} 700 50 1 0 {name=p10b sig_type=std_logic lab=ua5b}
C {devices/lab_pin.sym} 900 -150 1 0 {name=pv1b sig_type=std_logic lab=VAPWR}
C {devices/lab_pin.sym} 900 -70 1 0 {name=pv2b sig_type=std_logic lab=VDPWR}
C {devices/lab_pin.sym} 900 10 1 0 {name=pv3b sig_type=std_logic lab=VGND}
C {devices/vsource.sym} 100 150 0 0 {name=VAPWR value=3.3}
C {devices/lab_pin.sym} 100 120 1 0 {name=pva sig_type=std_logic lab=VAPWR}
C {devices/gnd.sym} 100 180 0 0 {name=l1 lab=VGND}
C {devices/vsource.sym} 200 150 0 0 {name=VDPWR value=1.8}
C {devices/lab_pin.sym} 200 120 1 0 {name=pvd sig_type=std_logic lab=VDPWR}
C {devices/gnd.sym} 200 180 0 0 {name=l2 lab=VGND}
C {devices/isource.sym} 300 150 2 1 {name=Ibias value=100u}
C {devices/lab_pin.sym} 300 120 1 0 {name=p4 sig_type=std_logic lab=Ibias}
C {devices/gnd.sym} 300 180 0 0 {name=l3 lab=VGND}
C {devices/vsource.sym} -600 150 0 0 {name=Vin value="PULSE(3.3 0 10n 1n 1n 200n 400n)"}
C {devices/lab_pin.sym} -600 120 1 0 {name=pin1 sig_type=std_logic lab=ua1}
C {devices/gnd.sym} -600 180 0 0 {name=lvin lab=VGND}
C {devices/capa.sym} 500 600 0 0 {name=Cload1 m=1 value=100p footprint=1206 device="ceramic capacitor"}
C {devices/lab_pin.sym} 500 570 1 0 {name=pc1 sig_type=std_logic lab=out_l1}
C {devices/gnd.sym} 500 630 0 0 {name=lc1 lab=VGND}
C {devices/capa.sym} 1300 600 0 0 {name=Cload2 m=1 value=100p footprint=1206 device="ceramic capacitor"}
C {devices/lab_pin.sym} 1300 570 1 0 {name=pc2 sig_type=std_logic lab=out_l2}
C {devices/gnd.sym} 1300 630 0 0 {name=lc2 lab=VGND}
C {sky130_fd_pr/corner.sym} -300 -600 0 0 {name=CORNER only_toplevel=true corner=tt}
C {devices/code_shown.sym} -300 -500 0 0 {name=NGSPICE only_toplevel=true value="
* Level-1 (out_l1, x1) vs Level-2 (out_l2, x2) inverter rise-time comparison.
* Vin pulses ua1 high->low at t=10n; the inverter output responds with a
* rising edge (examples/inverter/README.md's existing Level-1 methodology,
* now driven from a real xschem testbench instead of a hand-patched netlist).
.option rshunt=1e11
.control
  save all
* Vin's PULSE args give one period every 400n (falls at 10n, rises back
* at 212n) -- one period covers both .meas edges with margin, and ngspice
* inserts breakpoints at the PULSE's own transition times regardless of
* the step below, so 1n doesn't blur the 1n rise/fall edges. Without an
* explicit Tmax, this step value is also the solver's max internal
* timestep, so this is the actual runtime knob -- 100p over 1u forced >=
* 10000 steps through the full switch-matrix circuit for no accuracy gain.
  tran 1n 400n
  meas tran trise_l1 TRIG v(out_l1) VAL=0.33 RISE=1 TARG v(out_l1) VAL=2.97 RISE=1
  meas tran trise_l2 TRIG v(out_l2) VAL=0.33 RISE=1 TARG v(out_l2) VAL=2.97 RISE=1
  wrdata inverter_tb_ua1.txt v(ua1)
  wrdata inverter_tb_out_l1.txt v(out_l1)
  wrdata inverter_tb_out_l2.txt v(out_l2)
.endc
"}
