v {xschem version=3.4.8RC file_version=1.2}
G {}
K {}
V {}
S {}
E {}
N 100 -370 100 -110 {
lab=outp}
N 320 -370 320 -110 {
lab=outm}
N 100 -50 320 -50 {
lab=tail}
N 320 -50 320 -20 {
lab=tail}
N 320 -20 600 -20 {
lab=tail}
N 600 -20 600 -290 {
lab=tail}
N 550 -290 600 -290 {
lab=tail}
N 300 -250 510 -250 {
lab=ibias}
N 100 -430 320 -430 {
lab=bp}
N 60 -400 60 -370 {
lab=outp}
N 60 -370 280 -370 {
lab=outp}
N 280 -400 280 -370 {
lab=outp}
C {sky130_fd_pr/nfet3_g5v0d10v5.sym} 80 -80 0 0 {name=M3
L=0.5
W=40
nf=8
mult=1
ad="'int((nf+1)/2) * W/nf * 0.29'"
pd="'2*int((nf+1)/2) * (W/nf + 0.29)'"
as="'int((nf+2)/2) * W/nf * 0.29'"
ps="'2*int((nf+2)/2) * (W/nf + 0.29)'"
nrd="'0.29 / W'" nrs="'0.29 / W'"
sa=0 sb=0 sd=0
model=nfet_g5v0d10v5
body=bn
spiceprefix=X
}
C {sky130_fd_pr/nfet3_g5v0d10v5.sym} 300 -80 0 0 {name=M4
L=0.5
W=40
nf=8
mult=1
ad="'int((nf+1)/2) * W/nf * 0.29'"
pd="'2*int((nf+1)/2) * (W/nf + 0.29)'"
as="'int((nf+2)/2) * W/nf * 0.29'"
ps="'2*int((nf+2)/2) * (W/nf + 0.29)'"
nrd="'0.29 / W'" nrs="'0.29 / W'"
sa=0 sb=0 sd=0
model=nfet_g5v0d10v5
body=bn
spiceprefix=X
}
C {sky130_fd_pr/pfet3_g5v0d10v5.sym} 80 -400 0 0 {name=M1
L=1
W=60
nf=8
mult=1
ad="'int((nf+1)/2) * W/nf * 0.29'"
pd="'2*int((nf+1)/2) * (W/nf + 0.29)'"
as="'int((nf+2)/2) * W/nf * 0.29'"
ps="'2*int((nf+2)/2) * (W/nf + 0.29)'"
nrd="'0.29 / W'" nrs="'0.29 / W'"
sa=0 sb=0 sd=0
model=pfet_g5v0d10v5
body=bp
spiceprefix=X
}
C {sky130_fd_pr/pfet3_g5v0d10v5.sym} 300 -400 0 0 {name=M2
L=1
W=60
nf=8
mult=1
ad="'int((nf+1)/2) * W/nf * 0.29'"
pd="'2*int((nf+1)/2) * (W/nf + 0.29)'"
as="'int((nf+2)/2) * W/nf * 0.29'"
ps="'2*int((nf+2)/2) * (W/nf + 0.29)'"
nrd="'0.29 / W'" nrs="'0.29 / W'"
sa=0 sb=0 sd=0
model=pfet_g5v0d10v5
body=bp
spiceprefix=X
}
C {mosbius_nsink.sym} 550 -250 0 0 {name=Mtail ratio="tail" b=bn}
C {devices/ipin.sym} 60 -80 0 1 {name=p1 lab=inp}
C {devices/ipin.sym} 280 -80 0 1 {name=p2 lab=inm}
C {devices/iopin.sym} 100 -200 0 1 {name=p3 lab=outp}
C {devices/iopin.sym} 320 -200 0 1 {name=p4 lab=outm}
C {devices/ipin.sym} 300 -250 0 1 {name=p5 lab=ibias}
C {devices/lab_pin.sym} 200 -430 0 1 {name=p7 lab=bp}
