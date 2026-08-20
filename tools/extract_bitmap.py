#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Regenerate mosbius/bitmap.py from the submodule and the generated netlist.

This is the M0 deliverable described in SPEC.md Sec 2.9: joining each of the
192 config-chain bits to the mosbius.sym pin it drives, and for the 162 bits
that close a switch (156 in the 26-column matrix, plus the 6 cfg_bus_pwr
rail-tap bits that live outside it), to the (crosspoint, bus, side, row) it
closes.

Ground truth, in order of authority:

1. ``ttsky-mini-mosbius/src/project.v`` -- the RTL instantiated on the taped-out
   chip. It wires every ``ctrl_out[N]`` bit directly to a named ``mosbius``
   pin index, e.g. ``.cfga_nfeta_s ({ctrl[29], ctrl[27], ..., ctrl[24]})``.
   This is a complete, unambiguous, already-fabricated answer to the Sec 2.9
   join -- no inference needed. It supersedes the web configurator's SVG,
   which SPEC.md Sec 6.1 explicitly warns is not an independent oracle.

2. ``build/mosbius.spice`` -- the netlist produced by netlisting
   ``ttsky-mini-mosbius/xschem/mosbius.sch`` (see CLAUDE.md for the docker
   command). For every switch instance it gives cfg-signal -> (crosspoint
   node, bus, row), independently confirming SPEC.md Sec 2.8.

Everything this script produces is cross-checked against SPEC.md's VERIFIED
sections (Sec 2.2 chain composition, Sec 2.3 layout column order, Sec 2.4 bit
budget, Sec 2.10 external pin map) as an integrity check on the parse itself
-- not re-derived from them.

Usage:
    python3 tools/extract_bitmap.py [--netlist build/mosbius.spice] [--write]

Without --write, prints the structural cross-validation report and exits
nonzero on any check failure. With --write, also regenerates
mosbius/bitmap.py.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SUBMODULE = REPO_ROOT / "ttsky-mini-mosbius"
PROJECT_V = SUBMODULE / "src" / "project.v"
DEFAULT_NETLIST = REPO_ROOT / "build" / "mosbius.spice"
BITMAP_OUT = REPO_ROOT / "mosbius" / "bitmap.py"


# ---------------------------------------------------------------------------
# Step 1: parse project.v -- the ctrl_out[N] -> pin[index] assignment.
# ---------------------------------------------------------------------------

@dataclass
class PinAssignment:
    pin: str            # mosbius.sym pin name, e.g. "cfga_nfeta_s"
    width: int          # bit width of the pin (1, 2, 3 or 6)
    bits: list[int]     # ctrl_out bit number for each index, index 0 = pin's bit 0
    msb_first_index: bool  # True if source lists {msb, ..., lsb} (Verilog concat convention)


def parse_project_v(path: Path) -> dict[str, PinAssignment]:
    """Parse the `.pin (...)` connections inside the `mosbius mosbius_I (...)` instance.

    project.v writes multi-bit pins as Verilog concatenations, MSB first:
        .cfga_otan_inp ({ctrl[22], ctrl[20], ctrl[18]}),   // [3:1]
    means pin bit [3]=ctrl[22], [2]=ctrl[20], [1]=ctrl[18] (concatenation is
    MSB-to-LSB by Verilog convention, and the trailing comment confirms the
    pin's own bit-range order).
    Single-bit pins appear as a bare `.pin (ctrl[N])`.
    """
    text = path.read_text()
    # Isolate the mosbius_I instantiation body.
    m = re.search(r"mosbius\s+mosbius_I\s*\((.*?)\);", text, re.S)
    if not m:
        raise ValueError(f"could not find 'mosbius mosbius_I (...)' instance in {path}")
    body = m.group(1)

    assignments: dict[str, PinAssignment] = {}

    # Multi-bit: .pin_name ({ctrl[a], ctrl[b], ...}), // [msb:lsb]
    for pm in re.finditer(
        r"\.(\w+)\s*\(\s*\{([^}]+)\}\s*\)\s*,?\s*(?://\s*\[(\d+):(\d+)\])?",
        body,
    ):
        pin, inner, msb_c, lsb_c = pm.groups()
        bit_nums = [int(x) for x in re.findall(r"ctrl\[\s*(\d+)\s*\]", inner)]
        if not bit_nums:
            continue
        width = len(bit_nums)
        # bit_nums[0] is the MSB-listed entry (Verilog {a,b,c} => a is MSB).
        # Store bits indexed by pin bit position 0..width-1 where index i
        # corresponds to pin bit i (i.e. bits[i] = ctrl bit driving pin bit i).
        # bit_nums is listed MSB..LSB, so pin bit (width-1) = bit_nums[0].
        bits = [None] * width
        for offset, ctrl_bit in enumerate(bit_nums):
            pin_bit_index = width - 1 - offset
            bits[pin_bit_index] = ctrl_bit
        assignments[pin] = PinAssignment(pin=pin, width=width, bits=bits, msb_first_index=True)

    # Single-bit: .pin_name ( ctrl[N])
    for pm in re.finditer(r"\.(\w+)\s*\(\s*ctrl\[\s*(\d+)\s*\]\s*\)", body):
        pin, ctrl_bit = pm.groups()
        if pin in assignments:
            continue
        assignments[pin] = PinAssignment(pin=pin, width=1, bits=[int(ctrl_bit)], msb_first_index=False)

    return assignments


def parse_external_pins(path: Path) -> dict[str, str]:
    """Parse `assign ua[k] = bus_X[n];` -- the external analog pin map (Sec 2.10)."""
    text = path.read_text()
    out = {}
    for pm in re.finditer(r"assign\s+ua\[(\d+)\]\s*=\s*(bus_[AB]\[\d+\]);", text):
        idx, seg = pm.groups()
        out[f"ua[{idx}]"] = seg
    return out


# ---------------------------------------------------------------------------
# Step 2: parse build/mosbius.spice -- cfg signal -> (crosspoint, bus, row).
# ---------------------------------------------------------------------------

@dataclass
class SwitchInfo:
    """The two non-rail terminals of one `tt_asw_3v3` switch instance, raw.

    The netlist line shape is uniform (SPEC.md Sec 2.8):
        x<N>[<row>] VGND VDPWR VAPWR <cfg_signal>[<row>] <terminal1> <terminal2> tt_asw_3v3
    but what <terminal1>/<terminal2> *mean* depends on the signal:
      - cfga_*/cfgb_* : terminal1 = xpt_<signal> crosspoint, terminal2 = bus_<side>[row]
      - cfg_bus_pwr   : terminal1 = bus_<side>[row] (the tapped segment), terminal2 = rail name
      - cfg_bus_short : terminal1 = bus_B[row], terminal2 = bus_A[row]
    build_bitmap() interprets these per signal; this dataclass just holds the raw parse.
    """

    terminal1: str
    terminal2: str


def parse_netlist(path: Path) -> dict[str, dict[int, SwitchInfo]]:
    """Parse tt_asw_3v3 switch instances in the top-level `mosbius` subckt."""
    text = path.read_text()
    # Only the top-level `mosbius` subckt -- stop at the first '**.ends'.
    end = text.find("**.ends")
    top = text[:end] if end != -1 else text
    signals: dict[str, dict[int, SwitchInfo]] = {}
    pattern = re.compile(
        r"^x\d+\[(\d+)\]\s+VGND\s+VDPWR\s+VAPWR\s+(\w+)\[(\d+)\]\s+(\S+)\s+(\S+)\s+tt_asw_3v3\s*$",
        re.M,
    )
    for m in pattern.finditer(top):
        _inst_row, sig, row, terminal1, terminal2 = m.groups()
        row = int(row)
        signals.setdefault(sig, {})[row] = SwitchInfo(terminal1=terminal1, terminal2=terminal2)
    return signals


# ---------------------------------------------------------------------------
# Step 3: parse asw_matrix.mag -- the 26-column physical/chain order (Sec 2.3).
# ---------------------------------------------------------------------------

def parse_layout_column_order(path: Path) -> list[str]:
    """Return the 26 column instance names in chain order (position = X / 1840)."""
    text = path.read_text()
    cols = []  # (x, name)
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"use\s+asw_col_\w+\s+(asw_col_\w+)", line)
        if not m:
            continue
        name = m.group(1)
        # transform line follows within the next couple of lines: "transform 1 0 <X> 0 1 0"
        for j in range(i + 1, min(i + 4, len(lines))):
            tm = re.match(r"transform\s+1\s+0\s+(-?\d+)\s+0\s+1\s+0", lines[j])
            if tm:
                cols.append((int(tm.group(1)), name))
                break
    cols.sort(key=lambda c: c[0])
    # Sanity: pitch is 1840 and positions are consecutive integers 0..25.
    for pos, (x, _name) in enumerate(cols):
        assert x == pos * 1840, f"unexpected column pitch at position {pos}: X={x}"
    return [name for _x, name in cols]


# ---------------------------------------------------------------------------
# Step 4: assemble the full 192-bit map and cross-validate.
# ---------------------------------------------------------------------------

# The 30 cfg signals, their side (A/B/None) and pin-array width, read directly
# off mosbius.sym / the netlist (SPEC.md Sec 2.4, Sec 2.8) -- used only to
# sanity-check the parsed data, not as an independent source of bit numbers.
EXPECTED_SIGNAL_WIDTH = {
    "cfga_otan_inp": 3, "cfgb_otan_inm": 3,
    "cfga_otan_outp": 6, "cfgb_otan_outm": 6,
    "cfga_mirn_a": 6, "cfgb_mirn_b": 6,
    "cfga_mirp_a": 6, "cfgb_mirp_b": 6,
    "cfga_dpn_inp": 3, "cfgb_dpn_inm": 3,
    "cfga_dpn_outp": 6, "cfgb_dpn_outm": 6,
    "cfga_dpp_inp": 3, "cfgb_dpp_inm": 3,
    "cfga_dpp_outp": 6, "cfgb_dpp_outm": 6,
    "cfga_nfeta_d": 6, "cfgb_nfetb_d": 6,
    "cfga_nfeta_g": 6, "cfgb_nfetb_g": 6,
    "cfga_nfeta_s": 6, "cfgb_nfetb_s": 6,
    "cfga_pfeta_d": 6, "cfgb_pfetb_d": 6,
    "cfga_pfeta_g": 6, "cfgb_pfetb_g": 6,
    "cfga_pfeta_s": 6, "cfgb_pfetb_s": 6,
    "cfg_bus_pwr": 6,
    "cfg_bus_short": 6,
}

DEVICE_SETTING_WIDTHS = {
    "ctrl_otan_tail": 2, "ctrl_otan_mode": 2,
    "ctrl_mirp_a": 2, "ctrl_mirn_a": 2, "ctrl_mirp_b": 2, "ctrl_mirn_b": 2,
    "ctrl_dpp_tail": 2, "ctrl_dpn_tail": 2,
    "ctrl_dpp_source": 1, "ctrl_dpn_source": 1,
    "ctrl_pfeta_source": 1, "ctrl_nfeta_source": 1,
    "ctrl_pfeta_width": 2, "ctrl_nfeta_width": 2,
    "ctrl_pfetb_source": 1, "ctrl_nfetb_source": 1,
    "ctrl_pfetb_width": 2, "ctrl_nfetb_width": 2,
}


@dataclass
class MatrixBit:
    bit: int
    pin: str
    index: int          # 1-based index into the pin's [N:1] array
    crosspoint: str      # None for bus_short
    bus: str             # "A", "B" or None (bus_short joins both)
    row: int
    rail: str = None     # only set for cfg_bus_pwr bits


@dataclass
class DeviceSettingBit:
    bit: int
    pin: str
    index: int  # 0-based bit position within the pin (0 for single-bit pins)


def build_bitmap(pin_assignments: dict[str, PinAssignment],
                  netlist_signals: dict[str, dict[int, SwitchInfo]],
                  external_pins: dict[str, str]):
    matrix_bits: dict[int, MatrixBit] = {}
    setting_bits: dict[int, DeviceSettingBit] = {}

    for pin, assign in pin_assignments.items():
        is_matrix = pin in EXPECTED_SIGNAL_WIDTH
        if is_matrix:
            expected_w = EXPECTED_SIGNAL_WIDTH[pin]
            if assign.width != expected_w:
                raise ValueError(f"{pin}: parsed width {assign.width} != expected {expected_w}")
            for zero_idx, ctrl_bit in enumerate(assign.bits):
                one_idx = zero_idx + 1  # pins are declared [N:1]
                if pin == "cfg_bus_short":
                    # terminal1=bus_B[row], terminal2=bus_A[row]; joins both, no crosspoint.
                    matrix_bits[ctrl_bit] = MatrixBit(
                        bit=ctrl_bit, pin=pin, index=one_idx,
                        crosspoint=None, bus=None, row=one_idx,
                    )
                elif pin == "cfg_bus_pwr":
                    # terminal1=bus_<side>[row] (the tapped segment), terminal2=rail name.
                    sw = netlist_signals[pin][one_idx]
                    seg_m = re.match(r"bus_([AB])\[(\d+)\]", sw.terminal1)
                    if not seg_m:
                        raise ValueError(f"cfg_bus_pwr[{one_idx}]: unexpected terminal {sw.terminal1!r}")
                    side, seg_row = seg_m.group(1), int(seg_m.group(2))
                    matrix_bits[ctrl_bit] = MatrixBit(
                        bit=ctrl_bit, pin=pin, index=one_idx,
                        crosspoint=None, bus=side, row=seg_row, rail=sw.terminal2,
                    )
                else:
                    side = "A" if pin.startswith("cfga_") else "B"
                    sw = netlist_signals[pin][one_idx]
                    matrix_bits[ctrl_bit] = MatrixBit(
                        bit=ctrl_bit, pin=pin, index=one_idx,
                        crosspoint=sw.terminal1, bus=side, row=one_idx,
                    )
        else:
            if pin not in DEVICE_SETTING_WIDTHS:
                raise ValueError(f"unrecognised pin in project.v: {pin}")
            expected_w = DEVICE_SETTING_WIDTHS[pin]
            if assign.width != expected_w:
                raise ValueError(f"{pin}: parsed width {assign.width} != expected {expected_w}")
            for zero_idx, ctrl_bit in enumerate(assign.bits):
                setting_bits[ctrl_bit] = DeviceSettingBit(bit=ctrl_bit, pin=pin, index=zero_idx)

    return matrix_bits, setting_bits


# ---------------------------------------------------------------------------
# Step 5: structural cross-validation (SPEC.md Sec 6.1).
# ---------------------------------------------------------------------------

def cross_validate(matrix_bits: dict[int, MatrixBit], setting_bits: dict[int, DeviceSettingBit],
                    column_order: list[str], external_pins: dict[str, str]) -> list[str]:
    errors = []

    # Total bit budget: 192 bits, each claimed exactly once.
    all_bits = set(matrix_bits) | set(setting_bits)
    if all_bits != set(range(192)):
        missing = set(range(192)) - all_bits
        extra = all_bits - set(range(192))
        if missing:
            errors.append(f"bits never claimed: {sorted(missing)}")
        if extra:
            errors.append(f"bits out of range 0..191: {sorted(extra)}")
    if len(all_bits) != len(matrix_bits) + len(setting_bits):
        errors.append("a bit was claimed by more than one pin")

    # Every one of the 30 cfg signals claimed by exactly one column base.
    # A column base is bit 6*position; a signal is "on" a column if all its
    # bits share that base (full 6-wide) or half of an ab-column (3-wide).
    signal_bits: dict[str, list[int]] = {}
    for mb in matrix_bits.values():
        signal_bits.setdefault(mb.pin, []).append(mb.bit)

    if set(signal_bits) != set(EXPECTED_SIGNAL_WIDTH):
        errors.append(f"cfg signal set mismatch: {set(signal_bits) ^ set(EXPECTED_SIGNAL_WIDTH)}")

    matrix_signals = {k: v for k, v in signal_bits.items() if k not in ("cfg_bus_short", "cfg_bus_pwr")}
    three_bit = {k for k, w in EXPECTED_SIGNAL_WIDTH.items() if w == 3}
    ab_column_bases = set()
    full_column_bases = set()
    for pos, name in enumerate(column_order):
        base = pos * 6
        if "_ab_" in name:
            ab_column_bases.add(base)
        elif "_short_" not in name:
            full_column_bases.add(base)

    for sig, bits in matrix_signals.items():
        bits = sorted(bits)
        if sig in three_bit:
            base_candidates = {b - (b % 6) if (b % 6) < 3 else b - (b % 6) for b in bits}
            # 3-bit signals occupy either the low half (offsets 0,2,4) or high
            # half (offsets 1,3,5) of an ab column's 6-bit base range.
            bases = {b - (b % 6) for b in bits}
            if len(bases) != 1:
                errors.append(f"{sig}: bits not confined to one column base: {bits}")
                continue
            base = next(iter(bases))
            if base not in ab_column_bases:
                errors.append(f"{sig}: base {base} is not an ab-column (3-bit signal must sit on an ab column)")
        else:
            bases = {b - (b % 6) for b in bits}
            if len(bases) != 1:
                errors.append(f"{sig}: bits not confined to one column base: {bits}")
                continue
            base = next(iter(bases))
            if base not in full_column_bases:
                errors.append(f"{sig}: base {base} is not a full A/B column")
            side = "A" if sig.startswith("cfga_") else "B"
            col_name = column_order[base // 6]
            expected_infix = f"_{side.lower()}_"
            if expected_infix not in col_name:
                errors.append(f"{sig} (side {side}) sits on column {col_name}, expected an '{side}'-side column")

    # Each of the 26 columns claimed by exactly one signal (or the short/pwr set).
    claimed_bases = set()
    for sig, bits in matrix_signals.items():
        for b in bits:
            claimed_bases.add(b - (b % 6))
    short_base = 0  # position 0 is asw_col_short_0 (SPEC Sec 2.3 cross-check)
    all_column_bases = ab_column_bases | full_column_bases | {short_base}
    if claimed_bases | {short_base} != all_column_bases:
        errors.append(f"column base mismatch: claimed={sorted(claimed_bases)} vs layout={sorted(all_column_bases)}")

    # cfg_bus_short must claim exactly the short column's 6 bits (0-5).
    short_bits = sorted(signal_bits.get("cfg_bus_short", []))
    if short_bits != [0, 1, 2, 3, 4, 5]:
        errors.append(f"cfg_bus_short bits {short_bits} != [0..5] (position 0 is the short column)")

    # External pin map (Sec 2.10) must match project.v's own `assign ua[k]`.
    expected_ext = {
        "ua[1]": "bus_A[1]", "ua[2]": "bus_A[3]", "ua[3]": "bus_A[5]",
        "ua[4]": "bus_B[2]", "ua[5]": "bus_B[4]",
    }
    if external_pins != expected_ext:
        errors.append(f"external pin map mismatch: {external_pins} != {expected_ext}")

    return errors


# ---------------------------------------------------------------------------
# Step 6: emit mosbius/bitmap.py
# ---------------------------------------------------------------------------

HEADER = '''# SPDX-License-Identifier: Apache-2.0
"""Generated by tools/extract_bitmap.py -- do not edit by hand.

Maps every one of the 192 mini-MOSbius config-chain bits (`ctrl_out[191:0]`,
see SPEC.md Sec 2.1-2.2) to the `mosbius.sym` pin it drives, and for the 162
bits that close a switch, to the crosspoint/bus/row it closes.

Ground truth is `ttsky-mini-mosbius/src/project.v`, the RTL wiring that was
actually taped out -- see SPEC.md Sec 2.9 and the module docstring in
tools/extract_bitmap.py for why that supersedes the web configurator's SVG.

Regenerate with:
    python3 tools/extract_bitmap.py --write
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MatrixBit:
    """One of the 162 bits that close a `tt_asw_3v3` transmission gate.

    156 of these sit in the 26-column switch matrix (chain positions 0-155)
    and connect a crosspoint node (a device terminal) to one row of one bus
    side -- for those, `crosspoint`, `bus` and `row` are all set.

    6 more are `cfg_bus_short` (positions 0-5, the matrix's own column 0:
    joins `bus_A[row]` to `bus_B[row]`, no crosspoint, `bus=None`).

    The last 6 are `cfg_bus_pwr` (positions 168-174, living inside the
    diff-pair device-setting blocks per SPEC.md Sec 2.4/2.11 -- *not* part of
    the 26-column matrix). These tie one bus segment directly to a rail:
    `crosspoint=None`, `bus` set, `rail` set to "VAPWR" or "VGND".
    """

    bit: int          # position in ctrl_out[191:0] / the 192-bit chain
    pin: str           # mosbius.sym pin name, e.g. "cfga_nfeta_s"
    index: int         # 1-based index into that pin's [N:1] array
    crosspoint: str | None  # xpt_<signal> node; None for cfg_bus_short/cfg_bus_pwr
    bus: str | None    # "A", "B", or None (cfg_bus_short joins both sides)
    row: int           # bus row 1-6
    rail: str | None = None  # "VAPWR"/"VGND" for cfg_bus_pwr bits, else None


@dataclass(frozen=True)
class DeviceSettingBit:
    """One of the 30 remaining bits: device widths, mirror ratios, diff-pair/
    OTA tails, the 4 FET source ties, the 2 diff-pair source ties, and OTA
    mode (chain positions 156-191, minus the 6 cfg_bus_pwr bits above).
    """

    bit: int    # position in ctrl_out[191:0] / the 192-bit chain
    pin: str    # mosbius.sym pin name, e.g. "ctrl_pfeta_width"
    index: int  # 0-based bit position within that pin (0 for single-bit pins)


'''


def render_bitmap_module(matrix_bits: dict[int, MatrixBit], setting_bits: dict[int, DeviceSettingBit]) -> str:
    lines = [HEADER]
    lines.append("MATRIX_BITS: dict[int, MatrixBit] = {")
    for bit in sorted(matrix_bits):
        mb = matrix_bits[bit]
        cp = f'"{mb.crosspoint}"' if mb.crosspoint else "None"
        bus = f'"{mb.bus}"' if mb.bus else "None"
        rail = f'"{mb.rail}"' if mb.rail else "None"
        lines.append(
            f'    {bit}: MatrixBit(bit={bit}, pin="{mb.pin}", index={mb.index}, '
            f"crosspoint={cp}, bus={bus}, row={mb.row}, rail={rail}),"
        )
    lines.append("}")
    lines.append("")
    lines.append("DEVICE_SETTING_BITS: dict[int, DeviceSettingBit] = {")
    for bit in sorted(setting_bits):
        sb = setting_bits[bit]
        lines.append(f'    {bit}: DeviceSettingBit(bit={bit}, pin="{sb.pin}", index={sb.index}),')
    lines.append("}")
    lines.append("")
    lines.append("# Convenience: every bit, matrix or setting, keyed 0..191.")
    lines.append("ALL_BITS: dict[int, MatrixBit | DeviceSettingBit] = {**MATRIX_BITS, **DEVICE_SETTING_BITS}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--netlist", type=Path, default=DEFAULT_NETLIST,
                     help="path to build/mosbius.spice (see CLAUDE.md for how to generate it)")
    ap.add_argument("--project-v", type=Path, default=PROJECT_V)
    ap.add_argument("--layout", type=Path, default=SUBMODULE / "mag" / "asw_matrix.mag")
    ap.add_argument("--write", action="store_true", help="write mosbius/bitmap.py")
    args = ap.parse_args()

    if not args.netlist.exists():
        print(f"error: netlist not found at {args.netlist}\n"
              f"  Generate it first (see CLAUDE.md 'Running the EDA tools').",
              file=sys.stderr)
        return 1
    if not args.project_v.exists():
        print(f"error: {args.project_v} not found -- did you run "
              f"'git submodule update --init'?", file=sys.stderr)
        return 1

    pin_assignments = parse_project_v(args.project_v)
    external_pins = parse_external_pins(args.project_v)
    netlist_signals = parse_netlist(args.netlist)
    column_order = parse_layout_column_order(args.layout)

    matrix_bits, setting_bits = build_bitmap(pin_assignments, netlist_signals, external_pins)
    errors = cross_validate(matrix_bits, setting_bits, column_order, external_pins)

    print(f"Parsed {len(pin_assignments)} pins from project.v "
          f"({len(matrix_bits)} matrix bits, {len(setting_bits)} device-setting bits).")
    print(f"Layout column order: {len(column_order)} columns.")

    if errors:
        print(f"\n{len(errors)} structural cross-validation FAILURE(S):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print("Structural cross-validation: all checks passed "
          "(30 cfg signals claimed once each, sides consistent, widths consistent, "
          "192-bit budget closes exactly).")

    if args.write:
        BITMAP_OUT.parent.mkdir(parents=True, exist_ok=True)
        BITMAP_OUT.write_text(render_bitmap_module(matrix_bits, setting_bits))
        print(f"Wrote {BITMAP_OUT}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
