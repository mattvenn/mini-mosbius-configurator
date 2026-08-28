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
N -450 -220 -300 -220 {lab=ibias}
T {Programmable current source and sink} -300 -420 0 0 0.5 0.5 {}
T {I1 (mosbius_psource) sources current out of ua2, down from VAPWR.} -300 -380 0 0 0.3 0.3 {}
T {I2 (mosbius_nsink) sinks current into ua3, down to VGND.} -300 -350 0 0 0.3 0.3 {}
T {ratio= is the only property either one has: 1-4 multiples of ibias.} -300 -320 0 0 0.3 0.3 {}
T {Both draw their reference from ibias, which the symbols supply} -300 -290 0 0 0.3 0.3 {}
T {implicitly -- there is no bias pin to wire (see mosbius_psource.sym).} -300 -260 0 0 0.3 0.3 {}
C {mosbius_psource.sym} -50 -110 0 0 {name=I1 ratio=2}
C {mosbius_nsink.sym} 120 -100 0 0 {name=I2 ratio=2}
C {devices/iopin.sym} -300 -220 0 0 {name=p0 lab=ibias}
C {devices/iopin.sym} -300 -180 0 0 {name=p1 lab=ua1}
C {devices/iopin.sym} -50 -70 2 1 {name=p2 lab=ua2}
C {devices/iopin.sym} 120 -140 2 1 {name=p3 lab=ua3}
C {devices/iopin.sym} -300 -140 0 0 {name=p4 lab=ua4}
C {devices/iopin.sym} -300 -100 0 0 {name=p5 lab=ua5}
C {devices/iopin.sym} -300 -60 0 0 {name=p6 lab=VAPWR}
C {devices/iopin.sym} -300 -20 0 0 {name=p7 lab=VDPWR}
C {devices/iopin.sym} -300 20 0 0 {name=p8 lab=VGND}

C {mosbius_bias.sym} -450 -180 0 0 {name=BIAS}