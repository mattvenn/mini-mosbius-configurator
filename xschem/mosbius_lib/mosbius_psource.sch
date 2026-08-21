v {xschem version=3.4.8RC file_version=1.2}
G {}
K {}
V {}
S {}
E {}
N 60 -80 60 -140 {
lab=ibias}
N 100 -50 140 -50 {
lab=ibias}
N 140 -50 140 -140 {
lab=ibias}
N 280 -80 280 -140 {
lab=ibias}
N -20 -140 280 -140 {
lab=ibias}
N 100 -80 100 -160 {
lab=b}
N 320 -80 320 -160 {
lab=b}
N 100 -160 320 -160 {
lab=b}
N 320 -50 320 -20 {
lab=out}
C {sky130_fd_pr/pfet_g5v0d10v5.sym} 80 -80 0 0 {name=M1
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
spiceprefix=X
}
C {sky130_fd_pr/pfet_g5v0d10v5.sym} 300 -80 0 0 {name=M2
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
spiceprefix=X
}
C {devices/ipin.sym} -20 -140 0 1 {name=p1 lab=ibias}
C {devices/lab_pin.sym} 200 -160 0 1 {name=p2 lab=b}
C {devices/iopin.sym} 320 -20 0 1 {name=p3 lab=out}
