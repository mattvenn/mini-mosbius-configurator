#!/usr/bin/env bash
# Low-memory variant of tools/run_ringo_measured_bitstream_wire_cap.sh
# (the 37.62MHz best result), testing whether the row-coupling cap and
# the bus-wire cap were double-counting the same physical effect.
#
# The row-coupling cap (~43.19fF) was extracted from ONE column
# (asw_col_a.mag) -- a single switch's own bus stub coupling to its
# column's shared device-terminal (mod) net, applied identically to
# every one of the 150 real matrix-column switches regardless of
# open/closed state.
#
# The bus-wire cap (865fF-1.82pF) was extracted from the FULL matrix
# (asw_matrix.mag, all 26 columns) as the aggregate capacitance of an
# entire bus row. 26 columns x ~43.19fF = ~1.12pF, which lines up with
# the 865fF-1.82pF measured per row -- strongly suggesting the full-matrix
# number already includes each column's version of the same local
# coupling, summed across all 26 columns (open switches included, since
# PEX extraction is geometric, not electrical-state-dependent).
#
# So: this variant DROPS the row-coupling cap entirely (relying on the
# bus-wire cap to already cover it) AND drops every OPEN tt_asw_3v3
# instance from the netlist entirely (no transistor, no per-switch cap --
# its aggregate off-state contribution is claimed to already be in the
# bus-wire cap). Only CLOSED switches keep their real transistor model
# (needed for on-state channel resistance in the signal path). For this
# bitstream that's ~12-14 real switches instead of 188 -- small enough to
# actually run on a normal 1.9GB host, unlike every other full-matrix
# script in this investigation.
#
# If this comes out close to 37.62MHz, that's strong evidence for the
# double-counting hypothesis AND a real low-memory simulation recipe.
#
# RESULT (2026-08-22): NEGATIVE. This variant gives 63.17MHz -- not close
# to the 37.62MHz reference at all (68% higher, actually further off than
# the 67.66MHz row-coupling-only/full-matrix result from earlier in this
# investigation). The double-counting hypothesis does NOT hold: a real
# transistor's off-state electrical behaviour (junction/overlap
# capacitance, gate-dependent, per-device) is not equivalent to
# layout-extracted wire-to-substrate capacitance (a fixed geometric
# property) -- they're additive, different physical effects, not
# redundant. Dropping open switches from the netlist loses real accuracy
# no matter what capacitor tries to stand in for them, consistent with
# the much earlier flat-lumped-cap MVP finding in this same investigation.
# **Do not build a "closed switches only" simulation shortcut on this
# basis** -- keeping every switch (open or closed) as a real transistor
# is load-bearing for accuracy, not just a nice-to-have. The reusable
# outcome from this investigation instead lives in mosbius/spice.py's
# `render_bus_wire_caps()` -- a real, committed, one-time-extracted lookup
# table for the bus-wire capacitance itself, saving future testbenches
# from re-running a slow magic extraction, without claiming it can replace
# the real switch matrix.
#
# Same ngspice gotchas as every other script here: .control lines are
# 3-space indented; wrdata with >1 vector per call duplicates the time
# column (one vector per call); a bracketed net name cannot be referenced
# inside .control by ANY method -- rename at the point of use; the
# crossing-detection threshold must come from steady-state data only
# (t > 20ns), never the global min/max.
#
# Run from the repo root: tools/run_ringo_measured_bitstream_lowmem.sh
set -euo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT="$PWD"
mkdir -p build

MEASURED_BITSTREAM="380088007001000010000404250109000400000040000014"

echo "== Netlisting tb_mosbius_ringo.sch to obtain the verified device library (mosbius, pad_model, tt_asw_3v3, etc.) =="
docker run --rm -v "$REPO_ROOT:/work" -w /work/ttsky-mini-mosbius/xschem \
  hpretl/iic-osic-tools:2026.05 --skip bash -lc '
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
  echo "ERROR: couldn't find the mosbius.sym library-expansion marker in $SRC_NETLIST." >&2
  exit 1
fi
tail -n "+${LIB_START}" "$SRC_NETLIST" > build/mosbius_device_library_lowmem.spice

echo "== Filtering to CLOSED switches only (dropping every open tt_asw_3v3 instance entirely) =="
python3 - "$MEASURED_BITSTREAM" <<'PYEOF'
import sys
sys.path.insert(0, ".")
from mosbius.model import SwitchConfig
from mosbius.bitmap import ALL_BITS
from mosbius.spice import CONFIG_TIE_OHMS, SINGLE_BIT_PINS

bitstream = sys.argv[1]
cfg = SwitchConfig.from_bitstream(bitstream)

pin_net_to_rail = {}
for bit in range(192):
    info = ALL_BITS[bit]
    pin_net = info.pin if info.pin in SINGLE_BIT_PINS else f"{info.pin}[{info.index}]"
    pin_net_to_rail[pin_net] = "VDPWR" if bit in cfg.bits else "GND"

src = "build/mosbius_device_library_lowmem.spice"
text = open(src).read()
lines = text.split("\n")

out_lines = []
n_total_switches = 0
n_kept = 0
n_dropped = 0
for line in lines:
    if not line.endswith(" tt_asw_3v3"):
        out_lines.append(line)
        continue
    parts = line.split()
    if len(parts) != 8:
        # not a plain 6-arg tt_asw_3v3 call (shouldn't happen, but don't
        # silently mangle anything unexpected)
        out_lines.append(line)
        continue
    n_total_switches += 1
    name, ctrl = parts[0], parts[4]
    rail = pin_net_to_rail.get(ctrl)
    if rail is None:
        # ctrl net isn't one of the 192 config-chain pins (e.g. an
        # OTA-internal ctrl_mode/ctrl_tail wiring quirk not captured by
        # the simple per-bit map) -- don't guess, keep it as a real
        # device rather than risk dropping something load-bearing.
        out_lines.append(line)
        n_kept += 1
        continue
    if rail == "VDPWR":
        out_lines.append(line)
        n_kept += 1
    else:
        n_dropped += 1
        # drop the instance entirely -- no transistor, no lumped cap;
        # its aggregate contribution is claimed to already be in the
        # bus-wire cap added at the top level.

open(src, "w").write("\n".join(out_lines))
print(f"tt_asw_3v3 instances: {n_total_switches} total, {n_kept} kept (closed or unresolved), {n_dropped} dropped (open)")
assert n_dropped > 100, f"expected the vast majority of 188 switches to be dropped (open), only dropped {n_dropped} -- config lookup may be broken"
assert 5 <= n_kept <= 50, f"expected roughly a dozen kept (closed) switches, got {n_kept} -- investigate before trusting this run"
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
open("build/mosbius_subckt_header_lowmem.txt", "w").write("\n".join(out) + "\n")
print(f"Captured {len(out)} header lines")
PYEOF

echo "== Generating the low-memory measured-bitstream top-level testbench =="
python3 - "$MEASURED_BITSTREAM" <<'PYEOF'
import sys
sys.path.insert(0, ".")
from mosbius.model import SwitchConfig
from mosbius.bitmap import ALL_BITS
from mosbius.spice import CONFIG_TIE_OHMS, SINGLE_BIT_PINS

bitstream = sys.argv[1]
cfg = SwitchConfig.from_bitstream(bitstream)

pin_net_to_rail = {}
for bit in range(192):
    info = ALL_BITS[bit]
    pin_net = info.pin if info.pin in SINGLE_BIT_PINS else f"{info.pin}[{info.index}]"
    pin_net_to_rail[pin_net] = "VDPWR" if bit in cfg.bits else "GND"
rcfg_block = "\n".join(f"Rcfg{i} {net} {rail} {CONFIG_TIE_OHMS}" for i, (net, rail) in enumerate(pin_net_to_rail.items()))

toks = [t for t in open("build/mosbius_subckt_header_lowmem.txt").read().split()
        if t not in (".subckt", "mosbius", "+")]
assert len(toks) == 208, f"expected 208 mosbius subckt ports, found {len(toks)}"
for required in ("bus_A[1]", "bus_A[2]", "bus_A[3]", "bus_B[2]", "bus_B[3]"):
    assert required in toks, f"expected port {required} not found in subckt header"

config_toks = [t for t in toks if t not in ("VAPWR", "VDPWR", "VGND", "ibias")
               and not t.startswith("bus_A[") and not t.startswith("bus_B[")]
assert len(config_toks) == 192, f"expected 192 config-bit ports, found {len(config_toks)}"
missing = [t for t in config_toks if t not in pin_net_to_rail]
assert not missing, f"port list has config nets not in bitmap.py's ALL_BITS: {missing}"

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

top = f"""* LOW-MEMORY variant: closed switches only (real transistor model),
* every open switch dropped entirely, relying solely on the real
* bus-wire capacitance (below) to capture aggregate open-switch loading.
* No per-switch row-coupling cap in this variant -- testing whether it
* was double-counting the same effect the bus-wire cap already covers.
*
* Same measured bitstream ({bitstream}) as
* tools/run_ringo_measured_bitstream_wire_cap.sh (37.62MHz reference,
* which keeps ALL 188 switches as real transistors PLUS both caps).
.lib /foss/pdks/sky130A/libs.tech/combined/sky130.lib.spice tt

{x1_call}

VAPWR VAPWR GND 3.3
VDPWR VDPWR GND 1.8
Ibias GND Ibias 100u

{rcfg_block}
Xpad_ua1 GND ua1_pad {UA1_ALIAS} pad_model
Xpad_ua2 GND ua2_pad {UA2_ALIAS} pad_model
Xpad_ua4 GND ua4_pad {UA4_ALIAS} pad_model

* Real bus-wire capacitance (same extracted values as the 37.62MHz
* reference run) -- the only loading representing open switches in this
* variant.
Cwire_ua1net {UA1_ALIAS} GND 885.88f
Cwire_busA2 bus_A[2] GND 874.86f
Cwire_ua2net {UA2_ALIAS} GND 864.71f
Cwire_ua4net {UA4_ALIAS} GND 1819.36f
Cwire_busB3 bus_B[3] GND 908.76f

.nodeset v({UA1_ALIAS})=0
.nodeset v({UA2_ALIAS})=0
.nodeset v({UA4_ALIAS})=0
.control
   save v({UA1_ALIAS}) v({UA2_ALIAS}) v({UA4_ALIAS}) v(ua1_pad) v(ua2_pad) v(ua4_pad)
   set temp = 27
   tran 100p 500n UIC
   wrdata ringo_lowmem_ua1_pad.txt v(ua1_pad)
   wrdata ringo_lowmem_ua2_pad.txt v(ua2_pad)
   wrdata ringo_lowmem_ua4_pad.txt v(ua4_pad)
   wrdata ringo_lowmem_ua1_net.txt v({UA1_ALIAS})
   wrdata ringo_lowmem_ua2_net.txt v({UA2_ALIAS})
   wrdata ringo_lowmem_ua4_net.txt v({UA4_ALIAS})
.endc

"""

library = open("build/mosbius_device_library_lowmem.spice").read()
with open("build/ringo_lowmem.spice", "w") as f:
    f.write(top + library)

print(f"Wrote build/ringo_lowmem.spice ({len(top.splitlines()) + len(library.splitlines())} lines)")
PYEOF

echo "== Sanity-checking the generated netlist =="
python3 <<'PYEOF'
path = "build/ringo_lowmem.spice"
text = open(path).read()

n_switches = text.count(" tt_asw_3v3")
assert 5 <= n_switches <= 50, f"expected roughly a dozen kept switches, found {n_switches}"

n_ccpl = text.count("\nCcpl_")
assert n_ccpl == 0, f"expected NO row-coupling caps in this variant, found {n_ccpl}"

n_subckt = text.count("\n.subckt ")
n_ends = text.count("\n.ends")
assert n_subckt == n_ends, f".subckt/.ends mismatch: {n_subckt} vs {n_ends}"

assert text.count("\nX1 ") == 1, "expected exactly one X1 mosbius instantiation"

for pad in ("Xpad_ua1 GND ua1_pad ua1_net pad_model",
            "Xpad_ua2 GND ua2_pad ua2_net pad_model",
            "Xpad_ua4 GND ua4_pad ua4_net pad_model"):
    assert pad in text, f"pad instance line missing: {pad}"

for wire_cap in ("Cwire_ua1net ua1_net GND 885.88f",
                 "Cwire_busA2 bus_A[2] GND 874.86f",
                 "Cwire_ua2net ua2_net GND 864.71f",
                 "Cwire_ua4net ua4_net GND 1819.36f",
                 "Cwire_busB3 bus_B[3] GND 908.76f"):
    assert wire_cap in text, f"wire-cap line missing: {wire_cap}"

lines_ = text.split("\n")
ctrl_line_idx = next(i for i, l in enumerate(lines_) if l.strip() == ".control")
endc_line_idx = next(i for i, l in enumerate(lines_) if l.strip() == ".endc")
ctrl_body = "\n".join(lines_[ctrl_line_idx:endc_line_idx])
assert "[" not in ctrl_body, f"bracketed net reference found inside .control block: {ctrl_body}"

print(f"OK: {n_switches} real switch instances kept (no row-coupling caps), "
      f"{n_subckt} subckt/.ends pairs balanced, 3 pad instances present, "
      f"5 bus-wire caps present, no bracketed net in .control.")
PYEOF

echo "== Copying .spiceinit alongside the netlist =="
cp .spiceinit build/.spiceinit

echo "== Running ngspice (should be light -- ~a dozen real switches instead of 188) =="
docker run --rm -v "$REPO_ROOT:/work" -w /work/build \
  hpretl/iic-osic-tools:2026.05 --skip bash -lc '
    export PDK=sky130A PDK_ROOT=/foss/pdks
    ngspice -b ringo_lowmem.spice
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

for pin in ("ua1", "ua2", "ua4"):
    report(f"{pin}_pad (external, pad-loaded)", f"build/ringo_lowmem_{pin}_pad.txt")
    report(f"{pin}_net (internal, pre-pad)", f"build/ringo_lowmem_{pin}_net.txt")

print("Compare against: 37.62MHz (tools/run_ringo_measured_bitstream_wire_cap.sh -- "
      "same bitstream/pads/bus-wire cap, but ALL 188 switches kept as real "
      "transistors PLUS the row-coupling cap), real silicon ~30MHz.")
PYEOF
