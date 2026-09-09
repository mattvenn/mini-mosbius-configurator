#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Route examples/currentsource at ratio=1,2,3,4, to answer TODO.md's open
# question: has any device-setting cycler bit ever been exercised on
# silicon? psource_a/nsink_a's ratio is the cheapest to check, because a
# ratio of two currents from the same bias reference cancels the
# demoboard's uncalibrated bias source entirely -- see
# examples/currentsource/README.md's own "Try this".
#
# The four bitstreams need no schematic edit: ratio=2 is rewritten straight
# in the netlist, the same trick tools/sweep_corners_currentsource.sh uses
# for the PDK corner, so the committed schematic -- and every number
# examples/currentsource/README.md already publishes at ratio=2 -- stays
# put.
#
# Needs build/currentsource.spice already netlisted (xschem's Netlist
# button, or in the container:
#   docker run --rm -v "$PWD:/work" -w /work hpretl/iic-osic-tools:2026.05 \
#       --skip bash -lc 'xschem -n -q examples/currentsource/currentsource.sch'
# ) and runs on the host after that -- routing is pure Python, no PDK
# needed.
#
#   sh tools/sweep_ratio_currentsource.sh
#   sh tools/sweep_ratio_currentsource.sh tt_um_mosbius
#
# Takes an optional part, default tt_um_tnt_mosbius; the four configs go to
# build/currentsource_r<n>.mosbius.json for tnt's part and
# build/currentsource_r<n>_kang.mosbius.json for tt_um_mosbius, so a sweep
# of one part never overwrites the other's.
set -e

PROJECT=${1:-tt_um_tnt_mosbius}
SUFFIX=""
[ "$PROJECT" = "tt_um_mosbius" ] && SUFFIX="_kang"

cd "$(dirname "$0")/.."

if [ ! -f build/currentsource.spice ]; then
    echo "build/currentsource.spice does not exist yet." >&2
    echo "" >&2
    echo "  Netlist it first, from the container:" >&2
    echo "    docker run --rm -v \"\$PWD:/work\" -w /work hpretl/iic-osic-tools:2026.05 \\" >&2
    echo "        --skip bash -lc 'xschem -n -q examples/currentsource/currentsource.sch'" >&2
    exit 1
fi

for n in 1 2 3 4; do
    echo "== ratio=$n, $PROJECT"
    sed "s/ratio=2/ratio=$n/g" build/currentsource.spice > "build/currentsource_r$n$SUFFIX.spice"
    python3 -m mosbius.cli route "build/currentsource_r$n$SUFFIX.spice" --project "$PROJECT" \
        --out "build/currentsource_r$n$SUFFIX.mosbius.json"
done

echo
echo "== checking the four bitstreams differ only in the ratio cycler bits"
PROJECT="$PROJECT" SUFFIX="$SUFFIX" python3 - <<'PY'
import json
import os
from mosbius.chips import chip_for_macro
from mosbius.model import SwitchConfig

project = os.environ["PROJECT"]
suffix = os.environ["SUFFIX"]
chip = chip_for_macro(project)

configs = {}
for n in (1, 2, 3, 4):
    routed = json.load(open(f"build/currentsource_r{n}{suffix}.mosbius.json"))
    settings = SwitchConfig.from_bitstream(routed["bitstream"], chip=chip).device_settings()
    configs[n] = {
        "bitstream": routed["bitstream"],
        "roles": routed["device_roles"],
        "psource_ratio": settings.mirp_a_ratio,
        "nsink_ratio": settings.mirn_a_ratio,
    }

roles = {tuple(sorted(c["roles"].items())) for c in configs.values()}
if len(roles) > 1:
    print("DEVICE ROLES MOVED BETWEEN CONFIGS -- not a clean ratio sweep:")
    for n, c in configs.items():
        print(f"  ratio={n}: {c['roles']}")
    raise SystemExit(1)

ok = True
for n, c in configs.items():
    want = (n, n)
    got = (c["psource_ratio"], c["nsink_ratio"])
    print(f"  ratio={n}: psource_a={c['psource_ratio']} nsink_a={c['nsink_ratio']} "
          f"bitstream={c['bitstream']}")
    if got != want:
        ok = False

base = configs[1]["bitstream"]
n_diff_hex = {n: sum(a != b for a, b in zip(base, configs[n]["bitstream"]))
              for n in (2, 3, 4)}
print(f"\n  hex characters differing from ratio=1: {n_diff_hex}")
print("  (nonzero and small is right -- only the two ratio cycler bit groups")
print("  should move, each inside one hex character)")

if not ok:
    raise SystemExit("a decoded ratio does not match the ratio requested -- "
                      "see the table above")
print("\n  OK -- four clean configs, one hardware slot each, ready for "
      "measure_currentsource_ad3.py --mode ratio")
PY

echo
echo "done -- build/currentsource_r1$SUFFIX..4$SUFFIX.mosbius.json"
echo "measure with, e.g.:"
echo "  python3 tools/ad3/measure_currentsource_ad3.py --mode ratio --leg source \\"
echo "      --project $PROJECT \\"
echo "      --configs build/currentsource_r1$SUFFIX.mosbius.json build/currentsource_r2$SUFFIX.mosbius.json \\"
echo "                build/currentsource_r3$SUFFIX.mosbius.json build/currentsource_r4$SUFFIX.mosbius.json"
