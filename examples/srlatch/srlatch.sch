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
T {Draw your circuit here. Wire it to the ports below --} -80 -300 0 0 0.25 0.25 {}
T {those are exactly the chip's real pins (SPEC.md Sec 3.1b):} -80 -270 0 0 0.25 0.25 {}
T {ibias, ua1..ua5, VAPWR (3.3V), VDPWR (1.8V), VGND. Use} -80 -240 0 0 0.25 0.25 {}
T {mosbius_nmos/mosbius_pmos/mosbius_nsink/mosbius_psource/} -80 -210 0 0 0.25 0.25 {}
T {mosbius_ota from mosbius_lib -- the router (M3) maps them} -80 -180 0 0 0.25 0.25 {}
T {onto real chip devices. You cannot wire anything except} -80 -150 0 0 0.25 0.25 {}
T {through these ports -- there is no "off chip" by construction.} -80 -120 0 0 0.25 0.25 {}
N -30 40 -30 80 {lab=#net1}
N -70 10 -70 110 {lab=ua3}
N 100 40 100 80 {lab=ua3}
N 60 10 60 110 {lab=#net1}
N -30 60 60 60 {lab=#net1}
N 100 60 180 60 {lab=ua3}
N 180 -80 180 60 {lab=ua3}
N -120 -80 180 -80 {lab=ua3}
N -120 -80 -120 60 {lab=ua3}
N -120 60 -70 60 {lab=ua3}
N 180 60 180 200 {lab=ua3}
N 20 60 20 200 {lab=#net1}
N 20 260 20 330 {lab=VGND}
N 20 330 180 330 {lab=VGND}
N 180 260 180 330 {lab=VGND}
N -30 -50 -30 -20 {lab=VAPWR}
N -30 -50 290 -50 {lab=VAPWR}
N 100 -50 100 -20 {lab=VAPWR}
N -30 140 -30 170 {lab=VGND}
N -30 170 290 170 {lab=VGND}
N 100 140 100 170 {lab=VGND}
N 180 330 290 330 {lab=VGND}
N 290 170 290 330 {lab=VGND}
N -50 230 -20 230 {lab=ua1}
N 120 230 140 230 {lab=ua2}
N 180 60 220 60 {lab=ua3}
C {devices/iopin.sym} -400 -100 0 0 {name=p1 lab=ibias}
C {devices/iopin.sym} -50 230 2 0 {name=p2 lab=ua1}
C {devices/iopin.sym} 120 230 2 0 {name=p3 lab=ua2}
C {devices/iopin.sym} 220 60 0 0 {name=p4 lab=ua3}
C {devices/iopin.sym} -400 60 0 0 {name=p5 lab=ua4}
C {devices/iopin.sym} -400 100 0 0 {name=p6 lab=ua5}
C {devices/iopin.sym} 290 -50 2 1 {name=p7 lab=VAPWR}
C {devices/iopin.sym} 400 -50 2 1 {name=p8 lab=VDPWR}
C {devices/iopin.sym} 290 330 2 1 {name=p9 lab=VGND}
C {mosbius_pmos.sym} -50 10 0 0 {name=M1 w=1 b=VAPWR}
C {mosbius_nmos.sym} -50 110 0 0 {name=M2 w=1 b=VGND}
C {mosbius_pmos.sym} 80 10 0 0 {name=M3 w=1 b=VAPWR}
C {mosbius_nmos.sym} 80 110 0 0 {name=M4 w=1 b=VGND}
C {mosbius_nmos.sym} 0 230 0 0 {name=M5 w=4 b=VGND}
C {mosbius_nmos.sym} 160 230 0 0 {name=M6 w=4 b=VGND}
C {mosbius_bias.sym} -700 200 0 0 {name=BIAS}
