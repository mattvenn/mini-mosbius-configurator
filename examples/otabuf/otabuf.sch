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
T {OTA unity-gain follower} -450 -130 0 0 0.5 0.5 {}
T {A1's outm is tied back to its own inm, so the OTA drives ua2 to} -450 -90 0 0 0.3 0.3 {}
T {whatever voltage ua1 is held at. outm is the high-impedance output:} -450 -60 0 0 0.3 0.3 {}
T {inside mosbius_ota.sch the PMOS mirror gates are tied to outp, which} -450 -30 0 0 0.3 0.3 {}
T {makes outp the diode-connected node and outm the one with the gain.} -450 0 0 0 0.3 0.3 {}
T {Feeding outp back instead would be positive feedback -- a latch.} -450 30 0 0 0.3 0.3 {}
T {outp is brought out on ua3 so the mirror node is measurable too.} -450 60 0 0 0.3 0.3 {}
N -550 200 -400 200 {lab=ibias}
N -180 205 -50 205 {lab=ua1}
N 90 245 220 245 {lab=ua2}
N 220 245 320 245 {lab=ua2}
N 220 245 220 350 {lab=ua2}
N -180 350 220 350 {lab=ua2}
N -180 255 -180 350 {lab=ua2}
N -180 255 -50 255 {lab=ua2}
N 90 215 320 215 {lab=ua3}
C {mosbius_ota.sym} 20 230 0 0 {name=A1 tail=4}
C {devices/iopin.sym} -400 200 0 0 {name=p0 lab=ibias}
C {devices/iopin.sym} -180 205 2 0 {name=p1 lab=ua1}
C {devices/iopin.sym} 320 245 2 1 {name=p2 lab=ua2}
C {devices/iopin.sym} 320 215 2 1 {name=p3 lab=ua3}
C {devices/iopin.sym} -400 240 0 0 {name=p4 lab=ua4}
C {devices/iopin.sym} -400 280 0 0 {name=p5 lab=ua5}
C {devices/iopin.sym} -400 320 0 0 {name=p6 lab=VAPWR}
C {devices/iopin.sym} -400 360 0 0 {name=p7 lab=VDPWR}
C {devices/iopin.sym} -400 400 0 0 {name=p8 lab=VGND}
C {mosbius_bias.sym} -550 240 0 0 {name=BIAS}
