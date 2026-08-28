#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Monthly regression check for examples/inverter: netlists it, routes it,
# builds the routed subcircuit, runs the real tb_inverter.sch testbench
# through ngspice, and checks trise_drawn/trise_routed land near the
# reference measurements in examples/inverter/README.md via
# check_inverter_sim.py. This is what
# .github/workflows/spice-regression.yml runs once a month, alongside the
# ring, diff amp, SR latch, OTA follower and current source checks.
#
# Needs xschem/ngspice, so run it inside the IIC-OSIC-TOOLS container from
# the repo root:
#
#   docker run --rm -v "$PWD:/work" -w /work hpretl/iic-osic-tools:latest \
#       --skip bash -lc 'sh tools/check_inverter_sim.sh'
#
# Budget ~1-2 minutes for the ngspice step: sky130A's combined model
# library takes that long to parse regardless of circuit size (see
# .spiceinit's own note and CLAUDE.md's "Running ngspice" section).
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

echo "== netlisting examples/inverter/inverter.sch"
netlist_schematic examples/inverter/inverter.sch

echo "== routing build/inverter.spice"
python3 -m mosbius.cli route build/inverter.spice --out build/inverter.mosbius.json

echo "== building build/inverter_routed.spice"
python3 -m mosbius.cli simulate build/inverter.mosbius.json

echo "== netlisting examples/inverter/tb_inverter.sch"
netlist_schematic examples/inverter/tb_inverter.sch

echo "== running ngspice"
cp .spiceinit build/.spiceinit
( cd build && ngspice -b tb_inverter.spice > ngspice_tb_inverter.log 2>&1 ) \
    || { echo "ngspice exited non-zero -- tail of build/ngspice_tb_inverter.log:"; tail -40 build/ngspice_tb_inverter.log; exit 1; }

python3 tools/check_inverter_sim.py build/ngspice_tb_inverter.log
