v {xschem version=3.4.8RC file_version=1.2}
G {}
K {}
V {}
S {}
E {}
N 240 -160 240 -100 {
lab=s}
N -0 -160 240 -160 {
lab=s}
N -0 -70 200 -70 {
lab=g}
N -0 40 240 40 {
lab=d}
N 240 -40 240 40 {
lab=d}
C {sky130_fd_pr/pfet3_g5v0d10v5.sym} 220 -70 0 0 {name=M1
L=0.5
W="30*w"
nf="4*w"
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
C {devices/iopin.sym} 0 -160 0 1 {name=p7 lab=s}
C {devices/ipin.sym} 0 -70 0 1 {name=p1 lab=g}
C {devices/iopin.sym} 0 40 0 1 {name=p2 lab=d}
