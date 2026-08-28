#!/bin/sh
# Regenerate one design's routed netlist: the `mosbius simulate` output that
# a testbench's routed block includes. Lives in build/, so it is never in a
# fresh clone, and a testbench that wants it has to be able to say how to
# make it (see xschemrc's mosbius_routed_include).
#
#     tools/regenerate_routed.sh examples/inverter/inverter.sch
#
# Run from the top of the repo -- xschem needs the repo's own xschemrc for
# the symbol path, the sky130A PDK variant and netlist_dir=build/.
#
# This exists as a script, rather than inline in a testbench's launcher
# button, because a launcher's tclcommand attribute cannot survive braces or
# double quotes -- xschem re-parses the property and the command comes back
# empty, which shows up as "no action on launcher is defined" when you
# ctrl-click the arrow. Verified 2026-08-24. Keep the button's tclcommand a
# bare `execute 1 sh tools/regenerate_routed.sh <path>` with no punctuation.
set -e

sch=$1
if [ -z "$sch" ]; then
    echo "usage: tools/regenerate_routed.sh <design.sch>" >&2
    exit 2
fi
if [ ! -f "$sch" ]; then
    echo "no schematic at $sch -- give me the design's .sch, e.g." >&2
    echo "  tools/regenerate_routed.sh examples/inverter/inverter.sch" >&2
    exit 2
fi

name=$(basename "$sch" .sch)

echo "== netlisting $sch"
# Check what came out rather than xschem's exit code. It is a count of
# ERC messages, and this library used to produce them on every design:
# the `extra` mechanism that keeps body and bias connections off your
# sheet is invisible to xschem's connectivity check, so it called those
# nets undriven. mosbius_implicit_port markers settled that (2026-08-28)
# and the count is 0 today -- but a netlist that was written and is
# wrong, or not written at all, is what actually matters here.
xschem -n -q "$sch" || true
if [ ! -f "build/$name.spice" ]; then
    echo "xschem wrote no netlist for $sch (expected build/$name.spice)" >&2
    exit 1
fi
if grep -q 'IS MISSING' "build/$name.spice"; then
    echo "build/$name.spice has unresolved symbols -- run this from the" >&2
    echo "repo root, so xschem reads the repo's own xschemrc." >&2
    exit 1
fi

echo "== routing build/$name.spice"
python3 -m mosbius.cli route "build/$name.spice" --out "build/$name.mosbius.json"

echo "== building build/${name}_routed.spice"
python3 -m mosbius.cli simulate "build/$name.mosbius.json"

echo "== done -- re-netlist the testbench to pick it up"
