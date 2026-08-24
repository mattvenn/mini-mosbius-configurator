v {xschem version=3.4.8RC file_version=1.2}
G {}
K {}
V {}
S {}
E {}
N 100 100 100 120 {
lab=VAPWR}
N 200 100 200 120 {
lab=VDPWR}
N 300 100 300 120 {
lab=Ibias}
T {Copy this file alongside your design.sch (built from} -80 -260 0 0 0.25 0.25 {}
T {mini_mosbius.sch), then edit x1's schematic= attribute to} -80 -230 0 0 0.25 0.25 {}
T {name it: schematic=my_design.sch -- keep the .sch, a bare name} -80 -200 0 0 0.25 0.25 {}
T {silently netlists an empty block. Stimulus goes in .control below.} -80 -170 0 0 0.25 0.25 {}
C {mini_mosbius.sym} 0 -50 0 0 {name=x1
schematic=mini_mosbius.sch}
C {devices/vsource.sym} 100 150 0 0 {name=VAPWR value=3.3}
C {devices/gnd.sym} 100 180 0 0 {name=l1 lab=GND}
C {devices/lab_pin.sym} 100 100 1 0 {name=p2 sig_type=std_logic lab=VAPWR}
C {devices/vsource.sym} 200 150 0 0 {name=VDPWR value=1.8}
C {devices/gnd.sym} 200 180 0 0 {name=l2 lab=GND}
C {devices/lab_pin.sym} 200 100 1 0 {name=p3 sig_type=std_logic lab=VDPWR}
C {devices/isource.sym} 300 150 2 1 {name=Ibias value=100u}
C {devices/gnd.sym} 300 180 0 0 {name=l3 lab=GND}
C {devices/lab_pin.sym} 300 100 1 0 {name=p4 sig_type=std_logic lab=Ibias}
C {devices/lab_pin.sym} 100 -150 1 0 {name=pv1 sig_type=std_logic lab=VAPWR}
C {devices/lab_pin.sym} 100 -90 1 0 {name=pv2 sig_type=std_logic lab=VDPWR}
C {devices/lab_pin.sym} 100 -30 1 0 {name=pv3 sig_type=std_logic lab=VGND}
C {devices/gnd.sym} 500 10 0 0 {name=l4 lab=GND}
C {devices/lab_pin.sym} 500 -10 1 0 {name=p5 sig_type=std_logic lab=VGND}
C {devices/lab_pin.sym} 100 30 1 0 {name=p1 sig_type=std_logic lab=Ibias}
C {devices/lab_wire.sym} -100 -130 1 0 {name=p6 sig_type=std_logic lab=ua1}
C {devices/lab_wire.sym} -100 -90 1 0 {name=p7 sig_type=std_logic lab=ua2}
C {devices/lab_wire.sym} -100 -50 1 0 {name=p8 sig_type=std_logic lab=ua3}
C {devices/lab_wire.sym} -100 -10 1 0 {name=p9 sig_type=std_logic lab=ua4}
C {devices/lab_wire.sym} -100 30 1 0 {name=p10 sig_type=std_logic lab=ua5}
C {sky130_fd_pr/corner.sym} -300 250 0 0 {name=CORNER only_toplevel=true corner=tt}
C {devices/code_shown.sym} -300 350 0 0 {name=NGSPICE only_toplevel=true value="
* Add your stimulus (Vua1, etc.) and .control block here.
*
* Vgnd is not optional. xschem emits ground as a named global net (VGND,
* plus .GLOBAL VGND), never as SPICE node 0, so without this line nothing
* connects to 0 and the whole circuit floats -- any current with no DC
* return path then drags every node thousands of volts away from 0, with
* your real signals riding on top of the offset.
Vgnd VGND 0 0

.option reltol=0.01
.control
  save all
  tran 1n 1u
.endc
"}
