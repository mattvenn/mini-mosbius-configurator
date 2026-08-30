v {xschem version=3.4.8RC file_version=1.2}
G {}
K {}
V {}
S {}
F {}
E {}
T {The chip's bias generator: pin ua0's current in, the two reference
voltages every mirror leg and tail bank copies out.
Mbias_ref and Mbias_copy are mirror_n.sch's M1 and M2 (iout_fixed);
Mbias_p is mirror_p.sch's M4. Sizes are those devices' own.} -40 -210 0 0 0.3 0.3 {}
N 420 -30 480 -30 {lab=bp}
C {sky130_fd_pr/nfet3_g5v0d10v5.sym} 0 0 0 0 {name=Mbias_ref
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
body=bn
spiceprefix=X
}
C {sky130_fd_pr/nfet3_g5v0d10v5.sym} 200 0 0 0 {name=Mbias_copy
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
body=bn
spiceprefix=X
}
C {sky130_fd_pr/pfet3_g5v0d10v5.sym} 400 0 0 0 {name=Mbias_p
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
body=bp
spiceprefix=X
}
C {devices/iopin.sym} -20 0 2 0 {name=p1 lab=ibias}
C {devices/lab_pin.sym} 20 -30 1 0 {name=p2 lab=ibias}
C {devices/lab_pin.sym} 20 30 3 0 {name=p3 lab=bn}
C {devices/lab_pin.sym} 180 0 0 0 {name=p4 lab=ibias}
C {devices/lab_pin.sym} 220 -30 1 0 {name=p5 lab=ibias_p}
C {devices/lab_pin.sym} 220 30 3 0 {name=p6 lab=bn}
C {devices/lab_pin.sym} 380 0 0 0 {name=p7 lab=ibias_p}
C {devices/lab_pin.sym} 420 30 3 0 {name=p8 lab=ibias_p}
C {devices/lab_pin.sym} 420 -30 1 0 {name=p9 lab=bp}
C {mosbius_implicit_port.sym} 480 -30 0 0 {name=e1}
