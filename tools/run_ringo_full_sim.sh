#!/usr/bin/env bash
# Run the submodule's own, fully unmodified ring-oscillator testbench
# (ttsky-mini-mosbius/xschem/tb_mosbius_ringo.sch) through the real switch
# matrix -- all 188 tt_asw_3v3 instances, real pad_model loading, no
# lumped-capacitor approximation. Intended for a machine with more RAM than
# the ~1.9GB this project's usual dev host has (that ceiling is why this
# script exists instead of just using `mosbius watch`/the container directly
# -- see TODO.md for the background).
#
# Run from the repo root: tools/run_ringo_full_sim.sh
set -euo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT="$PWD"
mkdir -p build

echo "== Netlisting tb_mosbius_ringo.sch (unmodified) from ttsky-mini-mosbius/xschem =="
docker run --rm -v "$REPO_ROOT:/work" -w /work/ttsky-mini-mosbius/xschem \
  hpretl/iic-osic-tools:2026.05 --skip bash -lc '
    export PDK=sky130A PDK_ROOT=/foss/pdks
    xschem --rcfile $PDK_ROOT/sky130A/libs.tech/xschem/xschemrc -n -q \
      -o /work/build tb_mosbius_ringo.sch
  '

NETLIST="build/tb_mosbius_ringo.spice"
if [ ! -f "$NETLIST" ]; then
  echo "ERROR: expected $NETLIST, not found. Check the netlist filename xschem actually produced in build/." >&2
  exit 1
fi

echo "== Patching the netlist's .control block for headless batch mode =="
# The schematic's embedded .control block only has `plot` (interactive,
# needs X11) -- swap in `wrdata` so this works with `ngspice -b`, without
# touching the submodule itself (only the generated build/ copy).
python3 - "$NETLIST" <<'PYEOF'
import re, sys
path = sys.argv[1]
text = open(path).read()
# Note the 3-space indentation in the .control block -- an unindented
# match silently does nothing (no error), leaving the interactive `plot`
# in place and producing no wrdata output under `ngspice -b`. Also: a
# SINGLE wrdata call with two vectors duplicates the time column per
# vector (time,v(out),time,v(out_ref) -- 4 columns per line, not 2), which
# silently broke this script's own parser below (every line failed a
# 2-column check and got skipped, "No data" with no real error). Two
# separate single-vector calls instead -- we only need v(out) anyway.
old_ctrl = "   plot v(out)\n   plot v(out_ref)"
assert old_ctrl in text, "control block plot lines not found -- check the netlist's .control section"
text = text.replace(old_ctrl, "   wrdata ringo_full_tb.txt v(out)")
open(path, "w").write(text)
PYEOF

echo "== Copying .spiceinit alongside the netlist (ngspice only reads its own cwd) =="
cp .spiceinit build/.spiceinit

echo "== Running ngspice (budget ~2min+ for sky130A model load, more for a 188-switch deck) =="
docker run --rm -v "$REPO_ROOT:/work" -w /work/build \
  hpretl/iic-osic-tools:2026.05 --skip bash -lc '
    export PDK=sky130A PDK_ROOT=/foss/pdks
    ngspice -b tb_mosbius_ringo.spice
  '

echo "== Measuring period/frequency from build/ringo_full_tb.txt =="
python3 - <<'PYEOF'
import sys

def load(path):
    # Defensive: take the first two whitespace-separated fields as
    # (time, value) and ignore anything after. wrdata's exact column count
    # can vary (e.g. it duplicates the time column per extra vector if a
    # single call is ever given more than one), so requiring an exact
    # column count is fragile -- this already broke once on a 4-column
    # file when the script assumed 2.
    t, v = [], []
    with open(path) as f:
        for line in f:
            parts = line.split()
            if len(parts) < 2:
                continue
            try:
                t.append(float(parts[0]))
                v.append(float(parts[1]))
            except ValueError:
                continue
    return t, v

def periods(t, v, mid):
    crossings = []
    for i in range(1, len(v)):
        if v[i-1] < mid <= v[i]:
            # linear interpolate the crossing time
            frac = (mid - v[i-1]) / (v[i] - v[i-1])
            crossings.append(t[i-1] + frac * (t[i] - t[i-1]))
    return [b - a for a, b in zip(crossings, crossings[1:])]

t, v = load("build/ringo_full_tb.txt")
if not t:
    print("No data in build/ringo_full_tb.txt -- simulation likely didn't complete. Check ngspice output above for errors.")
    sys.exit(1)

# Restrict to steady state before computing the threshold -- the global
# min/max otherwise includes the 0V startup transient, which skews the
# midpoint low enough to miss real steady-state crossings (found the hard
# way on run_ring_pad_loaded.sh/run_ringo_no_stage2_pad.sh; this script
# hadn't been fixed the same way yet).
steady = [(ti, vi) for ti, vi in zip(t, v) if ti > 20e-9]
if len(steady) < 10:
    print(f"Only {len(steady)} points after the 20ns startup cutoff -- widen the window or check the run completed.")
    sys.exit(1)
st, sv = zip(*steady)
mid = (max(sv) + min(sv)) / 2
ps = periods(list(st), list(sv), mid)
if len(ps) < 3:
    print(f"Only {len(ps)} period(s) found on v(out) -- not enough to confirm oscillation. "
          f"Signal range was {min(sv):.3f}V to {max(sv):.3f}V over {t[-1]*1e9:.1f}ns simulated. "
          f"May need a longer .tran window if the real frequency is much lower than expected.")
    sys.exit(0)

# use the last few periods, after any startup transient
tail = ps[-min(10, len(ps)):]
avg = sum(tail) / len(tail)
print(f"Found {len(ps)} periods on v(out). Last {len(tail)} average: "
      f"{avg*1e9:.4f}ns -> {1/avg/1e6:.2f}MHz")
print(f"Individual last-{len(tail)} periods (ns): " + ", ".join(f"{p*1e9:.4f}" for p in tail))
PYEOF
