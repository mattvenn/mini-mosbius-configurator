#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Monthly regression check for examples/ringosc: netlists it, routes it,
# builds the routed subcircuit, runs the real tb_ring.sch testbench through
# ngspice, and checks freq_drawn/freq_routed land near the reference
# measurements in examples/ringosc/README.md via check_ring_sim.py. This is
# what .github/workflows/spice-regression.yml runs once a month, alongside
# tools/check_inverter_sim.sh.
#
# Needs xschem/ngspice, so run it inside the IIC-OSIC-TOOLS container from
# the repo root:
#
#   docker run --rm -v "$PWD:/work" -w /work hpretl/iic-osic-tools:latest \
#       --skip bash -lc 'sh tools/check_ring_sim.sh'
#
# Budget a couple of minutes: sky130A's model library takes 1-2 minutes to
# parse whatever the circuit is, and this deck runs two transients (the
# branches oscillate ~40x apart, so neither analysis suits both).
set -e

# Netlist one schematic and check what came out, rather than trusting
# xschem's exit code.
#
# xschem exits non-zero (10, observed) on any sheet that instantiates
# mosbius_nsink/mosbius_psource/mosbius_ntail/mosbius_ptail/mosbius_ota,
# while writing a perfectly good netlist. Those symbols supply their body
# and bias connections through xschem's `extra` attribute, which its
# connectivity check cannot see (CLAUDE.md, "Useful facts"), so it counts
# them as issues. Under `set -e` that stopped these scripts before they
# reached ngspice -- the diff amp job could never have passed.
#
# What is worth checking is the netlist itself: that it was written, and
# that the symbol library was actually on the path. Launch xschem from
# anywhere but the repo root and every device comes out as
# `IS MISSING !!!!` -- a deck with no transistors that ngspice runs
# happily (CLAUDE.md, and examples/README.md's gotchas).
netlist_schematic() {
    sch=$1
    out=build/$(basename "$sch" .sch).spice
    rm -f "$out"
    xschem -n -q "$sch" || true
    if [ ! -f "$out" ]; then
        echo "xschem wrote no netlist for $sch (expected $out)" >&2
        exit 1
    fi
    if grep -q 'IS MISSING' "$out"; then
        echo "$out has unresolved symbols -- run this from the repo root," >&2
        echo "so xschem reads the repo's own xschemrc." >&2
        exit 1
    fi
}

cd "$(dirname "$0")/.."
mkdir -p build

echo "== netlisting, routing and building examples/ringosc/ring.sch"
sh tools/regenerate_routed.sh examples/ringosc/ring.sch

echo "== netlisting examples/ringosc/tb_ring.sch"
netlist_schematic examples/ringosc/tb_ring.sch

echo "== running ngspice"
cp .spiceinit build/.spiceinit
( cd build && ngspice -b tb_ring.spice > ngspice_tb_ring.log 2>&1 ) \
    || { echo "ngspice exited non-zero -- tail of build/ngspice_tb_ring.log:"; tail -40 build/ngspice_tb_ring.log; exit 1; }

python3 tools/check_ring_sim.py build/ngspice_tb_ring.log
