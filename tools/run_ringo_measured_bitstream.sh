#!/usr/bin/env bash
# The first true apples-to-apples test in this investigation against the
# real ~30MHz silicon measurement: the EXACT measured bitstream
# (380088007001000010000404250109000400000040000014, per
# examples/ringosc/README.md), not tb_mosbius_ringo.sch's own different
# baked-in config and not this project's own ring.sch. Combines the two
# techniques already proven separately:
#   - tools/run_ring_pad_loaded.sh's approach: reuse the verified device
#     library out of netlisting tb_mosbius_ringo.sch, generate a fresh
#     top-level testbench with Rcfg ties for this bitstream's own config
#     (via mosbius/spice.py's real render_config_spice()), positional X1
#     call reusing the mosbius subckt's own port names.
#   - tools/run_ringo_row_coupling.sh's approach: add the real ~43.19fF
#     coupling capacitor (each tt_asw_3v3's own `bus` terminal to its
#     column's shared `mod`/device-terminal net -- NOT row-to-row
#     adjacency, see that script's header for the full explanation) on
#     all 150 real matrix-column switches.
#
# This bitstream's topology (decoded via `mosbius.cli decode`, cross-
# checked against the raw closed SwitchConfig bits): nmos_a/pmos_a (w=4)
# + ndiffpair+/pdiffpair+ + ndiffpair-/pdiffpair- (both diff-pairs
# standalone-tied to their rails, not using the tail current sink -- see
# CLAUDE.md trap #3), looped ua[2] -> ua[1] -> ua[4] -> ua[2]. Unlike
# tb_mosbius_ringo.sch (only 1 of 3 loop nodes pinned) or ring.sch (only
# 1 of 3 pinned), ALL THREE of this bitstream's loop connections are on
# real package pins -- ua[1]=bus_A[1] directly; ua[2]=bus_A[3], shorted to
# bus_B[3] (closed bit 4, cfg_bus_short row 3) since the diffpair-'s
# drains land on the B side; ua[4]=bus_B[2] (its real bonded row), shorted
# to bus_A[2] (closed bit 2, cfg_bus_short row 2) since diffpair+'s drains
# and diffpair-'s gates land on the A side. So three real pad_model
# instances go on bus_A[1], bus_A[3], and bus_B[2] specifically -- the
# pins' own real bonded rows, not the shorted-to rows on the other side.
#
# Same ngspice gotchas as every other script here: .control lines are
# 3-space indented; wrdata with >1 vector per call duplicates the time
# column (one vector per call); a bracketed net name (bus_A[1] etc.)
# cannot be referenced inside .control by ANY method (not wrdata
# directly, not let-aliasing either -- both fail differently) -- rename
# the net itself at its point of use, don't try to alias around it; and
# the crossing-detection threshold must come from steady-state data only
# (t > 20ns), never the global min/max, which includes the 0V startup
# transient and skews the threshold low enough to silently miss real
# crossings.
#
# Same memory requirement as the other four scripts here -- likely the
# heaviest yet (full matrix + 150 coupling caps + 3 pads): needs a machine
# with more RAM than this dev host's 1.9GB. The netlisting/generation
# steps below are cheap and safe to run anywhere; only the final `ngspice`
# step needs the extra memory.
#
# Run from the repo root: tools/run_ringo_measured_bitstream.sh
set -euo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT="$PWD"
mkdir -p build

MEASURED_BITSTREAM="380088007001000010000404250109000400000040000014"

echo "== Netlisting tb_mosbius_ringo.sch to obtain the verified device library (mosbius, pad_model, tt_asw_3v3, etc.) =="
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
LIB_START=$(grep -n "^\* expanding   symbol:  mosbius.sym" "$SRC_NETLIST" | head -1 | cut -d: -f1)
if [ -z "$LIB_START" ]; then
  echo "ERROR: couldn't find the mosbius.sym library-expansion marker in $SRC_NETLIST -- xschem's netlist format may have changed, check manually." >&2
  exit 1
fi
tail -n "+${LIB_START}" "$SRC_NETLIST" > build/mosbius_device_library.spice

echo "== Adding the row-coupling caps to the device library (bus<->mod, one per real matrix-column switch) =="
python3 - <<'PYEOF'
src = "build/mosbius_device_library.spice"
text = open(src).read()
lines = text.split("\n")

COUPLING_F = "43.19f"
coupling_lines = []
n_matched = 0
for line in lines:
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

assert n_matched == 150, f"expected 150 real matrix-column switches, matched {n_matched}"

# Insert right after the ".subckt mosbius" port-list block ends (first
# line that doesn't start with "+" after the .subckt mosbius header) --
# anywhere inside the subckt body works electrically, this is just tidy.
out_lines = []
inserted = False
in_mosbius_header = False
for line in lines:
    if line.startswith(".subckt mosbius "):
        in_mosbius_header = True
        out_lines.append(line)
        continue
    if in_mosbius_header and line.startswith("+"):
        out_lines.append(line)
        continue
    if in_mosbius_header and not line.startswith("+"):
        in_mosbius_header = False
        if not inserted:
            out_lines.append("* Row-coupling caps added by tools/run_ringo_measured_bitstream.sh")
            out_lines.extend(coupling_lines)
            out_lines.append("")
            inserted = True
    out_lines.append(line)
assert inserted, "could not find end of .subckt mosbius header to insert coupling caps after"

open(src, "w").write("\n".join(out_lines))
print(f"Added {n_matched} coupling caps ({COUPLING_F} each) to {src}")
PYEOF

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

echo "== Generating the measured-bitstream top-level testbench =="
python3 - "$MEASURED_BITSTREAM" <<'PYEOF'
import sys
sys.path.insert(0, ".")
from mosbius.model import SwitchConfig
from mosbius.bitmap import ALL_BITS
from mosbius.spice import CONFIG_TIE_OHMS, SINGLE_BIT_PINS

bitstream = sys.argv[1]
cfg = SwitchConfig.from_bitstream(bitstream)

# NOT using mosbius/spice.py's render_config_spice() directly: it
# hardcodes its tie target as the literal net name "VGND", but this
# testbench's ground net is called "GND" (matching tb_mosbius_ringo.sch's
# own convention -- the X1 call below maps the VGND *port* to a "GND"
# *net*). Calling render_config_spice() as-is would tie every "open" bit
# to a phantom, disconnected "VGND" node that doesn't otherwise exist in
# this circuit -- confirmed as a real bug by first running this script
# without this fix and finding a scope test (see this session's own
# verification) that top-level SPICE elements referencing a node name
# only used elsewhere DO NOT connect to it, they silently create a new,
# separate, floating node with the same text name. Reimplemented inline
# with the correct "GND" rail instead, same as tools/run_ring_pad_loaded.sh
# already does for exactly this reason.
pin_net_to_rail = {}
for bit in range(192):
    info = ALL_BITS[bit]
    pin_net = info.pin if info.pin in SINGLE_BIT_PINS else f"{info.pin}[{info.index}]"
    pin_net_to_rail[pin_net] = "VDPWR" if bit in cfg.bits else "GND"
rcfg_block = "\n".join(f"Rcfg{i} {net} {rail} {CONFIG_TIE_OHMS}" for i, (net, rail) in enumerate(pin_net_to_rail.items()))

toks = [t for t in open("build/mosbius_subckt_header.txt").read().split()
        if t not in (".subckt", "mosbius", "+")]
assert len(toks) == 208, f"expected 208 mosbius subckt ports, found {len(toks)}"
for required in ("bus_A[1]", "bus_A[2]", "bus_A[3]", "bus_B[2]", "bus_B[3]"):
    assert required in toks, f"expected port {required} not found in subckt header"

config_toks = [t for t in toks if t not in ("VAPWR", "VDPWR", "VGND", "ibias")
               and not t.startswith("bus_A[") and not t.startswith("bus_B[")]
assert len(config_toks) == 192, f"expected 192 config-bit ports, found {len(config_toks)}"
missing = [t for t in config_toks if t not in pin_net_to_rail]
assert not missing, f"port list has config nets not in bitmap.py's ALL_BITS: {missing}"

# Positional call list: reuse each port's own name as our testbench net
# name, except the 3 power ports (VGND->GND, ibias->Ibias, matching the
# tb_mosbius_ringo.sch convention) and the THREE nets we need to measure
# with v(...) inside .control -- those get renamed to bracket-free
# aliases at their point of use (ngspice's .control expression parser
# treats [n] as vector-indexing syntax, not literal name text; confirmed
# twice elsewhere in this investigation that neither referencing the
# bracketed name directly nor `let`-aliasing it works -- only renaming
# the underlying net does). bus_A[2] and bus_B[3] (the shorted-to rows,
# not the real pin's own bonded row) are left alone -- no pad or
# measurement needed there.
UA1_ALIAS, UA2_ALIAS, UA4_ALIAS = "ua1_net", "ua2_net", "ua4_net"
RENAME = {"bus_A[1]": UA1_ALIAS, "bus_A[3]": UA2_ALIAS, "bus_B[2]": UA4_ALIAS}
call_nets = [
    "GND" if t == "VGND" else
    ("Ibias" if t == "ibias" else
     RENAME.get(t, t))
    for t in toks
]

def wrap_call(nets, width=10):
    lines = ["X1 " + " ".join(nets[:width])]
    rest = nets[width:]
    while rest:
        lines.append("+ " + " ".join(rest[:width]))
        rest = rest[width:]
    lines.append("+ mosbius")
    return "\n".join(lines)

x1_call = wrap_call(call_nets)

top = f"""* Routed-onto-the-chip testbench for the MEASURED ring-oscillator bitstream
* ({bitstream}), the exact one the user measured at ~30MHz on real
* silicon (examples/ringosc/README.md) -- NOT tb_mosbius_ringo.sch's own
* different baked-in config, NOT ring.sch. Generated by
* tools/run_ringo_measured_bitstream.sh: reuses the verified device
* library from tb_mosbius_ringo.sch's own netlist (with row-coupling caps
* already added above, in build/mosbius_device_library.spice), only this
* top section plus the caps are new relative to that library.
*
* Loop: ua[2] -> ua[1] -> ua[4] -> ua[2], ALL THREE pinned (unlike every
* other testbench tried in this investigation). ua[1]=bus_A[1] direct;
* ua[2]=bus_A[3] (shorted to bus_B[3] internally); ua[4]=bus_B[2]
* (shorted to bus_A[2] internally). Renamed to bracket-free aliases
* {UA1_ALIAS}/{UA2_ALIAS}/{UA4_ALIAS} for .control measurement -- see the
* call_nets comment above.
.lib /foss/pdks/sky130A/libs.tech/combined/sky130.lib.spice tt

{x1_call}

VAPWR VAPWR GND 3.3
VDPWR VDPWR GND 1.8
Ibias GND Ibias 100u

{rcfg_block}
* Real pad_model on each of this bitstream's three real package pins --
* the pins' own bonded rows, not the shorted-to rows on the other side.
Xpad_ua1 GND ua1_pad {UA1_ALIAS} pad_model
Xpad_ua2 GND ua2_pad {UA2_ALIAS} pad_model
Xpad_ua4 GND ua4_pad {UA4_ALIAS} pad_model

.nodeset v({UA1_ALIAS})=0
.nodeset v({UA2_ALIAS})=0
.nodeset v({UA4_ALIAS})=0
.control
   save all
   set temp = 27
   tran 100p 500n UIC
   wrdata ringo_measured_ua1_pad.txt v(ua1_pad)
   wrdata ringo_measured_ua2_pad.txt v(ua2_pad)
   wrdata ringo_measured_ua4_pad.txt v(ua4_pad)
   wrdata ringo_measured_ua1_net.txt v({UA1_ALIAS})
   wrdata ringo_measured_ua2_net.txt v({UA2_ALIAS})
   wrdata ringo_measured_ua4_net.txt v({UA4_ALIAS})
.endc

"""

library = open("build/mosbius_device_library.spice").read()
with open("build/ringo_measured_bitstream.spice", "w") as f:
    f.write(top + library)

print(f"Wrote build/ringo_measured_bitstream.spice ({len(top.splitlines()) + len(library.splitlines())} lines)")
PYEOF

echo "== Sanity-checking the generated netlist =="
python3 <<'PYEOF'
path = "build/ringo_measured_bitstream.spice"
text = open(path).read()

n_caps = text.count("\nCcpl_")
assert n_caps == 150, f"expected 150 Ccpl_ lines, found {n_caps}"

n_subckt = text.count("\n.subckt ")
n_ends = text.count("\n.ends")
assert n_subckt == n_ends, f".subckt/.ends mismatch: {n_subckt} vs {n_ends}"

assert text.count("\nX1 ") == 1, "expected exactly one X1 mosbius instantiation"

for pad in ("Xpad_ua1 GND ua1_pad ua1_net pad_model",
            "Xpad_ua2 GND ua2_pad ua2_net pad_model",
            "Xpad_ua4 GND ua4_pad ua4_net pad_model"):
    assert pad in text, f"pad instance line missing: {pad}"

# Confirm no bracketed net is referenced inside the .control block.
# Use the real directive line, not a substring search -- text.index(".control")
# can (and did, caught by actually running this) match the word ".control"
# inside a comment earlier in the file, giving a bogus ctrl_start.
lines_ = text.split("\n")
ctrl_line_idx = next(i for i, l in enumerate(lines_) if l.strip() == ".control")
endc_line_idx = next(i for i, l in enumerate(lines_) if l.strip() == ".endc")
ctrl_body = "\n".join(lines_[ctrl_line_idx:endc_line_idx])
assert "[" not in ctrl_body, f"bracketed net reference found inside .control block: {ctrl_body}"

for wr in ("wrdata ringo_measured_ua1_pad.txt v(ua1_pad)",
           "wrdata ringo_measured_ua2_pad.txt v(ua2_pad)",
           "wrdata ringo_measured_ua4_pad.txt v(ua4_pad)",
           "wrdata ringo_measured_ua1_net.txt v(ua1_net)",
           "wrdata ringo_measured_ua2_net.txt v(ua2_net)",
           "wrdata ringo_measured_ua4_net.txt v(ua4_net)"):
    assert wr in text, f"wrdata line missing: {wr}"

print(f"OK: {n_caps} coupling caps present, {n_subckt} subckt/.ends pairs balanced, "
      f"3 pad instances present, no bracketed net in .control, 6 wrdata calls present.")
PYEOF

echo "== Copying .spiceinit alongside the netlist =="
cp .spiceinit build/.spiceinit

echo "== Running ngspice (budget ~2min+ for sky130A model load, more for the full deck plus 150 caps and 3 pads -- likely the heaviest run in this investigation, needs a machine with real RAM headroom) =="
docker run --rm -v "$REPO_ROOT:/work" -w /work/build \
  hpretl/iic-osic-tools:latest --skip bash -lc '
    export PDK=sky130A PDK_ROOT=/foss/pdks
    ngspice -b ringo_measured_bitstream.spice
  '

echo "== Measuring period/frequency on all three loop nodes =="
python3 <<'PYEOF'
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

for pin, alias in (("ua1", "ua1"), ("ua2", "ua2"), ("ua4", "ua4")):
    report(f"{pin}_pad (external, pad-loaded)", f"build/ringo_measured_{alias}_pad.txt")
    report(f"{pin}_net (internal, pre-pad)", f"build/ringo_measured_{alias}_net.txt")

print("Compare against: 93.5MHz (full matrix, tb_mosbius_ringo.sch config), "
      "78.81MHz (+ row-coupling caps, same config), real silicon ~30MHz "
      "(this exact bitstream).")
PYEOF
