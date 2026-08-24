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
N -110 -30 -110 140 {lab=ua1}
N 10 80 130 80 {lab=#net1}
N -220 60 -110 60 {lab=ua1}
N -190 -140 400 -140 {lab=VAPWR}
N -200 210 400 210 {lab=VGND}
N -240 30 -240 60 {lab=ua1}
N -240 60 -220 60 {lab=ua1}
N 400 -140 920 -140 {lab=VAPWR}
N 930 -140 930 -100 {lab=VAPWR}
N 920 -140 930 -140 {lab=VAPWR}
N 400 210 930 210 {lab=VGND}
N 930 60 930 210 {lab=VGND}
N 460 -30 460 140 {lab=#net2}
N 160 -30 160 140 {lab=#net1}
N 130 80 160 80 {lab=#net1}
N 280 60 460 60 {lab=#net2}
N 580 50 710 50 {lab=ua1}
N 710 50 710 350 {lab=ua1}
N -240 350 710 350 {lab=ua1}
N -240 60 -240 350 {lab=ua1}
N -110 -30 -70 -30 {lab=ua1}
N -30 -140 -30 -60 {lab=VAPWR}
N -30 -0 -30 110 {lab=#net1}
N -30 80 10 80 {lab=#net1}
N -110 140 -70 140 {lab=ua1}
N -30 170 -30 210 {lab=VGND}
N 160 140 200 140 {lab=#net1}
N 240 60 240 110 {lab=#net2}
N 240 60 280 60 {lab=#net2}
N 240 170 240 210 {lab=VGND}
N 240 0 240 60 {lab=#net2}
N 160 -30 200 -30 {lab=#net1}
N 240 -140 240 -60 {lab=VAPWR}
N 460 -30 500 -30 {lab=#net2}
N 460 140 500 140 {lab=#net2}
N 540 170 540 210 {lab=VGND}
N 540 0 540 110 {lab=ua1}
N 540 -140 540 -60 {lab=VAPWR}
N 540 50 580 50 {lab=ua1}
C {devices/iopin.sym} -400 -100 0 0 {name=p1 lab=ibias}
C {devices/iopin.sym} -240 30 0 0 {name=p2 lab=ua1}
C {devices/iopin.sym} -390 -40 0 0 {name=p3 lab=ua2}
C {devices/iopin.sym} -400 20 0 0 {name=p4 lab=ua3}
C {devices/iopin.sym} -400 60 0 0 {name=p5 lab=ua4}
C {devices/iopin.sym} -400 100 0 0 {name=p6 lab=ua5}
C {devices/iopin.sym} 930 -100 0 1 {name=p7 lab=VAPWR}
C {devices/iopin.sym} 930 -20 0 1 {name=p8 lab=VDPWR}
C {devices/iopin.sym} 930 60 0 1 {name=p9 lab=VGND}
C {mosbius_nmos.sym} -50 140 0 0 {name=M1 w=4}
C {mosbius_pmos.sym} -50 -30 0 0 {name=M2 w=4}
C {mosbius_nmos.sym} 520 140 0 0 {name=M3 w=4}
C {mosbius_pmos.sym} 520 -30 0 0 {name=M4 w=4}
C {mosbius_nmos.sym} 220 140 0 0 {name=M5 w=4}
C {mosbius_pmos.sym} 220 -30 0 0 {name=M6 w=4}
