v {xschem version=3.4.8RC file_version=1.2}
G {}
K {}
V {}
S {}
F {}
E {}
N -10 90 70 90 {
lab=b}
N 70 20 70 90 {
lab=b}
N -20 -10 30 -10 {lab=ibias}
N -20 -130 70 -130 {lab=out}
N 70 -130 70 -40 {lab=out}
C {sky130_fd_pr/nfet3_g5v0d10v5.sym} 50 -10 0 0 {name=M2
L=1
W="10*ratio"
nf="2*ratio"
mult=1
ad="'int((nf+1)/2) * W/nf * 0.29'"
pd="'2*int((nf+1)/2) * (W/nf + 0.29)'"
as="'int((nf+2)/2) * W/nf * 0.29'"
ps="'2*int((nf+2)/2) * (W/nf + 0.29)'"
nrd="'0.29 / W'" nrs="'0.29 / W'"
sa=0 sb=0 sd=0
model=nfet_g5v0d10v5
body=b
spiceprefix=X
}
C {devices/lab_pin.sym} -20 -10 2 1 {name=p1 lab=ibias}
C {devices/lab_pin.sym} -10 90 2 1 {name=p2 lab=b}
C {devices/iopin.sym} -20 -130 0 1 {name=p3 lab=out}
C {mosbius_implicit_port.sym} 10 -10 1 0 {name=e1}
C {mosbius_implicit_port.sym} 10 90 1 0 {name=e2}
