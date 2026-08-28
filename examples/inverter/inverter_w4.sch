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
N -700 160 -700 -100 {lab=ibias}
N -700 -100 -400 -100 {lab=ibias}
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
C {mosbius_pmos.sym} -50 -30 0 0 {name=M2 w=4}
C {mosbius_bias.sym} -700 200 0 0 {name=BIAS}
