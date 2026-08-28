v {xschem version=3.4.8RC file_version=1.2}
G {}
K {}
V {}
S {}
F {}
E {}
B 2 180 -180 980 220 {flags=graph
y1=-0.00022
y2=0.00023
ypos1=0
ypos2=2
divy=5
subdivy=1
unity=1
x1=0
x2=3.3
divx=6
subdivx=1
xlabmag=1.0
ylabmag=1.0
node="i(vam_source_drawn)
i(vam_source_routed)
i(vam_sink_drawn)
i(vam_sink_routed)"
color="12 14 4 10"
dataset=-1
unitx=1
logx=0
logy=0
}
T {Programmable current source and sink

x1 as drawn - ideal wires, no switch matrix
x2 as routed on the chip including analog mux and pads

One swept voltage source holds every output at the same voltage;
the four 0V sources are ammeters, one per leg per instance.
i(vam_...) is positive when current leaves the chip pin, so the
psource leg reads positive and the nsink leg negative.} -690 -970 0 0 0.5 0.5 {}
C {mini_mosbius.sym} -500 -120 0 0 {name=x1
schematic="tcleval([file normalize examples/currentsource/currentsource.sch])"}
C {mini_mosbius.sym} -110 -120 0 0 {name=x2
schematic=currentsource_routed
spice_sym_def="tcleval([mosbius_routed_include build/currentsource_routed.spice])"
tclcommand="textwindow [file normalize build/currentsource_routed.spice]"}
C {devices/lab_pin.sym} -400 -40 2 0 {name=p1 sig_type=std_logic lab=ibias_drawn}
C {devices/lab_wire.sym} -600 -200 0 0 {name=p6 sig_type=std_logic lab=ua1_drawn}
C {devices/lab_wire.sym} -600 -160 0 0 {name=p7 sig_type=std_logic lab=isource_drawn}
C {devices/lab_wire.sym} -600 -120 0 0 {name=p8 sig_type=std_logic lab=isink_drawn}
C {devices/lab_wire.sym} -600 -80 0 0 {name=p9 sig_type=std_logic lab=ua4_drawn}
C {devices/lab_wire.sym} -600 -40 0 0 {name=p10 sig_type=std_logic lab=ua5_drawn}
C {devices/lab_pin.sym} -400 -220 2 0 {name=pv1 sig_type=std_logic lab=VAPWR}
C {devices/lab_pin.sym} -400 -160 2 0 {name=pv2 sig_type=std_logic lab=VDPWR}
C {devices/lab_pin.sym} -400 -100 2 0 {name=pv3 sig_type=std_logic lab=VGND}
C {devices/lab_pin.sym} -10 -40 2 0 {name=p1b sig_type=std_logic lab=ibias_routed}
C {devices/lab_wire.sym} -210 -200 0 0 {name=p6b sig_type=std_logic lab=ua1_routed}
C {devices/lab_wire.sym} -210 -160 0 0 {name=p7b sig_type=std_logic lab=isource_routed}
C {devices/lab_wire.sym} -210 -120 0 0 {name=p8b sig_type=std_logic lab=isink_routed}
C {devices/lab_wire.sym} -210 -80 0 0 {name=p9b sig_type=std_logic lab=ua4_routed}
C {devices/lab_wire.sym} -210 -40 0 0 {name=p10b sig_type=std_logic lab=ua5_routed}
C {devices/lab_pin.sym} -10 -220 2 0 {name=pv1b sig_type=std_logic lab=VAPWR}
C {devices/lab_pin.sym} -10 -160 2 0 {name=pv2b sig_type=std_logic lab=VDPWR}
C {devices/lab_pin.sym} -10 -100 2 0 {name=pv3b sig_type=std_logic lab=VGND}
C {devices/vsource.sym} -530 180 0 0 {name=VAPWR value=3.3}
C {devices/lab_pin.sym} -530 150 1 0 {name=pva sig_type=std_logic lab=VAPWR}
C {devices/gnd.sym} -530 210 0 0 {name=l1 lab=VGND}
C {devices/vsource.sym} -430 180 0 0 {name=VDPWR value=1.8}
C {devices/lab_pin.sym} -430 150 1 0 {name=pvd sig_type=std_logic lab=VDPWR}
C {devices/gnd.sym} -430 210 0 0 {name=l2 lab=VGND}
C {devices/isource.sym} -330 180 2 1 {name=Ibias_drawn value="'ibias_amps'"}
C {devices/lab_pin.sym} -330 150 1 0 {name=p4 sig_type=std_logic lab=ibias_drawn}
C {devices/gnd.sym} -330 210 0 0 {name=l3 lab=VGND}
C {devices/isource.sym} -110 180 2 1 {name=Ibias_routed value="'ibias_amps'"}
C {devices/lab_pin.sym} -110 150 1 0 {name=p4b sig_type=std_logic lab=ibias_routed}
C {devices/gnd.sym} -110 210 0 0 {name=l3b lab=VGND}
C {devices/vsource.sym} -220 180 0 0 {name=Vsweep value=0}
C {devices/lab_pin.sym} -220 150 1 0 {name=psw sig_type=std_logic lab=vsweep}
C {devices/gnd.sym} -220 210 0 0 {name=lsw lab=VGND}
C {devices/vsource.sym} -570 -470 0 0 {name=Vam_source_drawn value=0}
C {devices/lab_pin.sym} -570 -500 1 0 {name=pa1 sig_type=std_logic lab=isource_drawn}
C {devices/lab_pin.sym} -570 -440 3 0 {name=pa1b sig_type=std_logic lab=vsweep}
C {devices/vsource.sym} -430 -470 0 0 {name=Vam_source_routed value=0}
C {devices/lab_pin.sym} -430 -500 1 0 {name=pa2 sig_type=std_logic lab=isource_routed}
C {devices/lab_pin.sym} -430 -440 3 0 {name=pa2b sig_type=std_logic lab=vsweep}
C {devices/vsource.sym} -290 -470 0 0 {name=Vam_sink_drawn value=0}
C {devices/lab_pin.sym} -290 -500 1 0 {name=pa3 sig_type=std_logic lab=isink_drawn}
C {devices/lab_pin.sym} -290 -440 3 0 {name=pa3b sig_type=std_logic lab=vsweep}
C {devices/vsource.sym} -150 -470 0 0 {name=Vam_sink_routed value=0}
C {devices/lab_pin.sym} -150 -500 1 0 {name=pa4 sig_type=std_logic lab=isink_routed}
C {devices/lab_pin.sym} -150 -440 3 0 {name=pa4b sig_type=std_logic lab=vsweep}
C {sky130_fd_pr/corner.sym} 730 -520 0 0 {name=CORNER only_toplevel=true corner=tt}
C {devices/code_shown.sym} 270 -970 0 0 {name=NGSPICE only_toplevel=true value="
Vgnd VGND 0 0

.param ibias_amps=100u

.option reltol=0.01
.control
  save all
  dc Vsweep 0 3.3 0.025
  meas dc i_source_drawn  FIND i(vam_source_drawn)  AT=1.65
  meas dc i_source_routed FIND i(vam_source_routed) AT=1.65
  meas dc i_sink_drawn    FIND i(vam_sink_drawn)    AT=1.65
  meas dc i_sink_routed   FIND i(vam_sink_routed)   AT=1.65
  let d_source = i_source_routed - i_source_drawn
  let d_sink   = i_sink_routed - i_sink_drawn
  print i_source_drawn i_source_routed d_source
  print i_sink_drawn i_sink_routed d_sink
  wrdata currentsource_tb.txt i(vam_source_drawn) i(vam_source_routed) i(vam_sink_drawn) i(vam_sink_routed)
  write tb_currentsource.raw

.endc
"}
C {devices/launcher.sym} 350 -460 0 0 {name=h5
descr="load waves"
tclcommand="xschem raw_read $netlist_dir/tb_currentsource.raw dc"
}
C {devices/launcher.sym} 350 -420 0 0 {name=h6
descr="generate routed spice"
tclcommand="execute 1 sh tools/regenerate_routed.sh examples/currentsource/currentsource.sch"
}
