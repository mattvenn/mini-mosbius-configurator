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
T {Draw your circuit here. Wire it to the ports below --} -170 -360 0 0 0.25 0.25 {}
T {those are exactly the chip's real pins (SPEC.md Sec 3.1b):} -170 -330 0 0 0.25 0.25 {}
T {ibias, ua1..ua5, VAPWR (3.3V), VDPWR (1.8V), VGND. Use} -170 -300 0 0 0.25 0.25 {}
T {mosbius_nmos/mosbius_pmos/mosbius_nsink/mosbius_psource/} -170 -270 0 0 0.25 0.25 {}
T {mosbius_ota from mosbius_lib -- the router (M3) maps them} -170 -240 0 0 0.25 0.25 {}
T {onto real chip devices. You cannot wire anything except} -170 -210 0 0 0.25 0.25 {}
T {through these ports -- there is no "off chip" by construction.} -170 -180 0 0 0.25 0.25 {}
N -190 -140 400 -140 {lab=VAPWR}
N -200 210 400 210 {lab=VGND}
N -110 40 -80 40 {lab=ua1}
N -80 -30 -80 40 {lab=ua1}
N -80 -30 -70 -30 {lab=ua1}
N -80 40 -80 140 {lab=ua1}
N -80 140 -70 140 {lab=ua1}
N -30 0 -30 110 {lab=ua2}
N -30 40 70 40 {lab=ua2}
N -30 -140 -30 -60 {lab=VAPWR}
N -30 170 -30 210 {lab=VGND}
C {devices/iopin.sym} -400 -100 0 0 {name=p1 lab=ibias}
C {devices/iopin.sym} -110 40 2 0 {name=p2 lab=ua1}
C {devices/iopin.sym} 70 40 0 0 {name=p3 lab=ua2}
C {devices/iopin.sym} -400 20 0 0 {name=p4 lab=ua3}
C {devices/iopin.sym} -400 60 0 0 {name=p5 lab=ua4}
C {devices/iopin.sym} -400 100 0 0 {name=p6 lab=ua5}
C {devices/iopin.sym} 400 -140 2 1 {name=p7 lab=VAPWR}
C {devices/iopin.sym} 400 -20 0 1 {name=p8 lab=VDPWR}
C {devices/iopin.sym} 400 210 2 1 {name=p9 lab=VGND}
C {mosbius_nmos.sym} -50 140 0 0 {name=M1 w=1}
C {mosbius_pmos.sym} -50 -30 0 0 {name=M2 w=1}
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
