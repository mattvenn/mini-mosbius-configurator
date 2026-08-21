v {xschem version=3.4.8RC file_version=1.2}
G {}
K {}
V {}
S {}
E {}
N 100 -50 100 20 {
lab=s}
N -120 20 100 20 {
lab=s}
N -120 -80 60 -80 {
lab=g}
N 100 -200 100 -110 {
lab=d}
N -120 -200 100 -200 {
lab=d}
N 100 -80 180 -80 {
lab=b}
C {sky130_fd_pr/nfet_g5v0d10v5.sym} 80 -80 0 0 {name=M1
L=0.5
W="10*w"
nf="2*w"
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
C {devices/iopin.sym} -120 20 0 1 {name=p7 lab=s}
C {devices/ipin.sym} -120 -80 0 1 {name=p1 lab=g}
C {devices/iopin.sym} -120 -200 0 1 {name=p2 lab=d}
C {bulk_tie.sym} 180 -80 0 1 {name=p4 lab=b}
