#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Re-run the currentsource testbench at every PDK corner.
#
# The question this answers is specific, and it is why the skewed corners
# matter as much as ss. Measured on silicon, the two mirror legs disagree
# with the tt deck in OPPOSITE directions -- psource_a 8.6% low, nsink_a
# 8.1% high -- and the two do not pass through the same devices.
# `nsink_a` copies the NMOS reference directly, one stage. `psource_a`
# goes NMOS reference -> the 1:1 NMOS copy -> the PMOS diode -> the PMOS
# slave: three stages, the last two PMOS. So a corner that skews n
# against p (fs, sf) should move them apart, while one that slows both
# together (ss) should move them the same way. Running all five says
# which, if either, the chip looks like.
#
# Run inside the IIC-OSIC-TOOLS container from the repo root, after
# tools/ci/check_example_sim.sh currentsource has produced build/tb_currentsource.spice:
#
#   docker run --rm -v "$PWD:/work" -w /work hpretl/iic-osic-tools:latest \
#       --skip bash -lc 'sh tools/sweep_corners_currentsource.sh'
#
# Budget ~2 minutes per corner: sky130A's combined model library takes
# that long to parse whatever the circuit is.
#
# The corner is substituted in the *netlist*, not the schematic, exactly
# as tools/sweep_corners.sh does it -- so the committed schematics, and
# therefore every number the READMEs quote, stay at tt.
set -e

cd "$(dirname "$0")/.."
cd build
cp -f ../.spiceinit .

# Two rewrites, not one. The corner is the point; the .include is
# housekeeping, and it bites because xschem writes an ABSOLUTE path to the
# routed subcircuit -- whatever the repo was mounted at when the netlist
# was made. Mount it anywhere else and ngspice stops with "Could not find
# include file" before it reaches a single model. Everything here runs
# from build/, so the bare filename is right wherever the repo lives.
for c in tt fs sf ff ss; do
    echo "== $c"
    sed -e "s|sky130.lib.spice tt|sky130.lib.spice $c|" \
        -e "s|^\.include .*/\([^/]*_routed\.spice\)|.include \1|" \
        tb_currentsource.spice > tb_cs_$c.spice

    # Delete the output before the run, never rename it after. Renaming
    # afterwards cannot tell a file this run wrote from one left over from
    # a previous one, so a failed ngspice quietly relabels stale data with
    # this corner's name -- and, worse, moves currentsource_tb.txt out from
    # under the plotting script, which reads it by that name.
    rm -f currentsource_tb.txt
    ngspice -b tb_cs_$c.spice > log_cs_$c.log 2>&1 || true
    if [ -f currentsource_tb.txt ]; then
        cp currentsource_tb.txt currentsource_tb_$c.txt
    else
        echo "  (ngspice wrote no sweep -- see build/log_cs_$c.log)"
    fi
    grep -iE "^i_(source|sink)_(drawn|routed) *=" log_cs_$c.log \
        || echo "  (no measurements in the log -- see build/log_cs_$c.log)"
done

# Leave the tt sweep in place under its plain name: that is the file
# tools/plot_currentsource_comparison.py reads, and tt is what every
# committed number is quoted at.
cp -f currentsource_tb_tt.txt currentsource_tb.txt 2>/dev/null || true

echo
echo "done -- the per-corner sweeps are build/currentsource_tb_<corner>.txt"
