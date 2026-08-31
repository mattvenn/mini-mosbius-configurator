#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Regression check for examples/currentsource: netlists it, routes it,
# builds the routed subcircuit, runs the real tb_currentsource.sch testbench
# through ngspice, and checks the two mirror legs' currents land
# near the reference measurements in examples/currentsource/README.md via
# check_currentsource_sim.py. This is what
# .github/workflows/spice-regression.yml runs on every push, alongside the
# inverter, ring, diff amp, SR latch and OTA follower checks.
#
# Needs xschem/ngspice, so run it inside the IIC-OSIC-TOOLS container from
# the repo root:
#
#   docker run --rm -v "$PWD:/work" -w /work hpretl/iic-osic-tools:latest \
#       --skip bash -lc 'sh tools/check_currentsource_sim.sh'
#
# Budget a couple of minutes: sky130A's model library takes 1-2 minutes to
# parse whatever the circuit is; the sweep itself is quick (133 DC points
# over both branches).
set -e

# Netlist one schematic and check what came out, rather than trusting
# xschem's exit code.
#
# xschem's exit code is a count of ERC messages, not a verdict on the
# netlist. This library used to produce them on every design that used a
# mirror or a tail bank: the `extra` mechanism that keeps body and bias
# connections off the sheet is invisible to xschem's connectivity check,
# so it called those nets undriven. Under `set -e` that stopped these
# scripts before they reached ngspice. mosbius_implicit_port markers
# settled the messages themselves (2026-08-28); checking the output rather
# than the exit code stays, because it is what actually matters.
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

echo "== netlisting, routing and building examples/currentsource/currentsource.sch"
sh tools/regenerate_routed.sh examples/currentsource/currentsource.sch

echo "== netlisting examples/currentsource/tb_currentsource.sch"
netlist_schematic examples/currentsource/tb_currentsource.sch

echo "== running ngspice"
cp .spiceinit build/.spiceinit
( cd build && ngspice -b tb_currentsource.spice > ngspice_tb_currentsource.log 2>&1 ) \
    || { echo "ngspice exited non-zero -- tail of build/ngspice_tb_currentsource.log:"; tail -40 build/ngspice_tb_currentsource.log; exit 1; }

python3 tools/check_currentsource_sim.py build/ngspice_tb_currentsource.log
