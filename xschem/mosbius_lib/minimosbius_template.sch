v {xschem version=3.4.8RC file_version=1.2}
G {}
K {type=subcircuit
format="@name @pinlist @symname"
template="name=x1"
}
V {}
S {}
E {}
T {Draw your circuit here. Wire it to the ports below --} -80 -300 0 0 0.25 0.25 {}
T {those are exactly the chip's real pins (SPEC.md Sec 3.1b):} -80 -270 0 0 0.25 0.25 {}
T {ibias, ua1..ua5, VAPWR (3.3V), VDPWR (1.8V), VGND. Use} -80 -240 0 0 0.25 0.25 {}
T {mosbius_nmos/mosbius_pmos/mosbius_nsink/mosbius_psource/} -80 -210 0 0 0.25 0.25 {}
T {mosbius_ota from mosbius_lib -- the router (M3) maps them} -80 -180 0 0 0.25 0.25 {}
T {onto real chip devices. You cannot wire anything except} -80 -150 0 0 0.25 0.25 {}
T {through these ports -- there is no "off chip" by construction.} -80 -120 0 0 0.25 0.25 {}
C {devices/iopin.sym} -400 -100 0 0 {name=p1 lab=ibias}
C {devices/iopin.sym} -400 -60 0 0 {name=p2 lab=ua1}
C {devices/iopin.sym} -400 -20 0 0 {name=p3 lab=ua2}
C {devices/iopin.sym} -400 20 0 0 {name=p4 lab=ua3}
C {devices/iopin.sym} -400 60 0 0 {name=p5 lab=ua4}
C {devices/iopin.sym} -400 100 0 0 {name=p6 lab=ua5}
C {devices/iopin.sym} 400 -100 0 1 {name=p7 lab=VAPWR}
C {devices/iopin.sym} 400 -20 0 1 {name=p8 lab=VDPWR}
C {devices/iopin.sym} 400 60 0 1 {name=p9 lab=VGND}
