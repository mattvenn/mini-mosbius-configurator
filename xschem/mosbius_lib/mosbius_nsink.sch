v {xschem version=3.4.8RC file_version=1.2}
G {}
K {}
V {}
S {}
E {}
N -120 -140 280 -140 {
lab=ibias}
N 280 -140 280 -80 {
lab=ibias}
N 200 20 320 20 {
lab=b}
N 320 -50 320 20 {
lab=b}
N 320 -200 320 -110 {
lab=out}
C {sky130_fd_pr/nfet3_g5v0d10v5.sym} 300 -80 0 0 {name=M2
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
body=b
spiceprefix=X
}
C {devices/lab_pin.sym} -120 -140 0 1 {name=p1 lab=ibias}
C {devices/lab_pin.sym} 200 20 0 1 {name=p2 lab=b}
C {devices/iopin.sym} 320 -200 0 1 {name=p3 lab=out}
C {mosbius_implicit_port.sym} 0 -140 0 0 {name=e1 lab=ibias}
C {mosbius_implicit_port.sym} 260 20 0 0 {name=e2 lab=b}
