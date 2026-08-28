#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Monthly regression check for examples/srlatch: netlists it, routes it,
# builds the routed subcircuit, runs the real tb_srlatch.sch testbench
# through ngspice, and checks the stored levels and the reset delays land
# near the reference measurements in examples/srlatch/README.md via
# check_srlatch_sim.py. This is what
# .github/workflows/spice-regression.yml runs once a month, alongside the
# inverter, ring, differential amplifier, OTA follower and current
# source checks.
#
# Needs xschem/ngspice, so run it inside the IIC-OSIC-TOOLS container from
# the repo root:
#
#   docker run --rm -v "$PWD:/work" -w /work hpretl/iic-osic-tools:latest \
#       --skip bash -lc 'sh tools/check_srlatch_sim.sh'
#
# Budget a couple of minutes: sky130A's model library takes 1-2 minutes to
# parse whatever the circuit is, which dominates the run.
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

echo "== netlisting, routing and building examples/srlatch/srlatch.sch"
sh tools/regenerate_routed.sh examples/srlatch/srlatch.sch

echo "== netlisting examples/srlatch/tb_srlatch.sch"
netlist_schematic examples/srlatch/tb_srlatch.sch

echo "== running ngspice"
cp .spiceinit build/.spiceinit
( cd build && ngspice -b tb_srlatch.spice > ngspice_tb_srlatch.log 2>&1 ) \
    || { echo "ngspice exited non-zero -- tail of build/ngspice_tb_srlatch.log:"; tail -40 build/ngspice_tb_srlatch.log; exit 1; }

python3 tools/check_srlatch_sim.py build/ngspice_tb_srlatch.log
