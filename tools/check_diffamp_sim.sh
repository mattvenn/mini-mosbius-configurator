#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Monthly regression check for examples/diffamp: netlists it, routes it,
# builds the routed subcircuit, runs the real tb_diffamp.sch testbench
# through ngspice, and checks the gains and the operating point land near
# the reference measurements in examples/diffamp/README.md via
# check_diffamp_sim.py. This is what
# .github/workflows/spice-regression.yml runs once a month, alongside the
# inverter, ring and SR latch checks.
#
# Needs xschem/ngspice, so run it inside the IIC-OSIC-TOOLS container from
# the repo root:
#
#   docker run --rm -v "$PWD:/work" -w /work hpretl/iic-osic-tools:latest \
#       --skip bash -lc 'sh tools/check_diffamp_sim.sh'
#
# Budget a couple of minutes: sky130A's model library takes 1-2 minutes to
# parse whatever the circuit is, and this deck runs a 6.5us transient (the
# output is a ~20MOhm node, so it needs microseconds to settle).
set -e

# Netlist one schematic and check what came out, rather than trusting
# xschem's exit code.
#
# xschem's exit code is a count of ERC messages, not a verdict on the
# netlist. This library used to produce them on every design that used a
# mirror or a tail bank: the `extra` mechanism that keeps body and bias
# connections off the sheet is invisible to xschem's connectivity check,
# so it called those nets undriven. Under `set -e` that stopped these
# scripts before they reached ngspice -- the diff amp job could never
# have passed. mosbius_implicit_port markers settled the messages
# themselves (2026-08-28); checking the output rather than the exit code
# stays, because it is what actually matters.
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

echo "== netlisting, routing and building examples/diffamp/diffamp.sch"
sh tools/regenerate_routed.sh examples/diffamp/diffamp.sch

echo "== netlisting examples/diffamp/tb_diffamp.sch"
netlist_schematic examples/diffamp/tb_diffamp.sch

echo "== running ngspice"
cp .spiceinit build/.spiceinit
( cd build && ngspice -b tb_diffamp.spice > ngspice_tb_diffamp.log 2>&1 ) \
    || { echo "ngspice exited non-zero -- tail of build/ngspice_tb_diffamp.log:"; tail -40 build/ngspice_tb_diffamp.log; exit 1; }

python3 tools/check_diffamp_sim.py build/ngspice_tb_diffamp.log
