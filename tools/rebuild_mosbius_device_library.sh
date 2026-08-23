#!/usr/bin/env bash
# Rebuild mosbius/data/mosbius_device_library.spice -- the real switch
# matrix + row-coupling capacitance that mosbius/simulate.py's generated
# testbenches embed. This is NOT part of the normal `mosbius simulate`
# workflow -- the library is a static, committed asset, built once and
# reused for every design. Only re-run this if the chip design
# (ttsky-mini-mosbius) or the sky130A PDK models it depends on change.
#
# What it does: netlists the upstream submodule's own
# tb_mosbius_ringo.sch (never modified -- read-only submodule), which
# pulls in mosbius.sym's full real switch-matrix hierarchy, extracts
# everything from that hierarchy onward, and inserts the real ~43.19fF
# row-coupling capacitance (one switch's own bus stub to its column's
# shared device-terminal net -- see mosbius/spice.py's module comments
# for the full provenance of that value) on all 150 real matrix-column
# switches, directly inside .subckt mosbius's body -- NOT at top-level
# scope, which would silently create disconnected phantom nodes instead
# of the real ones (a real bug hit and fixed earlier in this project's
# TODO.md Sec 1 ring-oscillator investigation).
#
# Run from the repo root: tools/rebuild_mosbius_device_library.sh
set -euo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT="$PWD"
mkdir -p build mosbius/data

echo "== Netlisting tb_mosbius_ringo.sch from ttsky-mini-mosbius/xschem =="
docker run --rm -v "$REPO_ROOT:/work" -w /work/ttsky-mini-mosbius/xschem \
  hpretl/iic-osic-tools:latest --skip bash -lc '
    export PDK=sky130A PDK_ROOT=/foss/pdks
    xschem --rcfile $PDK_ROOT/sky130A/libs.tech/xschem/xschemrc -n -q \
      -o /work/build tb_mosbius_ringo.sch
  '

SRC_NETLIST="build/tb_mosbius_ringo.spice"
if [ ! -f "$SRC_NETLIST" ]; then
  echo "ERROR: expected $SRC_NETLIST, not found." >&2
  exit 1
fi

echo "== Extracting the device library and inserting row-coupling caps =="
python3 - "$SRC_NETLIST" <<'PYEOF'
import sys

src = sys.argv[1]
lines = open(src).read().split("\n")

start = next(i for i, l in enumerate(lines) if l.startswith("* expanding   symbol:  mosbius.sym"))
library_lines = lines[start:]

COUPLING_F = "43.19f"
coupling_lines = []
n_matched = 0
for line in library_lines:
    if not line.endswith(" tt_asw_3v3"):
        continue
    parts = line.split()
    if len(parts) != 8:
        continue
    name, mod, bus = parts[0], parts[5], parts[6]
    if not mod.startswith("xpt_"):
        continue
    n_matched += 1
    cname = "Ccpl_" + name.replace("[", "_").replace("]", "_").replace(".", "_")
    coupling_lines.append(f"{cname} {mod} {bus} {COUPLING_F}")

assert n_matched == 150, f"expected 150 real matrix-column switches, matched {n_matched} -- xschem's netlist format may have changed, check before trusting this"

out_lines = []
inserted = False
i = 0
while i < len(library_lines):
    line = library_lines[i]
    out_lines.append(line)
    if not inserted and line.startswith(".subckt mosbius "):
        i += 1
        while i < len(library_lines) and library_lines[i].startswith("+"):
            out_lines.append(library_lines[i])
            i += 1
        out_lines.append("* Row-coupling caps (see tools/rebuild_mosbius_device_library.sh)")
        out_lines.extend(coupling_lines)
        out_lines.append("")
        inserted = True
        continue
    i += 1
assert inserted, "could not find .subckt mosbius to insert coupling caps inside"

dst = "mosbius/data/mosbius_device_library.spice"
with open(dst, "w") as f:
    f.write("\n".join(out_lines) + "\n")
print(f"Wrote {dst}: {n_matched} coupling caps inserted, {len(out_lines)} lines total")
PYEOF

echo "== Verifying the result =="
python3 - <<'PYEOF'
path = "mosbius/data/mosbius_device_library.spice"
text = open(path).read()
n_caps = text.count("\nCcpl_")
assert n_caps == 150, f"expected 150 Ccpl_ lines, found {n_caps}"
n_subckt = text.count("\n.subckt ")
n_ends = text.count("\n.ends")
assert n_subckt == n_ends, f".subckt/.ends mismatch: {n_subckt} vs {n_ends}"
print(f"OK: {n_caps} coupling caps present, {n_subckt} subckt/.ends pairs balanced.")
PYEOF

echo "== Checking the submodule is still clean (magic/xschem sometimes leak stray files) =="
if [ -n "$(cd ttsky-mini-mosbius && git status --short)" ]; then
  echo "WARNING: ttsky-mini-mosbius has uncommitted changes -- investigate before committing." >&2
  (cd ttsky-mini-mosbius && git status --short) >&2
  exit 1
fi
echo "Submodule clean."
