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
N -600 0 -600 -260 {lab=ibias}
N -600 -260 -300 -260 {lab=ibias}
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
C {mosbius_bias.sym} -600 40 0 0 {name=BIAS}
