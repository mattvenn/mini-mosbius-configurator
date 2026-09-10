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
N 150 -200 150 -180 {
lab=well}
N 150 -120 150 -100 {
lab=s}
N 250 -200 250 -180 {
lab=well}
N 250 -120 250 -80 {
lab=b}
N 250 -80 280 -80 {lab=b}
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
body=well
spiceprefix=X
}
C {devices/iopin.sym} -50 -110 0 1 {name=p7 lab=s}
C {devices/ipin.sym} -50 -20 2 1 {name=p1 lab=g}
C {devices/iopin.sym} -50 90 0 1 {name=p2 lab=d}
C {devices/code.sym} -220 -60 0 0 {name=SIZE only_toplevel=false value=".param wdev='30*w' nfdev='wdev/pmos_width_per_finger'"}
C {devices/res.sym} 150 -150 0 0 {name=Rwell_source value="'rwell_source'" footprint=1206 device=resistor m=1}
C {devices/res.sym} 250 -150 0 0 {name=Rwell_rail value="'rwell_rail'" footprint=1206 device=resistor m=1}
C {devices/lab_pin.sym} 150 -200 2 1 {name=pwell1 lab=well}
C {devices/lab_pin.sym} 150 -100 2 1 {name=pwellsrc lab=s}
C {devices/lab_pin.sym} 250 -200 2 1 {name=pwell2 lab=well}
C {devices/lab_pin.sym} 250 -80 2 1 {name=pwellrail lab=b}
C {mosbius_implicit_port.sym} 280 -80 1 0 {name=e1}
T {well: split to source/rail by rwell_source/rwell_rail (Chip.bulk_follows_source)} 130 -260 0 0 0.2 0.2 {}
