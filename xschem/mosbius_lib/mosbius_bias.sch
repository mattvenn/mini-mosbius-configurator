v {xschem version=3.4.8RC file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {The chip's bias generator: pin ua0's current in, the two reference} -240 -320 0 0 0.3 0.3 {}
T {voltages every mirror leg and tail bank copies out.} -240 -290 0 0 0.3 0.3 {}
T {Mbias_ref and Mbias_copy are mirror_n.sch's M1 and M2 (iout_fixed);} -240 -260 0 0 0.3 0.3 {}
T {Mbias_p is mirror_p.sch's M4. Sizes are those devices' own.} -240 -230 0 0 0.3 0.3 {}
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
C {sky130_fd_pr/pfet3_g5v0d10v5.sym} 200 -200 0 0 {name=Mbias_p
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
C {devices/iopin.sym} -20 0 0 0 {name=p1 lab=ibias}
C {devices/lab_pin.sym} 20 -30 1 0 {name=p2 lab=ibias}
C {devices/lab_pin.sym} 20 30 3 0 {name=p3 lab=bn}
C {devices/lab_pin.sym} 180 0 2 0 {name=p4 lab=ibias}
C {devices/lab_pin.sym} 220 -30 1 0 {name=p5 lab=ibias_p}
C {devices/lab_pin.sym} 220 30 3 0 {name=p6 lab=bn}
C {devices/lab_pin.sym} 180 -200 2 0 {name=p7 lab=ibias_p}
C {devices/lab_pin.sym} 220 -170 3 0 {name=p8 lab=ibias_p}
N 220 -230 280 -230 {lab=bp}
C {devices/lab_pin.sym} 220 -230 1 0 {name=p9 lab=bp}
C {mosbius_implicit_port.sym} 280 -230 0 0 {name=e1 lab=bp}
