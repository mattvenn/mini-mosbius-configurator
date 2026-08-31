#!/usr/bin/env bash
# Controlled comparison against tools/run_ringo_full_sim.sh's 93.5MHz result:
# same unmodified tb_mosbius_ringo.sch, with exactly one change -- the real
# pad_model instance on stage 2's input (bus_A[1], the only one of the
# ring's 3 loop-critical nodes that carries a real package pin, per
# TODO.md Sec 1 / the tb_mosbius_ringo.sch comment block at lines 326-331)
# is replaced with a direct short, so that node is unloaded like stage 1's
# and stage 3's inputs already are. Isolates how much that one asymmetric
# pad actually matters to the oscillation frequency, vs just reasoning
# about it. Everything else -- the other 4 real pad instances (n2-n4, out,
# Ibias), the full real switch matrix, real device models -- is untouched.
#
# Same memory requirement as run_ringo_full_sim.sh: this dev host's 1.9GB
# is not enough for the full unfiltered circuit, run this on a machine
# with more RAM. Run from the repo root: tools/run_ringo_no_stage2_pad.sh
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
OUT_NETLIST="build/tb_mosbius_ringo_no_stage2_pad.spice"
if [ ! -f "$NETLIST" ]; then
  echo "ERROR: expected $NETLIST, not found." >&2
  exit 1
fi

echo "== Verifying and removing the one pad instance on stage 2's input (bus_A[1]) =="
EXPECTED_LINE='x2[1] GND n1 bus_A[1] pad_model'
if ! grep -qF "$EXPECTED_LINE" "$NETLIST"; then
  echo "ERROR: expected netlist line not found:" >&2
  echo "  $EXPECTED_LINE" >&2
  echo "xschem's netlisting output format may have changed -- check 'grep -in pad_model $NETLIST' and update this script's replacement accordingly, don't just force it through." >&2
  exit 1
fi

python3 - "$NETLIST" "$OUT_NETLIST" <<'PYEOF'
import sys
src, dst = sys.argv[1], sys.argv[2]
text = open(src).read()

old = "x2[1] GND n1 bus_A[1] pad_model"
# Comment on its own line (a trailing "* comment" after other tokens is NOT
# valid SPICE -- * only starts a comment at the start of a line), and no
# apostrophe (ngspice uses ' for expression syntax, e.g. the ad="'int(...)'"
# parameters elsewhere in this netlist -- a stray ' in what should be plain
# text breaks its parser with a confusing "closing } not found" error).
new = ("* pad on stage 2 input removed for comparison\n"
       "Rshort_stage2pad n1 bus_A[1] 1m")
assert text.count(old) == 1, f"expected exactly one match, found {text.count(old)}"
text = text.replace(old, new)

# Same headless-batch patch as run_ringo_full_sim.sh (note the 3-space
# indentation in the .control block -- a plain "plot v(out)\nplot v(out_ref)"
# match fails without it). Two SEPARATE single-vector wrdata calls, not one
# call with both vectors -- ngspice's wrdata duplicates the time column per
# vector when given more than one (time,v(out),time,v(out_ref), 4 columns
# per line, not 2), which silently broke this script's own parser the first
# time it actually ran (every line failed the 2-column check and got
# skipped, "No data" with no real error). We only need v(out) anyway.
old_ctrl = "   plot v(out)\n   plot v(out_ref)"
new_ctrl = "   wrdata ringo_no_stage2_pad_tb.txt v(out)"
assert old_ctrl in text, "control block plot lines not found -- check the netlist's .control section"
text = text.replace(old_ctrl, new_ctrl)

open(dst, "w").write(text)
print(f"Wrote {dst}")
PYEOF

echo "== Copying .spiceinit alongside the netlist =="
cp .spiceinit build/.spiceinit

echo "== Running ngspice (budget ~2min+ for sky130A model load, more for the full deck) =="
docker run --rm -v "$REPO_ROOT:/work" -w /work/build \
  hpretl/iic-osic-tools:2026.05 --skip bash -lc '
    export PDK=sky130A PDK_ROOT=/foss/pdks
    ngspice -b tb_mosbius_ringo_no_stage2_pad.spice
  '

echo "== Measuring period/frequency from build/ringo_no_stage2_pad_tb.txt =="
python3 - <<'PYEOF'
import sys

def load(path):
    # Defensive: take the first two whitespace-separated fields as
    # (time, value) and ignore anything after -- see run_ringo_full_sim.sh
    # for why an exact column count is fragile here.
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

t, v = load("build/ringo_no_stage2_pad_tb.txt")
if not t:
    print("No data -- simulation likely didn't complete. Check ngspice output above for errors.")
    sys.exit(1)

# restrict to steady state, skip startup transient
steady = [(ti, vi) for ti, vi in zip(t, v) if ti > 20e-9]
if len(steady) < 10:
    print(f"Only {len(steady)} points after the 20ns startup cutoff -- widen the window or check the run completed.")
    sys.exit(1)
st, sv = zip(*steady)
mid = (max(sv) + min(sv)) / 2

ps = periods(list(st), list(sv), mid)
if len(ps) < 3:
    print(f"Only {len(ps)} period(s) found on v(out) in steady state -- not enough to confirm oscillation. "
          f"Signal range was {min(sv):.3f}V to {max(sv):.3f}V.")
    sys.exit(0)

tail = ps[-min(10, len(ps)):]
avg = sum(tail) / len(tail)
print(f"No-stage2-pad result: {len(ps)} periods found, last {len(tail)} average: "
      f"{avg*1e9:.4f}ns -> {1/avg/1e6:.2f}MHz")
print(f"Compare against the full baseline (tools/run_ringo_full_sim.sh): 10.7ns / 93.5MHz")
print(f"Individual last-{len(tail)} periods (ns): " + ", ".join(f"{p*1e9:.4f}" for p in tail))
PYEOF
