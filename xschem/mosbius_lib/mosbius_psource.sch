v {xschem version=3.4.8RC file_version=1.2}
G {}
K {}
V {}
S {}
F {}
E {}
N 320 -160 320 -110 {
lab=b}
N 200 -160 320 -160 {
lab=b}
N 320 -50 320 -20 {
lab=out}
N 200 -80 280 -80 {lab=ibias}
C {sky130_fd_pr/pfet3_g5v0d10v5.sym} 300 -80 0 0 {name=M2
L=1
W="30*ratio"
nf="4*ratio"
mult=1
ad="'int((nf+1)/2) * W/nf * 0.29'"
pd="'2*int((nf+1)/2) * (W/nf + 0.29)'"
as="'int((nf+2)/2) * W/nf * 0.29'"
ps="'2*int((nf+2)/2) * (W/nf + 0.29)'"
nrd="'0.29 / W'" nrs="'0.29 / W'"
sa=0 sb=0 sd=0
model=pfet_g5v0d10v5
body=b
spiceprefix=X
}
C {devices/lab_pin.sym} 200 -80 2 1 {name=p1 lab=ibias}
C {devices/lab_pin.sym} 200 -160 2 1 {name=p2 lab=b}
C {devices/iopin.sym} 320 -20 0 1 {name=p3 lab=out}
C {mosbius_implicit_port.sym} 240 -80 1 0 {name=e1}
C {mosbius_implicit_port.sym} 260 -160 1 0 {name=e2}
