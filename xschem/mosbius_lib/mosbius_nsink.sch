v {xschem version=3.4.8RC file_version=1.2}
G {}
K {}
V {}
S {}
E {}
N 60 -80 60 -140 {
lab=ibias}
N -120 -140 280 -140 {
lab=ibias}
N 280 -140 280 -80 {
lab=ibias}
N 100 -140 100 -110 {
lab=ibias}
N 100 -200 100 -110 {
lab=ibias}
N 100 -50 100 20 {
lab=b}
N 100 -80 180 -80 {
lab=b}
N 180 -80 180 20 {
lab=b}
N 100 20 320 20 {
lab=b}
N 320 -80 320 20 {
lab=b}
N 320 -200 320 -110 {
lab=out}
C {sky130_fd_pr/nfet_g5v0d10v5.sym} 80 -80 0 0 {name=M1
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
spiceprefix=X
}
C {sky130_fd_pr/nfet_g5v0d10v5.sym} 300 -80 0 0 {name=M2
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
spiceprefix=X
}
C {devices/ipin.sym} -120 -140 0 1 {name=p1 lab=ibias}
C {bulk_tie.sym} 200 20 0 1 {name=p2 lab=b}
C {devices/iopin.sym} 320 -200 0 1 {name=p3 lab=out}
