#!/usr/bin/env bash
# Rebuild mosbius/data/kang_device_library.spice -- the real switch matrix,
# row-coupling capacitance and pad model that mosbius/simulate.py embeds when
# it writes an as-routed deck for Andrew Kang's mini-MOSbius.
#
# The counterpart of tools/rebuild_mosbius_device_library.sh, which does the
# same job for tnt's part. Like that one, this is NOT part of the normal
# `mosbius simulate` workflow: the library is a static, committed asset, built
# once and reused for every design. Only re-run it if the chip design
# (ttsky25a-minimosbius) or the sky130A models it depends on change.
#
# Unlike tnt's, this needs no docker and no xschem. Andrew's repo commits the
# netlist of the schematic that was taped out, so the whole build is a text
# transformation of a file that is already in the tree.
#
# Run from the repo root: tools/build_kang_device_library.sh
set -euo pipefail

cd "$(dirname "$0")/.."
python3 tools/build_kang_device_library.py "$@"
