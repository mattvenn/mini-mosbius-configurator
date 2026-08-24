v {xschem version=3.4.8RC file_version=1.2}
G {}
K {type=subcircuit
format="@name @pinlist @symname"
template="name=x1"
}
V {}
S {}
F {}
E {}
T {Same topology as the bitstream measured at ~30MHz on real silicon} -450 -310 0 0 0.25 0.25 {}
T {(380088007001000010000404250109000400000040000014, decode it with} -450 -280 0 0 0.25 0.25 {}
T {`python3 -m mosbius.cli decode 380088...0014`): three inverting stages,} -450 -250 0 0 0.25 0.25 {}
T {loop ua2 -> ua1 -> ua4 -> ua2. M1/M2 (nmos_a/pmos_a) is a plain} -450 -220 0 0 0.25 0.25 {}
T {inverter; M3/M4 and M5/M6 are the two diff-pair stages, each pair} -450 -190 0 0 0.25 0.25 {}
T {sharing a source net (no mosbius_ntail/ptail drawn) standalone-tied} -450 -160 0 0 0.25 0.25 {}
T {per CLAUDE.md Trap #3. Routing this reproduces the measured design's} -450 -130 0 0 0.25 0.25 {}
T {device roles exactly (nmos_a/pmos_a/ndiffpair+-/pdiffpair+-, same} -450 -100 0 0 0.25 0.25 {}
T {wiring, same w=4/tail=2) but NOT its literal bitstream: the router} -450 -70 0 0 0.25 0.25 {}
T {ties this shared source through the bus/crosspoint switches (an} -450 -40 0 0 0.25 0.25 {}
T {internal net), while the measured design's bitstream instead has} -450 -10 0 0 0.25 0.25 {}
T {ctrl_dpn_source/ctrl_dpp_source set -- the dedicated rail-tie switch} -450 20 0 0 0.25 0.25 {}
T {CLAUDE.md Trap #3 describes for a source wired straight to VGND/VAPWR.} -450 50 0 0 0.25 0.25 {}
T {Drawing THAT instead (see README.md) makes the router use nmos_b for} -450 80 0 0 0.25 0.25 {}
T {one half rather than pairing both as diffpair -- a real allocator} -450 110 0 0 0.25 0.25 {}
T {limitation, not a drawing mistake. For a bit-exact 30MHz comparison,} -450 140 0 0 0.25 0.25 {}
T {use the measured bitstream directly (README.md's "Exact comparison").} -450 170 0 0 0.25 0.25 {}
C {mosbius_nmos.sym} 0 200 0 0 {name=M1 w=4}
C {mosbius_pmos.sym} 0 0 0 0 {name=M2 w=4}
C {mosbius_nmos.sym} 300 200 0 0 {name=M3 w=4}
C {mosbius_nmos.sym} 500 200 0 0 {name=M4 w=4}
C {mosbius_pmos.sym} 300 0 0 0 {name=M5 w=4}
C {mosbius_pmos.sym} 500 0 0 0 {name=M6 w=4}
C {devices/iopin.sym} -450 100 0 0 {name=p1 lab=ua1}
C {devices/iopin.sym} -450 120 0 0 {name=p2 lab=ua2}
C {devices/iopin.sym} -450 130 0 0 {name=p3 lab=ua4}
C {devices/iopin.sym} -450 230 0 0 {name=p4 lab=VGND}
C {devices/iopin.sym} -450 -30 0 0 {name=p5 lab=VAPWR}
C {devices/iopin.sym} -450 350 0 0 {name=p6 lab=ibias}
C {devices/iopin.sym} -450 390 0 0 {name=p7 lab=ua3}
C {devices/iopin.sym} -450 430 0 0 {name=p8 lab=ua5}
C {devices/iopin.sym} -450 470 0 0 {name=p9 lab=VDPWR}
N -450 100 20 100 {lab=ua1}
N 20 100 280 100 {lab=ua1}
N 20 30 20 170 {lab=ua1}
N 280 0 280 200 {lab=ua1}
N -450 120 -20 120 {lab=ua2}
N -20 120 520 120 {lab=ua2}
N -20 0 -20 200 {lab=ua2}
N 520 30 520 170 {lab=ua2}
N -450 130 320 130 {lab=ua4}
N 320 130 480 130 {lab=ua4}
N 320 30 320 170 {lab=ua4}
N 480 0 480 200 {lab=ua4}
N -450 230 20 230 {lab=VGND}
N -450 -30 20 -30 {lab=VAPWR}
N 320 230 340 230 {lab=dn_tail}
N 520 230 540 230 {lab=dn_tail}
N 340 230 540 230 {lab=dn_tail}
N 320 -30 340 -30 {lab=dp_tail}
N 520 -30 540 -30 {lab=dp_tail}
N 340 -30 540 -30 {lab=dp_tail}
