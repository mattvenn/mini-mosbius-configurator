v {xschem version=3.4.8RC file_version=1.3}
G {}
K {type=subcircuit
format="@name @pinlist @symname"
template="name=x1"
}
V {}
S {}
F {}
E {}
T {This is the empty mini-MOSbius design block, and the schematic
behind mini_mosbius.sym. Copy it to start a design of your own.

Draw your circuit here. Wire it to the ports below --
those are exactly the chip's real pins:
ibias, ua1..ua5, VAPWR (3.3V), VDPWR (1.8V), VGND.

Use mosbius_nmos/mosbius_pmos/mosbius_nsink/mosbius_psource/
mosbius_ota from mosbius_lib -- the router maps them
onto real chip devices. You cannot wire anything except
through these ports.} -220 -80 0 0 0.25 0.25 {}
N -630 -100 -400 -100 {lab=ibias}
C {devices/iopin.sym} -400 -100 0 0 {name=p1 lab=ibias}
C {devices/iopin.sym} -400 -60 0 0 {name=p2 lab=ua1}
C {devices/iopin.sym} -400 -20 0 0 {name=p3 lab=ua2}
C {devices/iopin.sym} -400 20 0 0 {name=p4 lab=ua3}
C {devices/iopin.sym} -400 60 0 0 {name=p5 lab=ua4}
C {devices/iopin.sym} -400 100 0 0 {name=p6 lab=ua5}
C {devices/iopin.sym} 400 -100 0 1 {name=p7 lab=VAPWR}
C {devices/iopin.sym} 400 -20 0 1 {name=p8 lab=VDPWR}
C {devices/iopin.sym} 400 60 0 1 {name=p9 lab=VGND}
C {mosbius_bias.sym} -630 -60 0 0 {name=BIAS}
