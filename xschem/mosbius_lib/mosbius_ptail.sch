v {xschem version=3.4.8RC file_version=1.2}
G {}
K {}
V {}
S {}
E {}
N 280 -80 280 -140 {
lab=g}
N -20 -140 280 -140 {
lab=g}
N 320 -110 320 -160 {
lab=s}
N 200 -160 320 -160 {
lab=s}
N 320 -50 320 -20 {
lab=d}
C {sky130_fd_pr/pfet3_g5v0d10v5.sym} 300 -80 0 0 {name=M2
L=1
W="60*(tail/2)"
nf="8*(tail/2)"
mult=1
ad="'int((nf+1)/2) * W/nf * 0.29'"
pd="'2*int((nf+1)/2) * (W/nf + 0.29)'"
as="'int((nf+2)/2) * W/nf * 0.29'"
ps="'2*int((nf+2)/2) * (W/nf + 0.29)'"
nrd="'0.29 / W'" nrs="'0.29 / W'"
sa=0 sb=0 sd=0
model=pfet_g5v0d10v5
body=s
spiceprefix=X
}
C {devices/lab_pin.sym} -20 -140 0 1 {name=p1 lab=g}
C {devices/lab_pin.sym} 200 -160 0 1 {name=p2 lab=s}
C {devices/iopin.sym} 320 -20 0 1 {name=p3 lab=d}
