#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Regenerate mosbius/chips/kang_bits.py from Andrew Kang's own netlist.

This is the counterpart of tools/extract_bitmap.py, which does the same job
for tnt's part. The two parts are joined to the rest of the toolchain by
mosbius/chips/__init__.py.

Ground truth is one file, committed in Andrew's repo and pinned here as the
`ttsky25a-minimosbius` submodule:

    xschem/simulation/tt_um_mosbius.spice

It is the netlist of the schematic that was taped out, and it answers both
halves of the question on its own:

1. **Which bit drives which pin.** `.subckt mosbius <ports...>` gives the
   block's port order, and the `x2 ... mosbius` instance line inside
   `.subckt tt_um_mosbius` gives what each of those ports is wired to, in the
   same order. Zip them and every config port names the `reg[N]` that drives
   it. Nothing has to be inferred, in the same way tnt's `project.v` needs
   nothing inferred -- it is just a netlist here rather than RTL.

2. **What closing that bit does.** Every switch in the matrix appears as a
   `tt_asw_3v3` instance inside `.subckt mosbius`, carrying its control
   signal, the node it switches, and the bus row it switches onto.

The shift direction is read off `shift_reg_len8` in the same file: `dat`
feeds `reg[0]` and propagates upward, so the bit shifted in first ends at
`reg[195]`. That is MSB first, the same convention as tnt's part.

Four structural differences from tnt's chip fall out of the parse, and the
cross-checks below assert each one rather than assuming it:

- 196 chain bits, not 192.
- Package pins reach the bus through `cfg_bus_ext` switches rather than bond
  wires, so a pin costs a bit and an unused pin is genuinely disconnected.
- Rails reach the bus through two full matrix columns, `cfga_vapwr` and
  `cfga_vgnd`, rather than six fixed taps.
- The OTA has one output, so 27 crosspoints rather than 28.

Usage:
    python3 tools/extract_bitmap_kang.py [--write]

Without --write, prints the cross-validation report and exits nonzero on any
check failure.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SUBMODULE = REPO_ROOT / "ttsky25a-minimosbius"
NETLIST = SUBMODULE / "xschem" / "simulation" / "tt_um_mosbius.spice"
BITMAP_OUT = REPO_ROOT / "mosbius" / "chips" / "kang_bits.py"

NUM_BITS = 196

# Every config port of `mosbius.sym`, and how wide it is. Transcribed from the
# symbol so the parse has something independent to fail against: a port that
# turns up with the wrong number of bits means the netlist and this list
# disagree, and one of them is wrong.
EXPECTED_WIDTH = {
    # switch-matrix columns
    "cfga_nfeta_d": 6, "cfga_nfeta_g": 6, "cfga_nfeta_s": 6,
    "cfgb_nfetb_d": 6, "cfgb_nfetb_g": 6, "cfgb_nfetb_s": 6,
    "cfga_pfeta_d": 6, "cfga_pfeta_g": 6, "cfga_pfeta_s": 6,
    "cfgb_pfetb_d": 6, "cfgb_pfetb_g": 6, "cfgb_pfetb_s": 6,
    "cfga_dpn_outp": 6, "cfgb_dpn_outm": 6,
    "cfga_dpp_outp": 6, "cfgb_dpp_outm": 6,
    "cfga_mirn_a": 6, "cfgb_mirn_b": 6,
    "cfga_mirp_a": 6, "cfgb_mirp_b": 6,
    "cfga_otan_out": 6,
    "cfga_dpn_inp": 3, "cfgb_dpn_inm": 3,
    "cfga_dpp_inp": 3, "cfgb_dpp_inm": 3,
    "cfga_otan_inp": 3, "cfgb_otan_inm": 3,
    # bus-level columns
    "cfga_vapwr": 6, "cfga_vgnd": 6,
    "cfg_bus_short": 6, "cfg_bus_ext": 5,
    # device settings
    "ctrl_nfeta_width": 2, "ctrl_nfetb_width": 2,
    "ctrl_pfeta_width": 2, "ctrl_pfetb_width": 2,
    "ctrl_mirn_a": 2, "ctrl_mirn_b": 2,
    "ctrl_mirp_a": 2, "ctrl_mirp_b": 2,
    "ctrl_dpn_tail": 2, "ctrl_dpp_tail": 2, "ctrl_otan_tail": 2,
    "ctrl_nfeta_source": 1, "ctrl_nfetb_source": 1,
    "ctrl_pfeta_source": 1, "ctrl_pfetb_source": 1,
    "ctrl_dpn_source": 1, "ctrl_dpp_source": 1,
    "ctrl_otan_diode": 1,
}

SINGLE_BIT_PORTS = {p for p, w in EXPECTED_WIDTH.items() if w == 1}

# The wrapper's own analog pin assignment, from src/project.v:
#   .bus1(ua[0]) .bus2(ua[1]) .bus3(ua[2]) .bus4(ua[3]) .bus5(ua[4])
#   .ibias(ua[5])
# So Andrew's part puts the bias reference on ua[5] and the five matrix pins
# on ua[0]..ua[4] -- the opposite way round from tnt's, which is CLAUDE.md
# trap 1 all over again and the reason this is written down rather than
# assumed.
BUS_PORT_TO_UA = {f"bus{n}": n - 1 for n in range(1, 6)}
IBIAS_UA = 5


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _subckt_body(text: str, name: str) -> tuple[list[str], str]:
    """Return (`port list`, `body text`) for one `.subckt`.

    Continuation lines start with `+`, which is how a port list of nearly two
    hundred names is written.
    """
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if not line.startswith(f".subckt {name} "):
            continue
        ports = line.split()[2:]
        j = i + 1
        while j < len(lines) and lines[j].startswith("+"):
            ports += lines[j][1:].split()
            j += 1
        end = j
        while end < len(lines) and not lines[end].startswith(".ends"):
            end += 1
        return ports, "\n".join(lines[j:end])
    raise ValueError(f"no .subckt {name} in the netlist")


def _instance_connections(body: str, subckt: str) -> list[str]:
    """The connection list of the single instance of `subckt` in `body`."""
    lines = body.split("\n")
    for i, line in enumerate(lines):
        if not re.match(r"^x\S*\s", line):
            continue
        conns = line.split()[1:]
        j = i + 1
        while j < len(lines) and lines[j].startswith("+"):
            conns += lines[j][1:].split()
            j += 1
        if conns and conns[-1] == subckt:
            return conns[:-1]
    raise ValueError(f"no instance of {subckt} found")


def parse_bit_for_port(text: str) -> dict[str, int]:
    """`"cfga_nfeta_d[3]"` -> the chain bit that drives it.

    Positional: the block's port order zipped against what the wrapper wired
    to each port.
    """
    ports, _ = _subckt_body(text, "mosbius")
    _, top_body = _subckt_body(text, "tt_um_mosbius")
    conns = _instance_connections(top_body, "mosbius")
    if len(ports) != len(conns):
        raise ValueError(
            f"the mosbius block has {len(ports)} ports but the wrapper wires "
            f"{len(conns)} nets to it -- the netlist is not self-consistent"
        )
    out: dict[str, int] = {}
    for port, net in zip(ports, conns):
        m = re.fullmatch(r"reg\[(\d+)\]", net)
        if m:
            out[port] = int(m.group(1))
    return out


def parse_switches(text: str) -> dict[str, tuple[str, str]]:
    """`"cfga_nfeta_d[3]"` -> (`switched node`, `bus node`).

    Every matrix switch is a `tt_asw_3v3` instance whose connection order is
    VGND VDPWR VAPWR ctrl mod bus.
    """
    _, body = _subckt_body(text, "mosbius")
    out: dict[str, tuple[str, str]] = {}
    for line in body.split("\n"):
        parts = line.split()
        if len(parts) != 8 or parts[-1] != "tt_asw_3v3":
            continue
        _inst, _gnd, _dpwr, _apwr, ctrl, mod, bus = parts[:7]
        out[ctrl] = (mod, bus)
    return out


# ---------------------------------------------------------------------------
# Building the table
# ---------------------------------------------------------------------------

class Bit:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def build_bitmap(bit_for_port: dict[str, int], switches: dict[str, tuple[str, str]]):
    matrix: dict[int, Bit] = {}
    settings: dict[int, Bit] = {}

    for port, bit in bit_for_port.items():
        m = re.fullmatch(r"(\w+)\[(\d+)\]", port)
        name, index = (m.group(1), int(m.group(2))) if m else (port, 0)
        if name not in EXPECTED_WIDTH:
            raise ValueError(f"{port} is not a config port this script knows about")

        if port not in switches:
            settings[bit] = Bit(bit=bit, pin=name, index=index)
            continue

        mod, bus = switches[port]
        row_m = re.fullmatch(r"bus_([AB])_int\[(\d+)\]", bus)
        if not row_m:
            raise ValueError(f"{port} switches onto {bus}, which is not a bus row")
        side, row = row_m.group(1), int(row_m.group(2))

        if name == "cfg_bus_short":
            # Joins the two sides of one row: no crosspoint, no single side.
            matrix[bit] = Bit(bit=bit, pin=name, index=index, crosspoint=None,
                              bus=None, row=row, rail=None, pin_net=None)
        elif mod in ("VAPWR", "VGND"):
            matrix[bit] = Bit(bit=bit, pin=name, index=index, crosspoint=None,
                              bus=side, row=row, rail=mod, pin_net=None)
        elif name == "cfg_bus_ext":
            pin_m = re.fullmatch(r"bus_([AB])\[(\d+)\]", mod)
            if not pin_m:
                raise ValueError(f"{port} connects {mod}, which is not a package pin")
            ua = BUS_PORT_TO_UA[f"bus{pin_m.group(2)}"]
            matrix[bit] = Bit(bit=bit, pin=name, index=index, crosspoint=None,
                              bus=side, row=row, rail=None, pin_net=f"ua{ua}")
        else:
            matrix[bit] = Bit(bit=bit, pin=name, index=index, crosspoint=mod,
                              bus=side, row=row, rail=None, pin_net=None)

    return matrix, settings


def cross_validate(matrix: dict[int, Bit], settings: dict[int, Bit]) -> list[str]:
    errors = []

    claimed = set(matrix) | set(settings)
    if claimed != set(range(NUM_BITS)):
        missing = sorted(set(range(NUM_BITS)) - claimed)
        extra = sorted(claimed - set(range(NUM_BITS)))
        errors.append(f"chain budget doesn't close: missing {missing}, extra {extra}")
    if set(matrix) & set(settings):
        errors.append(f"bits claimed twice: {sorted(set(matrix) & set(settings))}")

    seen: dict[str, set[int]] = {}
    for b in list(matrix.values()) + list(settings.values()):
        seen.setdefault(b.pin, set()).add(b.index)
    for pin, want in EXPECTED_WIDTH.items():
        got = seen.get(pin)
        if got is None:
            errors.append(f"{pin} never appears in the netlist")
            continue
        expect = {0} if pin in SINGLE_BIT_PORTS else set(range(1, want + 1))
        # The device-setting cyclers index from 0, the matrix columns from 1.
        if pin.startswith("ctrl_") and want == 2:
            expect = {0, 1}
        if got != expect:
            errors.append(f"{pin} has indices {sorted(got)}, expected {sorted(expect)}")

    crosspoints = {b.crosspoint for b in matrix.values() if b.crosspoint}
    if len(crosspoints) != 27:
        errors.append(f"{len(crosspoints)} crosspoints, expected 27 "
                      f"(one OTA output, not two)")

    # Both rails reach all six A-side rows, so a (side, row) key collides
    # between VAPWR and VGND: count the ties, and check each rail separately.
    rails = [(b.rail, b.bus, b.row) for b in matrix.values() if b.rail]
    if len(rails) != 12:
        errors.append(f"{len(rails)} rail ties, expected 12 (both rails, all six A rows)")
    for rail in ("VAPWR", "VGND"):
        rows = sorted(row for r, side, row in rails if r == rail and side == "A")
        if rows != [1, 2, 3, 4, 5, 6]:
            errors.append(f"{rail} reaches A rows {rows}, expected all six")
    if any(side != "A" for _rail, side, _row in rails):
        errors.append("a rail tie landed on side B; Andrew's are all on side A")

    pins = {b.pin_net: (b.bus, b.row) for b in matrix.values() if b.pin_net}
    want_pins = {f"ua{k}": ("A", k + 1) for k in range(5)}
    if pins != want_pins:
        errors.append(f"package pins came out {pins}, expected {want_pins}")

    for b in matrix.values():
        if b.crosspoint and not b.crosspoint.startswith("xpt_"):
            errors.append(f"bit {b.bit} switches {b.crosspoint}, not a crosspoint")

    return errors


# ---------------------------------------------------------------------------
# Emitting
# ---------------------------------------------------------------------------

HEADER = '''# SPDX-License-Identifier: Apache-2.0
"""Generated by tools/extract_bitmap_kang.py -- do not edit by hand.

Maps every one of the 196 config-chain bits of Andrew Kang's mini-MOSbius
(`tt_um_mosbius`) to the `mosbius.sym` pin it drives, and for the 167 bits
that close a switch, to what closing it connects.

Ground truth is `ttsky25a-minimosbius/xschem/simulation/tt_um_mosbius.spice`,
the netlist of the schematic that was taped out. The same design is on four
shuttles -- ttsky25a, ttsky25b, ttsky26a and ttsky26b -- from two repos whose
schematics are byte-identical, so this one table covers all four.

tnt's part has its own table next door in `tnt_bits.py`. The two are joined
to everything else by `mosbius/chips/__init__.py`.

Regenerate with:
    python3 tools/extract_bitmap_kang.py --write
"""

from __future__ import annotations

from mosbius.chips.bits import DeviceSettingBit, MatrixBit

NUM_BITS = 196

'''


def render(matrix: dict[int, Bit], settings: dict[int, Bit]) -> str:
    lines = [HEADER, "MATRIX_BITS: dict[int, MatrixBit] = {"]
    for bit in sorted(matrix):
        b = matrix[bit]
        def q(v):
            return f'"{v}"' if v else "None"
        lines.append(
            f'    {bit}: MatrixBit(bit={bit}, pin="{b.pin}", index={b.index}, '
            f"crosspoint={q(b.crosspoint)}, bus={q(b.bus)}, row={b.row}, "
            f"rail={q(b.rail)}, pin_net={q(b.pin_net)}),"
        )
    lines += ["}", "", "DEVICE_SETTING_BITS: dict[int, DeviceSettingBit] = {"]
    for bit in sorted(settings):
        b = settings[bit]
        lines.append(
            f'    {bit}: DeviceSettingBit(bit={bit}, pin="{b.pin}", index={b.index}),'
        )
    lines += ["}", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--netlist", type=Path, default=NETLIST)
    ap.add_argument("--write", action="store_true",
                    help="write mosbius/chips/kang_bits.py")
    args = ap.parse_args()

    if not args.netlist.exists():
        print(f"error: {args.netlist} not found -- did you run "
              f"'git submodule update --init'?", file=sys.stderr)
        return 1

    text = args.netlist.read_text()
    bit_for_port = parse_bit_for_port(text)
    switches = parse_switches(text)
    matrix, settings = build_bitmap(bit_for_port, switches)
    errors = cross_validate(matrix, settings)

    print(f"Parsed {len(bit_for_port)} config ports and {len(switches)} switches "
          f"({len(matrix)} matrix bits, {len(settings)} device-setting bits).")

    if errors:
        print(f"\n{len(errors)} cross-validation FAILURE(S):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print("Cross-validation: all checks passed (196-bit budget closes exactly, "
          "every port the expected width, 27 crosspoints, 12 rail ties, "
          "5 package pins on A rows 1-5).")

    if args.write:
        BITMAP_OUT.write_text(render(matrix, settings))
        print(f"Wrote {BITMAP_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
