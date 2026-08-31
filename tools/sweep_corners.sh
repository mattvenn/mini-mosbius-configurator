#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Re-run the inverter and ring testbenches at every PDK corner, to ask
# which corner the chip on the bench actually behaves like.
#
# Run inside the IIC-OSIC-TOOLS container from the repo root, after the
# ordinary check_*_sim.sh scripts have produced the netlists:
#
#   docker run --rm -v "$PWD:/work" -w /work hpretl/iic-osic-tools:2026.05 \
#       --skip bash -lc 'sh tools/sweep_corners.sh'
#
# Then compare against the bench with:
#
#   python3 tools/compare_corners.py
#
# Budget ~2 minutes per corner per testbench: sky130A's combined model
# library takes that long to parse whatever the circuit is.
#
# The corner is substituted in the *netlist*, not the schematic. Each
# tb_*.sch carries `corner=tt` on its sky130_fd_pr/corner.sym instance,
# which netlists to a `.lib ... sky130.lib.spice tt` line; rewriting that
# one line leaves the committed schematics -- and therefore the numbers
# every README quotes -- alone.
set -e

cd "$(dirname "$0")/.."
cd build
cp -f ../.spiceinit .

for c in tt fs sf ff ss; do
    echo "== $c"

    sed "s|sky130.lib.spice tt|sky130.lib.spice $c|" tb_inverter.spice > tb_inv_$c.spice
    ngspice -b tb_inv_$c.spice > log_inv_$c.log 2>&1 || true
    mv -f inverter_dc_routed.txt inverter_dc_routed_$c.txt 2>/dev/null || true
    mv -f inverter_dc_drawn.txt inverter_dc_drawn_$c.txt 2>/dev/null || true
    grep -iE "^trise_" log_inv_$c.log || echo "  (inverter: no trise in log)"

    sed "s|sky130.lib.spice tt|sky130.lib.spice $c|" tb_ring.spice > tb_ring_$c.spice
    ngspice -b tb_ring_$c.spice > log_ring_$c.log 2>&1 || true
    grep -iE "freq_drawn = |freq_routed = " log_ring_$c.log || echo "  (ring: no freq in log)"
done

echo
echo "done -- now run: python3 tools/compare_corners.py"
