v {xschem version=3.4.8RC file_version=1.2}
G {}
K {}
V {}
S {}
F {}
E {}
N 100 -50 100 20 {
lab=s}
N 100 -200 100 -110 {
lab=d}
N 40 -200 100 -200 {lab=d}
N 40 -80 60 -80 {lab=g}
N 40 20 100 20 {lab=s}
C {sky130_fd_pr/nfet3_g5v0d10v5.sym} 80 -80 0 0 {name=M1
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
model=nfet_g5v0d10v5
body=b
spiceprefix=X
}
C {devices/iopin.sym} 40 20 0 1 {name=p7 lab=s}
C {devices/ipin.sym} 40 -80 2 1 {name=p1 lab=g}
C {devices/iopin.sym} 40 -200 0 1 {name=p2 lab=d}
C {devices/code.sym} -160 -140 0 0 {name=SIZE only_toplevel=false value=".param wdev='10*w' nfdev='2*w'"}
