#!/usr/bin/env bash
# Same 93.5MHz baseline as run_ringo_full_sim.sh (tb_mosbius_ringo.sch,
# unmodified, full real switch matrix + real pad model), plus one real
# layout-extracted effect that's been skipped from every ring-oscillator
# simulation in this investigation so far: the capacitive coupling
# between each tt_asw_3v3 switch's own `bus` terminal and the shared
# `mod` net its whole column routes to (the actual device terminal, e.g.
# a FET gate). This is NOT "adjacent bus row" coupling -- re-verified
# directly against a fresh magic PEX extraction of
# ttsky-mini-mosbius/mag/asw_col_a.mag (cthresh=5fF, rthresh=10ohm):
# every one of a column's 6 switches shares the exact same `mod` node
# (confirmed -- only "[0].mod" appears anywhere in the extraction, magic
# recognized all 6 as literally the same net), and each switch's own
# `bus` terminal couples to that shared `mod` trace at a consistent
# ~43.19fF regardless of row (43.16-43.21fF across all 6, see the six
# C4/C5/C11/C17/C20/C26 lines in that extraction) -- physically because
# the device-terminal trace runs the height of the column past every
# row's local bus stub, not because of row-to-row adjacency.
#
# Applies to the 150 real matrix-column switches only (26 columns: 22
# single-side x 6 rows = 132, plus 3 dual-side "asw_col_ab" columns x 6
# switches split 3-per-side = 18, total 150 -- confirmed by counting
# instances in the actual netlist whose `mod` argument starts with
# `xpt_`, the crosspoint-net naming convention). Explicitly NOT applied
# to: the 6 cfg_bus_short switches (mod is a bus_A/bus_B net, not a
# device terminal -- different physical structure, not re-verified here)
# or the OTA's/mirror's/diff-pair's own internal tt_asw_3v3 instances
# (mod is an internal signal like outp/outm/Vd_1x, also a different
# structure, not covered by the asw_col_a extraction this is based on).
#
# Same memory requirement as run_ringo_full_sim.sh: needs a machine with
# more RAM than this dev host's 1.9GB for the full 186-switch matrix --
# see TODO.md Sec 1 / tools/run_ringo_full_sim.sh's own header.
#
# Run from the repo root: tools/run_ringo_row_coupling.sh
set -euo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT="$PWD"
mkdir -p build

echo "== Netlisting tb_mosbius_ringo.sch (unmodified) from ttsky-mini-mosbius/xschem =="
docker run --rm -v "$REPO_ROOT:/work" -w /work/ttsky-mini-mosbius/xschem \
  hpretl/iic-osic-tools:latest --skip bash -lc '
    export PDK=sky130A PDK_ROOT=/foss/pdks
    xschem --rcfile $PDK_ROOT/sky130A/libs.tech/xschem/xschemrc -n -q \
      -o /work/build tb_mosbius_ringo.sch
  '

SRC_NETLIST="build/tb_mosbius_ringo.spice"
OUT_NETLIST="build/tb_mosbius_ringo_row_coupling.spice"
if [ ! -f "$SRC_NETLIST" ]; then
  echo "ERROR: expected $SRC_NETLIST, not found." >&2
  exit 1
fi

echo "== Adding the row-coupling caps (bus<->mod, one per real matrix-column switch) =="
python3 - "$SRC_NETLIST" "$OUT_NETLIST" <<'PYEOF'
import re, sys

src, dst = sys.argv[1], sys.argv[2]
text = open(src).read()
lines = text.split("\n")

COUPLING_F = "43.19f"
coupling_lines = []
n_matched = 0
for line in lines:
    if not line.endswith(" tt_asw_3v3"):
        continue
    parts = line.split()
    # <name> VGND VDPWR VAPWR ctrl mod bus tt_asw_3v3 -- 8 tokens
    if len(parts) != 8:
        continue
    name, mod, bus = parts[0], parts[5], parts[6]
    if not mod.startswith("xpt_"):
        continue  # not a real matrix-column switch (bus_short / OTA-internal / mirror-internal)
    n_matched += 1
    cname = "Ccpl_" + name.replace("[", "_").replace("]", "_").replace(".", "_")
    coupling_lines.append(f"{cname} {mod} {bus} {COUPLING_F}")

assert n_matched == 150, f"expected 150 real matrix-column switches, matched {n_matched} -- xschem's netlist format or instance count may have changed, check before trusting this run"

# Insert the coupling caps right before the .control block (same
# 3-space-indented-.control-block netlist as always -- insert before the
# bare ".control" line, not inside it).
out_lines = []
inserted = False
for line in lines:
    if not inserted and line == ".control":
        out_lines.append("* Row-coupling caps added by tools/run_ringo_row_coupling.sh")
        out_lines.extend(coupling_lines)
        out_lines.append("")
        inserted = True
    out_lines.append(line)
assert inserted, "could not find the .control block to insert coupling caps before"

text = "\n".join(out_lines)

# Same headless-batch patch as run_ringo_full_sim.sh (3-space indentation,
# one vector per wrdata call -- see that script's own comments for why).
old_ctrl = "   plot v(out)\n   plot v(out_ref)"
assert old_ctrl in text, "control block plot lines not found -- check the netlist's .control section"
text = text.replace(old_ctrl, "   wrdata ringo_row_coupling_tb.txt v(out)")

open(dst, "w").write(text)
print(f"Wrote {dst}: {n_matched} coupling caps added ({COUPLING_F} each)")
PYEOF

echo "== Sanity-checking the generated netlist =="
python3 <<'PYEOF'
path = "build/tb_mosbius_ringo_row_coupling.spice"
text = open(path).read()
n_caps = text.count("\nCcpl_")
assert n_caps == 150, f"expected 150 Ccpl_ lines, found {n_caps}"
n_subckt = text.count("\n.subckt ")
n_ends = text.count("\n.ends")
assert n_subckt == n_ends, f".subckt/.ends mismatch: {n_subckt} vs {n_ends}"
assert "wrdata ringo_row_coupling_tb.txt v(out)" in text, "wrdata patch missing"
print(f"OK: {n_caps} coupling caps present, {n_subckt} subckt/.ends pairs balanced, wrdata patch present.")
PYEOF

echo "== Copying .spiceinit alongside the netlist =="
cp .spiceinit build/.spiceinit

echo "== Running ngspice (budget ~2min+ for sky130A model load, more for the full 186-switch deck -- needs a machine with real RAM headroom) =="
docker run --rm -v "$REPO_ROOT:/work" -w /work/build \
  hpretl/iic-osic-tools:latest --skip bash -lc '
    export PDK=sky130A PDK_ROOT=/foss/pdks
    ngspice -b tb_mosbius_ringo_row_coupling.spice
  '

echo "== Measuring period/frequency from build/ringo_row_coupling_tb.txt =="
python3 - <<'PYEOF'
import sys

def load(path):
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
            frac = (mid - v[i-1]) / (v[i] - v[i-1])
            crossings.append(t[i-1] + frac * (t[i] - t[i-1]))
    return [b - a for a, b in zip(crossings, crossings[1:])]

t, v = load("build/ringo_row_coupling_tb.txt")
if not t:
    print("No data -- simulation likely didn't complete. Check ngspice output above for errors.")
    sys.exit(1)

# Restrict to steady state before computing the threshold -- the global
# min/max otherwise includes the 0V startup transient, which skews the
# midpoint low enough to miss real steady-state crossings (found the hard
# way earlier in this investigation, on run_ring_pad_loaded.sh).
steady = [(ti, vi) for ti, vi in zip(t, v) if ti > 20e-9]
if len(steady) < 10:
    print(f"Only {len(steady)} points after the 20ns startup cutoff -- widen the window or check the run completed.")
    sys.exit(1)
st, sv = zip(*steady)
mid = (max(sv) + min(sv)) / 2
ps = periods(list(st), list(sv), mid)
if len(ps) < 3:
    print(f"Only {len(ps)} period(s) found on v(out) -- not enough to confirm oscillation. "
          f"Signal range was {min(sv):.3f}V to {max(sv):.3f}V over {t[-1]*1e9:.1f}ns simulated.")
    sys.exit(0)

tail = ps[-min(10, len(ps)):]
avg = sum(tail) / len(tail)
print(f"Found {len(ps)} periods on v(out). Last {len(tail)} average: "
      f"{avg*1e9:.4f}ns -> {1/avg/1e6:.2f}MHz")
print("Compare against the baseline (tools/run_ringo_full_sim.sh): 10.7ns / 93.5MHz")
print(f"Individual last-{len(tail)} periods (ns): " + ", ".join(f"{p*1e9:.4f}" for p in tail))
PYEOF
