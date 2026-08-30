v {xschem version=3.4.8RC file_version=1.2}
G {}
K {}
V {}
S {}
F {}
E {}
N 60 30 60 100 {
lab=s}
N 60 -120 60 -30 {
lab=d}
N -30 0 20 0 {lab=g}
C {sky130_fd_pr/nfet3_g5v0d10v5.sym} 40 0 0 0 {name=M2
L=1
W="20*(tail/2)"
nf="4*(tail/2)"
mult=1
ad="'int((nf+1)/2) * W/nf * 0.29'"
pd="'2*int((nf+1)/2) * (W/nf + 0.29)'"
as="'int((nf+2)/2) * W/nf * 0.29'"
ps="'2*int((nf+2)/2) * (W/nf + 0.29)'"
nrd="'0.29 / W'" nrs="'0.29 / W'"
sa=0 sb=0 sd=0
model=nfet_g5v0d10v5
body=s
spiceprefix=X
}
C {devices/lab_pin.sym} -30 0 2 1 {name=p1 lab=g}
C {devices/lab_pin.sym} 60 100 2 1 {name=p2 lab=s}
C {devices/iopin.sym} 60 -120 0 1 {name=p3 lab=d}
C {mosbius_implicit_port.sym} -30 0 1 0 {name=e1}
C {mosbius_implicit_port.sym} 60 100 0 0 {name=e2}
