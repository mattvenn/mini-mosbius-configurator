#!/usr/bin/env bash
# Level-2 simulation of THIS PROJECT'S OWN ring oscillator
# (examples/ringosc/ring.sch, bitstream
# 3f008803f004001801000020100804000060040100000021) through the real
# switch matrix, with the real pad_model.sym wired onto every external
# package pin this specific design actually uses.
#
# Unlike tools/run_ringo_full_sim.sh (which reruns the *submodule's own*
# ring.sch-unrelated testbench, tb_mosbius_ringo.sch), ring.sch has no
# upstream testbench of its own -- there is nothing to netlist directly.
# So this script builds one: it reuses the *verified device library*
# (the `.subckt mosbius`, `pad_model`, `tt_asw_3v3`, etc. definitions)
# from netlisting tb_mosbius_ringo.sch -- proven correct, that's what
# produced the 93.5MHz result -- and generates a fresh top-level testbench
# around it: real VAPWR=3.3V/VDPWR=1.8V/Ibias=100uA sources, one Rcfg tie
# per config bit (using mosbius/bitmap.py + mosbius/model.py directly, the
# same source of truth mosbius/spice.py's render_config_spice() uses --
# not hand-typed), and exactly one pad_model instance.
#
# Per examples/ringosc/README.md, ring.sch brings out only ONE package pin
# for its whole 3-stage loop: ua1 = bus_A[1]. The other two loop nodes
# (bus_A[2], bus_A[6]/bus_B[6]) are internal-only bus rows with no real
# pin -- so "add the pad model to all external pins" for this design means
# exactly one pad_model instance, on bus_A[1].
#
# This avoids the coordinate-sensitive xschem-schematic-building approach
# (parsing mosbius.sym's B/pin-box lines, hand-placing 192 lab_wire labels
# -- a real trap hit twice already in this project: one bad coordinate
# silently floats a pin) entirely, by working at the SPICE level directly:
# mosbius/spice.py's render_config_spice() already proves each config pin
# net name is a plain string tie target, no schematic geometry involved.
#
# Same memory requirement as the other two scripts in this directory:
# this dev host's 1.9GB is not enough for the full unfiltered circuit --
# run this on a machine with more RAM. The netlisting/generation steps
# below are cheap and safe to run anywhere; only the final `ngspice` step
# needs the extra memory.
#
# Run from the repo root: tools/run_ring_pad_loaded.sh
set -euo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT="$PWD"
mkdir -p build

RING_BITSTREAM="3f008803f004001801000020100804000060040100000021"

echo "== Netlisting tb_mosbius_ringo.sch to obtain the verified device library (mosbius, pad_model, etc.) =="
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

echo "== Extracting the reusable device library (mosbius + all child subckts) =="
# The file is: top-level testbench-specific stuff (lines before the first
# ".subckt mosbius"), then the device library, then ".GLOBAL GND" / ".end".
# Verified by inspection: library starts right after the first
# "* expanding   symbol:  mosbius.sym" comment line.
LIB_START=$(grep -n "^\* expanding   symbol:  mosbius.sym" "$SRC_NETLIST" | head -1 | cut -d: -f1)
if [ -z "$LIB_START" ]; then
  echo "ERROR: couldn't find the mosbius.sym library-expansion marker in $SRC_NETLIST -- xschem's netlist format may have changed, check manually." >&2
  exit 1
fi
tail -n "+${LIB_START}" "$SRC_NETLIST" > build/mosbius_device_library.spice

echo "== Extracting mosbius subckt's exact port list (positional -- must match exactly) =="
python3 - "$SRC_NETLIST" <<'PYEOF'
import sys
path = sys.argv[1]
lines = open(path).read().splitlines()
out = []
capture = False
for line in lines:
    if line.startswith(".subckt mosbius "):
        capture = True
        out.append(line)
        continue
    if capture:
        if line.startswith("+"):
            out.append(line)
        else:
            break
open("build/mosbius_subckt_header.txt", "w").write("\n".join(out) + "\n")
print(f"Captured {len(out)} header lines")
PYEOF

echo "== Generating the ring.sch-specific top-level testbench =="
python3 - "$RING_BITSTREAM" <<'PYEOF'
import sys
sys.path.insert(0, ".")
from mosbius.model import SwitchConfig
from mosbius.bitmap import ALL_BITS
from mosbius.spice import SINGLE_BIT_PINS

bitstream = sys.argv[1]
cfg = SwitchConfig.from_bitstream(bitstream)

# Same pin-net naming as mosbius/spice.py's render_config_spice() -- not
# reimplemented from scratch, just inlined here since we also need the
# per-bit VALUE cross-referenced against the real subckt port list below,
# which render_config_spice() doesn't expose on its own.
pin_net_to_rail = {}
for bit in range(192):
    info = ALL_BITS[bit]
    pin_net = info.pin if info.pin in SINGLE_BIT_PINS else f"{info.pin}[{info.index}]"
    pin_net_to_rail[pin_net] = "VDPWR" if bit in cfg.bits else "GND"

toks = [t for t in open("build/mosbius_subckt_header.txt").read().split()
        if t not in (".subckt", "mosbius", "+")]
assert len(toks) == 208, f"expected 208 mosbius subckt ports, found {len(toks)} -- check build/mosbius_subckt_header.txt"

config_toks = [t for t in toks if t not in ("VAPWR", "VDPWR", "VGND", "ibias")
               and not t.startswith("bus_A[") and not t.startswith("bus_B[")]
assert len(config_toks) == 192, f"expected 192 config-bit ports, found {len(config_toks)}"
missing = [t for t in config_toks if t not in pin_net_to_rail]
assert not missing, f"port list has config nets not in bitmap.py's ALL_BITS: {missing}"

# Positional call list: reuse each port's own name as our testbench net
# name (so the Rcfg ties below reference the exact same net objects),
# except the 3 power ports (renamed to match the working tb_mosbius_ringo
# convention: VGND port -> net "GND") and ibias (-> net "Ibias").
call_nets = ["GND" if t == "VGND" else ("Ibias" if t == "ibias" else t) for t in toks]

def wrap_call(nets, width=10):
    lines = ["X1 " + " ".join(nets[:width])]
    rest = nets[width:]
    while rest:
        lines.append("+ " + " ".join(rest[:width]))
        rest = rest[width:]
    lines.append("+ mosbius")
    return "\n".join(lines)

x1_call = wrap_call(call_nets)
rcfg_lines = "\n".join(f"Rcfg{i} {net} {rail} 0" for i, (net, rail) in enumerate(pin_net_to_rail.items()))

top = f"""* Level-2 testbench for examples/ringosc/ring.sch (bitstream {bitstream}).
* Generated by tools/run_ring_pad_loaded.sh -- reuses the verified device
* library from ttsky-mini-mosbius/xschem/tb_mosbius_ringo.sch's own
* netlist (mosbius, pad_model, tt_asw_3v3, etc. -- unmodified below this
* point), only this top section is new.
*
* ring.sch, per examples/ringosc/README.md: XM1->nmos_a, XM2->pmos_a,
* XM3->nmos_b, XM4->pmos_b, XM5->ndiffpair+, XM6->pdiffpair+, loop
* ua1(bus_A[1]) -> bus_A[2] -> bus_A[6]+bus_B[6] -> back to bus_A[1].
* Only bus_A[1] (=ua1) has a real package pin -- bus_A[2] and
* bus_A[6]/bus_B[6] are internal-only rows, no pad on those.
.lib /foss/pdks/sky130A/libs.tech/combined/sky130.lib.spice tt

{x1_call}

VAPWR VAPWR GND 3.3
VDPWR VDPWR GND 1.8
Ibias GND Ibias 100u

{rcfg_lines}

* The one real pad on this design's one real package pin (ua1 = bus_A[1]).
* pin=out_pad (external/probe side), mod=bus_A[1] (same net the X1 call
* above already uses for that position), VGND=GND.
Xpad_ua1 GND out_pad bus_A[1] pad_model

.nodeset v(bus_A[1])=0
.control
   save all
   set temp = 27
   tran 100p 500n UIC
   let bus_a1_alias = v(bus_A[1])
   wrdata ring_pad_loaded_out_pad.txt v(out_pad)
   wrdata ring_pad_loaded_bus_a1.txt bus_a1_alias
.endc

"""

library = open("build/mosbius_device_library.spice").read()
with open("build/ring_pad_loaded.spice", "w") as f:
    f.write(top + library)

print(f"Wrote build/ring_pad_loaded.spice ({len(top.splitlines()) + len(library.splitlines())} lines)")
PYEOF

echo "== Sanity-checking the generated netlist (structure only -- see the script's own inline notes for why ngspice itself isn't run here) =="
python3 <<'PYEOF'
path = "build/ring_pad_loaded.spice"
text = open(path).read()
n_subckt = text.count("\n.subckt ")
n_ends = text.count("\n.ends")
assert n_subckt == n_ends, f".subckt/.ends mismatch: {n_subckt} vs {n_ends}"
assert "Xpad_ua1 GND out_pad bus_A[1] pad_model" in text, "pad instance line missing"
assert text.count("\nX1 ") == 1, "expected exactly one X1 mosbius instantiation"
print(f"OK: {n_subckt} subckt/.ends pairs balanced, pad instance present, single X1 call.")
PYEOF

echo "== Copying .spiceinit alongside the netlist =="
cp .spiceinit build/.spiceinit

echo "== Running ngspice (budget ~2min+ for sky130A model load, more for the full deck -- needs a machine with real RAM headroom, see TODO.md Sec 1) =="
docker run --rm -v "$REPO_ROOT:/work" -w /work/build \
  hpretl/iic-osic-tools:latest --skip bash -lc '
    export PDK=sky130A PDK_ROOT=/foss/pdks
    ngspice -b ring_pad_loaded.spice
  '

echo "== Measuring period/frequency =="
python3 - <<'PYEOF'
import sys

def load(path):
    # Defensive: take the first two whitespace-separated fields as
    # (time, value) and ignore anything after -- see run_ringo_full_sim.sh
    # for why an exact column count is fragile here (ngspice's wrdata
    # duplicates the time column per vector if a call is ever given more
    # than one, which isn't the case in this script's own calls, but this
    # loader is copy-pasted between all three scripts so keep it robust).
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

def report(label, path):
    t, v = load(path)
    if not t:
        print(f"{label}: no data -- check ngspice output above for errors.")
        return
    steady = [(ti, vi) for ti, vi in zip(t, v) if ti > 20e-9]
    if len(steady) < 10:
        print(f"{label}: only {len(steady)} points after 20ns cutoff, widen the window or check the run completed.")
        return
    st, sv = zip(*steady)
    mid = (max(sv) + min(sv)) / 2
    ps = periods(list(st), list(sv), mid)
    if len(ps) < 3:
        print(f"{label}: only {len(ps)} period(s) found, not enough to confirm oscillation. "
              f"Range {min(sv):.3f}V to {max(sv):.3f}V. May need a longer .tran window.")
        return
    tail = ps[-min(10, len(ps)):]
    avg = sum(tail) / len(tail)
    print(f"{label}: {len(ps)} periods found, last {len(tail)} average: "
          f"{avg*1e9:.4f}ns -> {1/avg/1e6:.2f}MHz")

report("out_pad (external, pad-loaded)", "build/ring_pad_loaded_out_pad.txt")
report("bus_A[1] (internal, pre-pad)", "build/ring_pad_loaded_bus_a1.txt")
PYEOF
