#!/usr/bin/env bash
# Measure both mini-MOSbius parts' bus-row capacitance from their own layouts,
# the same way, so the two sets can be compared rather than merely both quoted.
#
# This is NOT part of the normal workflow. The numbers it produces are static,
# committed assets in mosbius/chips/__init__.py; re-run this only if a chip's
# layout or the sky130A extraction rules change.
#
# Both submodules are read-only, so everything is copied into build/ first and
# magic works there. Andrew Kang's repo ships its own .ext files, which are
# reused; tnt's ships none, so his are extracted from the .mag hierarchy here.
# Both then get the same ext2spice settings -- `cthresh 5f rthresh 10`, flat --
# which is what makes the comparison mean anything.
#
# Run from the repo root: tools/extract_bus_caps.sh
set -euo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT="$PWD"
IMAGE=hpretl/iic-osic-tools:2026.05

for part in tnt kang; do
  case "$part" in
    tnt)  src=ttsky-mini-mosbius/mag       top=tt_um_tnt_mosbius  extract=yes ;;
    kang) src=ttsky25a-minimosbius/mag     top=tt_um_mosbius      extract=no  ;;
  esac

  if [ ! -d "$src" ]; then
    echo "ERROR: $src is missing. This needs both layout submodules:" >&2
    echo "       git submodule update --init" >&2
    exit 1
  fi

  work="build/buscaps_$part"
  rm -rf "$work"
  mkdir -p "$work"
  cp "$src"/*.mag "$work"/
  # Andrew's committed .ext files are the extraction he ran; reusing them is
  # the point, so copy them where they will be found. tnt has none.
  cp "$src"/*.ext "$work"/ 2>/dev/null || true

  {
    echo "load $top -dereference"
    if [ "$extract" = yes ]; then
      echo "select top cell"
      echo "extract do local"
      echo "extract all"
    fi
    echo "ext2spice rthresh 10"
    echo "ext2spice cthresh 5f"
    echo "ext2spice scale off"
    echo "ext2spice hierarchy off"
    echo "ext2spice format ngspice"
    echo "ext2spice -o ${top}_flat.spice"
    echo "quit -noprompt"
  } > "$work/ext.tcl"

  echo "== Extracting $top =="
  docker run --rm -v "$REPO_ROOT/$work:/work" -w /work "$IMAGE" --skip bash -lc '
      export PDK=sky130A PDK_ROOT=/foss/pdks
      magic -dnull -noconsole \
        -rcfile $PDK_ROOT/sky130A/libs.tech/magic/sky130A.magicrc ext.tcl
    ' | grep -v '^\[INFO\]' | tail -3

  echo
  python3 tools/extract_bus_caps.py "$work/${top}_flat.spice" --part "$part"
  echo
done
