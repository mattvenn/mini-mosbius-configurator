#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Monthly regression check for examples/srlatch: netlists it, routes it,
# builds the routed subcircuit, runs the real tb_srlatch.sch testbench
# through ngspice, and checks the stored levels and the reset delays land
# near the reference measurements in examples/srlatch/README.md via
# check_srlatch_sim.py. This is what
# .github/workflows/spice-regression.yml runs once a month, alongside the
# inverter, ring and differential amplifier checks.
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

cd "$(dirname "$0")/.."
mkdir -p build

echo "== netlisting, routing and building examples/srlatch/srlatch.sch"
sh tools/regenerate_routed.sh examples/srlatch/srlatch.sch

echo "== netlisting examples/srlatch/tb_srlatch.sch"
xschem -n -q examples/srlatch/tb_srlatch.sch

echo "== running ngspice"
cp .spiceinit build/.spiceinit
( cd build && ngspice -b tb_srlatch.spice > ngspice_tb_srlatch.log 2>&1 ) \
    || { echo "ngspice exited non-zero -- tail of build/ngspice_tb_srlatch.log:"; tail -40 build/ngspice_tb_srlatch.log; exit 1; }

python3 tools/check_srlatch_sim.py build/ngspice_tb_srlatch.log
