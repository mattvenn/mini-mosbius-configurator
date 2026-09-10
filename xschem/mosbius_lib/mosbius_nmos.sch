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
N 220 -200 220 -180 {
lab=well}
N 220 -120 220 -100 {
lab=s}
N 320 -200 320 -180 {
lab=well}
N 320 -120 320 -80 {
lab=b}
N 320 -80 350 -80 {lab=b}
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
body=well
spiceprefix=X
}
C {devices/iopin.sym} 40 20 0 1 {name=p7 lab=s}
C {devices/ipin.sym} 40 -80 2 1 {name=p1 lab=g}
C {devices/iopin.sym} 40 -200 0 1 {name=p2 lab=d}
C {devices/code.sym} -160 -140 0 0 {name=SIZE only_toplevel=false value=".param wdev='10*w' nfdev='2*w'"}
C {devices/res.sym} 220 -150 0 0 {name=Rwell_source value="'rwell_source'" footprint=1206 device=resistor m=1}
C {devices/res.sym} 320 -150 0 0 {name=Rwell_rail value="'rwell_rail'" footprint=1206 device=resistor m=1}
C {devices/lab_pin.sym} 220 -200 2 1 {name=pwell1 lab=well}
C {devices/lab_pin.sym} 220 -100 2 1 {name=pwellsrc lab=s}
C {devices/lab_pin.sym} 320 -200 2 1 {name=pwell2 lab=well}
C {devices/lab_pin.sym} 320 -80 2 1 {name=pwellrail lab=b}
C {mosbius_implicit_port.sym} 350 -80 1 0 {name=e1}
T {well: split to source/rail by rwell_source/rwell_rail (Chip.bulk_follows_source)} 200 -260 0 0 0.2 0.2 {}
