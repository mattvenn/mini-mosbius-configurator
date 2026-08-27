v {xschem version=3.4.8RC file_version=1.2}
G {}
K {}
V {}
S {}
F {}
E {}
N 60 -140 60 -80 {
lab=#net1}
N 280 -140 280 -80 {
lab=#net1}
N 100 -140 100 -110 {
lab=#net1}
N 100 -50 100 20 {
lab=s}
N 100 20 320 20 {
lab=s}
N 320 -50 320 20 {
lab=s}
N 320 -200 320 -110 {
lab=d}
N 0 -140 280 -140 {lab=#net1}
C {sky130_fd_pr/nfet3_g5v0d10v5.sym} 80 -80 0 0 {name=M1
L=1
W=20
nf=4
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
C {sky130_fd_pr/nfet3_g5v0d10v5.sym} 300 -80 0 0 {name=M2
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
C {devices/lab_pin.sym} 0 -140 2 1 {name=p1 lab=g}
C {devices/lab_pin.sym} 320 20 0 1 {name=p2 lab=s}
C {devices/iopin.sym} 320 -200 2 1 {name=p3 lab=d}
