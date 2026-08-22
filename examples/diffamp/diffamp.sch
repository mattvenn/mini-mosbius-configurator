v {xschem version=3.4.8RC file_version=1.2}
G {}
K {type=subcircuit
format="@name @pinlist @symname"
template="name=x1"
}
V {}
S {}
E {}
N 20 30 20 110 {lab=tail}
N 20 110 100 110 {lab=tail}
N 220 30 220 110 {lab=tail}
N 220 110 100 110 {lab=tail}
N 20 -170 20 -30 {lab=netd1}
N -20 -200 -20 -170 {lab=netd1}
N -20 -170 20 -170 {lab=netd1}
N 20 -170 180 -170 {lab=netd1}
N 180 -170 180 -200 {lab=netd1}
N 220 -30 220 -170 {lab=out}
N 20 -230 20 -260 {lab=VAPWR}
N 20 -260 220 -260 {lab=VAPWR}
N 220 -260 220 -230 {lab=VAPWR}
N -150 0 -20 0 {lab=ua1}
N 180 0 350 0 {lab=ua2}
N 220 -170 350 -100 {lab=out}
C {mosbius_nmos.sym} 0 0 0 0 {name=M1 w=4}
C {mosbius_nmos.sym} 200 0 0 0 {name=M2 w=4}
C {mosbius_ntail.sym} 100 150 0 0 {name=T1 tail=4}
C {mosbius_pmos.sym} 0 -200 0 0 {name=M3 w=1}
C {mosbius_pmos.sym} 200 -200 0 0 {name=M4 w=1}
C {devices/iopin.sym} -150 0 0 1 {name=p1 lab=ua1}
C {devices/iopin.sym} 350 0 0 1 {name=p2 lab=ua2}
C {devices/iopin.sym} 350 -100 0 1 {name=p3 lab=out}
C {devices/iopin.sym} 20 -260 0 1 {name=p4 lab=VAPWR}
