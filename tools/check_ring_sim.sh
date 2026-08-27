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

cd "$(dirname "$0")/.."
mkdir -p build

echo "== netlisting, routing and building examples/ringosc/ring.sch"
sh tools/regenerate_routed.sh examples/ringosc/ring.sch

echo "== netlisting examples/ringosc/tb_ring.sch"
xschem -n -q examples/ringosc/tb_ring.sch

echo "== running ngspice"
cp .spiceinit build/.spiceinit
( cd build && ngspice -b tb_ring.spice > ngspice_tb_ring.log 2>&1 ) \
    || { echo "ngspice exited non-zero -- tail of build/ngspice_tb_ring.log:"; tail -40 build/ngspice_tb_ring.log; exit 1; }

python3 tools/check_ring_sim.py build/ngspice_tb_ring.log
