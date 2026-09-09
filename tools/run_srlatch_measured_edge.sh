#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Re-run examples/srlatch's testbench with the stimulus the bench actually
# applies, so its reset delay can be compared with the one measured on
# silicon by tools/ad3/measure_srlatch_edge_ad3.py.
#
# Why this exists rather than a change to tb_srlatch.sch: the sheet drives
# RESET as a 1 ns step, and an Analog Discovery's generator takes about
# 20 ns (10%-90%) to move 3.3 V. A latch driven by a 20 ns ramp does not
# switch when a latch driven by a 1 ns step does, so treset_drawn and
# treset_routed as published are not the quantity the bench measures --
# they are the right numbers for the sheet and the wrong ones for this
# comparison. The sheet keeps them; this script asks the same two decks
# what they do under the bench's own stimulus and probe.
#
# Everything here is a rewrite of the generated netlist, in the manner of
# tools/sweep_corners.sh: the committed schematics are untouched, so every
# published number still comes from the sheet as drawn.
#
# Needs xschem/ngspice, so run it inside the IIC-OSIC-TOOLS container from
# the repo root:
#
#   docker run --rm -v "$PWD:/work" -w /work hpretl/iic-osic-tools:2026.05 \
#       --skip bash -lc 'sh tools/run_srlatch_measured_edge.sh'
#
# Takes an optional process corner (default tt) and part (default
# tt_um_tnt_mosbius):
#
#   sh tools/run_srlatch_measured_edge.sh ss
#   sh tools/run_srlatch_measured_edge.sh tt tt_um_mosbius
#
# tnt's chip measured as an ss part -- see CLAUDE.md for the two-circuit
# argument that establishes that -- so ss is the corner to compare a
# silicon timing against there; tt_um_mosbius's corner is not established,
# so tt (the committed sheets' own corner) is the reasonable default for
# it. tt stays what CI uses either way.
set -e

CORNER=${1:-tt}
PROJECT=${2:-tt_um_tnt_mosbius}
export MOSBIUS_PROJECT="$PROJECT"

# The measured 10%-90% stimulus edge for whichever part -- both from
# tools/ad3/measure_srlatch_edge_ad3.py, close but not identical since
# it's the same AD3 generator either way.
case "$PROJECT" in
    tt_um_tnt_mosbius) STIMULUS_NS=20.2 ;;
    tt_um_mosbius)     STIMULUS_NS=19.63 ;;
    *) echo "no measured stimulus edge recorded for $PROJECT -- add one" \
            "to this script's case statement" >&2; exit 1 ;;
esac
SUFFIX=""
[ "$PROJECT" = "tt_um_mosbius" ] && SUFFIX="_kang"

cd "$(dirname "$0")/.."
mkdir -p build

# Always rebuild the routed subcircuit rather than reusing whatever is in
# build/ -- it is cheap (route + build, no ngspice), and reusing it would
# silently replay whichever part it was last built for regardless of
# $PROJECT.
echo "== building the routed subcircuit for $PROJECT"
sh tools/regenerate_routed.sh examples/srlatch/srlatch.sch

# Always re-netlist rather than reusing whatever is in build/. The
# testbench's `.include` of the routed subcircuit is written as an
# absolute path, so a netlist generated under a different mount point --
# a previous container run, or a host with the repo somewhere else --
# points at a directory that does not exist here, and ngspice stops with
# "Could not find include file".
echo "== netlisting examples/srlatch/tb_srlatch.sch"
rm -f build/tb_srlatch.spice
xschem -n -q examples/srlatch/tb_srlatch.sch || true
[ -f build/tb_srlatch.spice ] || { echo "xschem wrote no netlist" >&2; exit 1; }
grep -q 'IS MISSING' build/tb_srlatch.spice && {
    echo "build/tb_srlatch.spice has unresolved symbols -- run this from the" >&2
    echo "repo root, so xschem reads the repo's own xschemrc." >&2; exit 1; }

echo "== rewriting the stimulus, the probe and the analysis ($STIMULUS_NS ns edge)"
python3 tools/rewrite_srlatch_measured_edge.py \
    build/tb_srlatch.spice build/tb_srlatch_measured_edge.spice \
    --stimulus-ns "$STIMULUS_NS" --prefix "srlatch_edge$SUFFIX"
if [ "$CORNER" != "tt" ]; then
    echo "== switching the model library to $CORNER"
    sed -i "s|\(sky130.lib.spice\) tt|\1 $CORNER|" build/tb_srlatch_measured_edge.spice
fi

echo "== running ngspice at $CORNER"
cp .spiceinit build/.spiceinit
log="ngspice_tb_srlatch_measured_edge$SUFFIX.log"
( cd build && ngspice -b tb_srlatch_measured_edge.spice > "$log" 2>&1 ) \
    || { echo "ngspice exited non-zero -- tail of the log:"; \
         tail -40 "build/$log"; exit 1; }

grep -E '^(treset|vhigh|vlow)' "build/$log" || true
echo
echo "Compare treset_* above with the silicon number from"
echo "tools/ad3/measure_srlatch_edge_ad3.py, not with the sheet's own treset."
