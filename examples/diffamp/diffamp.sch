v {xschem version=3.4.8RC file_version=1.2}
G {}
K {type=subcircuit
format="@name @pinlist @symname"
template="name=x1"
}
V {}
S {}
F {}
E {}
N 20 30 20 110 {lab=#net1}
N 20 110 100 110 {lab=#net1}
N 220 30 220 110 {lab=#net1}
N 100 110 220 110 {lab=#net1}
N 20 -170 20 -30 {lab=#net2}
N -20 -200 -20 -170 {lab=#net2}
N 180 -200 180 -170 {lab=#net2}
N 220 -170 220 -30 {lab=ua4}
N 20 -260 20 -230 {lab=VAPWR}
N 20 -260 220 -260 {lab=VAPWR}
N 220 -260 220 -230 {lab=VAPWR}
N 220 -100 330 -100 {lab=ua4}
N 140 -0 180 0 {lab=ua2}
N -77.5 0 -20 -0 {lab=ua1}
N -20 -170 -20 -122.5 {lab=#net2}
N -20 -122.5 20 -122.5 {lab=#net2}
N 20 -122.5 180 -122.5 {lab=#net2}
N 180 -170 180 -122.5 {lab=#net2}
C {mosbius_nmos.sym} 0 0 0 0 {name=M1 w=4}
C {mosbius_nmos.sym} 200 0 0 0 {name=M2 w=4}
C {mosbius_ntail.sym} 100 150 0 0 {name=T1 tail=4}
C {mosbius_pmos.sym} 0 -200 0 0 {name=M3 w=1}
C {mosbius_pmos.sym} 200 -200 0 0 {name=M4 w=1}
C {devices/iopin.sym} -300 -260 0 0 {name=p0 lab=ibias}
C {devices/iopin.sym} -77.5 0 0 1 {name=p1 lab=ua1}
C {devices/iopin.sym} 140 0 0 1 {name=p2 lab=ua2}
C {devices/iopin.sym} -300 -220 0 0 {name=p2b lab=ua3}
C {devices/iopin.sym} 330 -100 2 1 {name=p3 lab=ua4}
C {devices/iopin.sym} -300 -180 0 0 {name=p3b lab=ua5}
C {devices/iopin.sym} 20 -260 0 1 {name=p4 lab=VAPWR}
C {devices/iopin.sym} -300 -140 0 0 {name=p4b lab=VDPWR}
C {devices/iopin.sym} -300 -100 0 0 {name=p4c lab=VGND}
T {The chip's bias generator -- part of the silicon, not of your circuit.} -80 480 0 0 0.3 0.3 {}
T {ibias (pin ua0) is a current input. Mbias_ref turns it into the gate} -80 510 0 0 0.3 0.3 {}
T {voltage every NMOS mirror leg, tail bank and OTA tail copies. Mbias_copy} -80 540 0 0 0.3 0.3 {}
T {makes a 1:1 copy of it and Mbias_p turns that into ibias_p, which is what} -80 570 0 0 0.3 0.3 {}
T {the PMOS legs copy -- the chip's own ua0 -> mirror_n -> ibias_p -> mirror_p} -80 600 0 0 0.3 0.3 {}
T {chain (mirror_n.sch M1/M2, mirror_p.sch M4). Sizes are those devices'.} -80 630 0 0 0.3 0.3 {}
T {There is exactly one of these per chip, so keep exactly one per design.} -80 660 0 0 0.3 0.3 {}
C {sky130_fd_pr/nfet3_g5v0d10v5.sym} 0 780 0 0 {name=Mbias_ref
L=1
W=10
nf=2
mult=1
ad="'int((nf+1)/2) * W/nf * 0.29'"
pd="'2*int((nf+1)/2) * (W/nf + 0.29)'"
as="'int((nf+2)/2) * W/nf * 0.29'"
ps="'2*int((nf+2)/2) * (W/nf + 0.29)'"
nrd="'0.29 / W'" nrs="'0.29 / W'"
sa=0 sb=0 sd=0
model=nfet_g5v0d10v5
body=VGND
spiceprefix=X
}
C {sky130_fd_pr/nfet3_g5v0d10v5.sym} 200 780 0 0 {name=Mbias_copy
L=1
W=10
nf=2
mult=1
ad="'int((nf+1)/2) * W/nf * 0.29'"
pd="'2*int((nf+1)/2) * (W/nf + 0.29)'"
as="'int((nf+2)/2) * W/nf * 0.29'"
ps="'2*int((nf+2)/2) * (W/nf + 0.29)'"
nrd="'0.29 / W'" nrs="'0.29 / W'"
sa=0 sb=0 sd=0
model=nfet_g5v0d10v5
body=VGND
spiceprefix=X
}
C {sky130_fd_pr/pfet3_g5v0d10v5.sym} 200 640 0 0 {name=Mbias_p
L=1
W=30
nf=4
mult=1
ad="'int((nf+1)/2) * W/nf * 0.29'"
pd="'2*int((nf+1)/2) * (W/nf + 0.29)'"
as="'int((nf+2)/2) * W/nf * 0.29'"
ps="'2*int((nf+2)/2) * (W/nf + 0.29)'"
nrd="'0.29 / W'" nrs="'0.29 / W'"
sa=0 sb=0 sd=0
model=pfet_g5v0d10v5
body=VAPWR
spiceprefix=X
}
C {devices/lab_pin.sym} -20 780 2 0 {name=pbias1 sig_type=std_logic lab=ibias}
C {devices/lab_pin.sym} 20 750 1 0 {name=pbias2 sig_type=std_logic lab=ibias}
C {devices/lab_pin.sym} 20 810 3 0 {name=pbias3 sig_type=std_logic lab=VGND}
C {devices/lab_pin.sym} 180 780 2 0 {name=pbias4 sig_type=std_logic lab=ibias}
C {devices/lab_pin.sym} 220 750 1 0 {name=pbias5 sig_type=std_logic lab=ibias_p}
C {devices/lab_pin.sym} 220 810 3 0 {name=pbias6 sig_type=std_logic lab=VGND}
C {devices/lab_pin.sym} 180 640 2 0 {name=pbias7 sig_type=std_logic lab=ibias_p}
C {devices/lab_pin.sym} 220 670 3 0 {name=pbias8 sig_type=std_logic lab=ibias_p}
C {devices/lab_pin.sym} 220 610 1 0 {name=pbias9 sig_type=std_logic lab=VAPWR}
