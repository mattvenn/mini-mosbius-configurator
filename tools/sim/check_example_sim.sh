#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Regression check for one example: netlists the design, routes it, builds
# the routed subcircuit, netlists the example's own testbench, runs it
# through ngspice, and hands the log to tools/sim/check_<name>_sim.py, which
# compares what came out against the reference measurements published in
# that example's README.
#
# This is what .github/workflows/spice-regression.yml runs on every push,
# once per example as a matrix leg. There used to be seven near-identical
# copies of this file; they differed only in two names, and one of them
# (the inverter's) had drifted into routing by hand rather than calling
# tools/regenerate_routed.sh like the other six.
#
# Needs xschem/ngspice, so run it inside the IIC-OSIC-TOOLS container from
# the repo root:
#
#   docker run --rm -v "$PWD:/work" -w /work hpretl/iic-osic-tools:latest \
#       --skip bash -lc 'sh tools/sim/check_example_sim.sh inverter'
#
# Budget a couple of minutes whichever example you pick: sky130A's combined
# model library takes 1-2 minutes to parse regardless of circuit size, and
# that dominates every run (see .spiceinit's own note and CLAUDE.md's
# "Running ngspice" section). What each deck adds on top of that is noted
# in the table below.
set -e

usage() {
    echo "usage: sh tools/sim/check_example_sim.sh <example>" >&2
    echo "" >&2
    echo "  inverter       a digital edge: rise time as drawn and as routed" >&2
    echo "  ring           two transients; the branches oscillate ~40x apart," >&2
    echo "                 so no single analysis suits both" >&2
    echo "  diffamp        a 6.5us transient; the output settles slowly" >&2
    echo "  pdiffamp       the same, in the opposite polarity" >&2
    echo "  srlatch        stored levels and reset delays" >&2
    echo "  otabuf         a 15us transient over both branches, ~36s of it" >&2
    echo "  currentsource  a 133-point DC sweep over both branches" >&2
    exit 2
}

# example -> "<directory> <design> <testbench> <checker>". The directory and
# the design name are not always the same word: the ring oscillator lives in
# examples/ringosc/ but its schematic, subcircuit and netlist are all called
# ring, because a subcircuit's name follows its schematic= file.
case "${1:-}" in
    inverter)      dir=inverter      design=inverter      check=inverter      ;;
    ring)          dir=ringosc       design=ring          check=ring          ;;
    diffamp)       dir=diffamp       design=diffamp       check=diffamp       ;;
    pdiffamp)      dir=pdiffamp      design=pdiffamp      check=pdiffamp      ;;
    srlatch)       dir=srlatch       design=srlatch       check=srlatch       ;;
    otabuf)        dir=otabuf        design=otabuf        check=otabuf        ;;
    currentsource) dir=currentsource design=currentsource check=currentsource ;;
    "")            echo "no example named." >&2; echo "" >&2; usage ;;
    *)             echo "unknown example '$1'." >&2; echo "" >&2; usage ;;
esac

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

# This script lives in tools/sim/, so the repo root is two levels up. Every
# path below (build/, examples/, .spiceinit) is relative to it.
cd "$(dirname "$0")/../.."
mkdir -p build

echo "== netlisting, routing and building examples/$dir/$design.sch"
sh tools/regenerate_routed.sh "examples/$dir/$design.sch"

echo "== netlisting examples/$dir/tb_$design.sch"
netlist_schematic "examples/$dir/tb_$design.sch"

echo "== running ngspice"
cp .spiceinit build/.spiceinit
( cd build && ngspice -b "tb_$design.spice" > "ngspice_tb_$design.log" 2>&1 ) \
    || { echo "ngspice exited non-zero -- tail of build/ngspice_tb_$design.log:"; \
         tail -40 "build/ngspice_tb_$design.log"; exit 1; }

python3 "tools/sim/check_${check}_sim.py" "build/ngspice_tb_$design.log"
