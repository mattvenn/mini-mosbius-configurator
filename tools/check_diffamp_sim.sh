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

cd "$(dirname "$0")/.."
mkdir -p build

echo "== netlisting, routing and building examples/diffamp/diffamp.sch"
sh tools/regenerate_routed.sh examples/diffamp/diffamp.sch

echo "== netlisting examples/diffamp/tb_diffamp.sch"
xschem -n -q examples/diffamp/tb_diffamp.sch

echo "== running ngspice"
cp .spiceinit build/.spiceinit
( cd build && ngspice -b tb_diffamp.spice > ngspice_tb_diffamp.log 2>&1 ) \
    || { echo "ngspice exited non-zero -- tail of build/ngspice_tb_diffamp.log:"; tail -40 build/ngspice_tb_diffamp.log; exit 1; }

python3 tools/check_diffamp_sim.py build/ngspice_tb_diffamp.log
