#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Monthly regression check for examples/inverter: netlists it, routes it,
# builds the routed subcircuit, runs the real tb_inverter.sch testbench
# through ngspice, and checks trise_drawn/trise_routed land near the
# reference measurements in examples/inverter/README.md via
# check_inverter_sim.py. This is what
# .github/workflows/spice-regression.yml runs once a month.
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

cd "$(dirname "$0")/.."
mkdir -p build

echo "== netlisting examples/inverter/inverter.sch"
xschem -n -q examples/inverter/inverter.sch

echo "== routing build/inverter.spice"
python3 -m mosbius.cli route build/inverter.spice --out build/inverter.mosbius.json

echo "== building build/inverter_routed.spice"
python3 -m mosbius.cli simulate build/inverter.mosbius.json

echo "== netlisting examples/inverter/tb_inverter.sch"
xschem -n -q examples/inverter/tb_inverter.sch

echo "== running ngspice"
cp .spiceinit build/.spiceinit
( cd build && ngspice -b tb_inverter.spice > ngspice_tb_inverter.log 2>&1 ) \
    || { echo "ngspice exited non-zero -- tail of build/ngspice_tb_inverter.log:"; tail -40 build/ngspice_tb_inverter.log; exit 1; }

python3 tools/check_inverter_sim.py build/ngspice_tb_inverter.log
