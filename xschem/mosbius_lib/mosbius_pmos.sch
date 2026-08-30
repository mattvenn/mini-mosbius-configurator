v {xschem version=3.4.8RC file_version=1.2}
G {}
K {}
V {}
S {}
F {}
E {}
N 30 -110 30 -50 {
lab=s}
N -50 -110 30 -110 {
lab=s}
N -50 -20 -10 -20 {
lab=g}
N -50 90 30 90 {
lab=d}
N 30 10 30 90 {
lab=d}
C {sky130_fd_pr/pfet3_g5v0d10v5.sym} 10 -20 0 0 {name=M1
L=0.5
W="wdev"
nf="nfdev"
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
C {devices/iopin.sym} -50 -110 0 1 {name=p7 lab=s}
C {devices/ipin.sym} -50 -20 2 1 {name=p1 lab=g}
C {devices/iopin.sym} -50 90 0 1 {name=p2 lab=d}
C {devices/code.sym} -220 -60 0 0 {name=SIZE only_toplevel=false value=".param wdev='30*w' nfdev='4*w'"}
