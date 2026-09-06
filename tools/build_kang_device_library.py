#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build mosbius/data/kang_device_library.spice from Andrew Kang's netlist.

The counterpart of tools/rebuild_mosbius_device_library.sh, which builds the
same asset for tnt's part. The two libraries are deliberately the same shape,
because mosbius/simulate.py writes one kind of as-routed deck and should not
have to know which part it is describing.

Source is `ttsky25a-minimosbius/xschem/simulation/tt_um_mosbius.spice`, the
netlist of the schematic that was taped out, committed in Andrew's own repo.
So unlike tnt's library this needs no docker and no xschem: everything below
is a text transformation of a file already in the tree.

Three things this does beyond copying subcircuits out.

**It renames the bus nodes into this project's vocabulary.** Andrew's block
calls its bus rows `bus_A_int[n]` / `bus_B_int[n]` and uses the names
`bus_A[1..5]` for something else entirely -- the five package pins. tnt's
block calls the rows `bus_A[n]` / `bus_B[n]`, which is also what
mosbius/model.py, the router and every diagnostic call them. So the rows take
those names here and the package pins become `pad_ua1`..`pad_ua5`, which is
what they are: the node a bond pad attaches to. Without this, one part's
`bus_A[1]` would be a bus row and the other's a package pin, and a bus-wire
capacitor written against that name would land on the wrong node in silence.

**It exposes the rows as ports.** They are internal nodes in Andrew's
netlist, since nothing outside the block reaches them there. simulate.py
attaches per-row bus-wire capacitance from outside, so they have to be
reachable, exactly as they are on tnt's block.

**It adds the pad model.** Andrew's netlist has none, because his top level
does not instantiate one. `xschem/pad_model.sch` is byte-identical between
the two repos -- it is the Tiny Tapeout harness pad and its analog mux, not
anything either author designed -- so the cell is copied from tnt's library
rather than rebuilt, and that is an equality rather than an approximation.

**The row-coupling capacitance is his own now.** It used to be tnt's 43.19 fF
reused, on the argument that the two matrices are the same shape from the same
switch cell. Extracting both (tools/extract_bus_caps.sh) says his crosspoints
couple about 6% harder than tnt's, which is small but is a measurement rather
than an argument, and the same extraction pair moves his bus-row capacitance by
up to 25% -- see mosbius/chips/__init__.py.

Usage:
    python3 tools/build_kang_device_library.py [--check]

--check verifies the committed library matches what this would write, without
writing anything.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / "ttsky25a-minimosbius" / "xschem" / "simulation" / "tt_um_mosbius.spice"
TNT_LIBRARY = REPO_ROOT / "mosbius" / "data" / "mosbius_device_library.spice"
OUT = REPO_ROOT / "mosbius" / "data" / "kang_device_library.spice"

# One switch's own bus stub to its column's shared device-terminal net.
#
# Measured on Andrew's own layout: the median of the 137 such capacitors a
# whole-chip extraction finds is 46.16 fF against 43.74 fF for the 150 on
# tnt's, and 43.74 against tnt's published 43.19 is what says the method
# reproduces the number it is being checked on, to 1.3%. As with the bus-row
# capacitance in mosbius/chips/__init__.py, the value written here is tnt's
# published figure scaled by that ratio, so both parts sit on the one
# calibration silicon was fitted against: 43.19 * 46.16 / 43.74.
COUPLING_F = "45.58f"

# Subcircuits to carry across. Everything else in the source netlist is either
# the digital shift register (not part of the analog block a routed design
# simulates) or the top-level wrapper.
WANTED = (
    "mosbius", "tt_asw_3v3", "mirror_n", "mirror_p",
    "diff_n", "diff_p", "nmos_prog", "pmos_prog", "ota_n",
)

BUS_ROWS = [f"bus_{side}[{row}]" for side in ("A", "B") for row in range(1, 7)]


def _parse(text: str) -> dict[str, tuple[list[str], list[str]]]:
    lines = text.split("\n")
    out: dict[str, tuple[list[str], list[str]]] = {}
    i = 0
    while i < len(lines):
        if not lines[i].startswith(".subckt "):
            i += 1
            continue
        parts = lines[i].split()
        name, ports = parts[1], parts[2:]
        i += 1
        while i < len(lines) and lines[i].startswith("+"):
            ports += lines[i][1:].split()
            i += 1
        body: list[str] = []
        while i < len(lines) and not lines[i].startswith(".ends"):
            body.append(lines[i])
            i += 1
        i += 1
        out[name] = (ports, body)
    return out


def rename_bus_nodes(tokens: list[str]) -> list[str]:
    """Andrew's names -> this project's, token by token.

    Exact-token replacement rather than a text substitution, so
    `bus_A_int[1]` cannot be half-rewritten by a rule meant for `bus_A[1]`.
    """
    out = []
    for tok in tokens:
        m = re.fullmatch(r"bus_A\[(\d)\]", tok)
        if m:
            out.append(f"pad_ua{m.group(1)}")
            continue
        m = re.fullmatch(r"bus_([AB])_int\[(\d)\]", tok)
        if m:
            out.append(f"bus_{m.group(1)}[{m.group(2)}]")
            continue
        out.append(tok)
    return out


def coupling_caps(body: list[str]) -> list[str]:
    """One capacitor per real matrix-column switch: its bus stub to the
    device-terminal net its column shares. The bus-level switches -- the two
    rail columns, the row shorts, the package-pin connects -- have no
    device-terminal net behind them and get none, which is the same rule
    tnt's build applies.
    """
    caps = []
    for line in body:
        parts = line.split()
        if len(parts) != 8 or parts[-1] != "tt_asw_3v3":
            continue
        name, mod, bus = parts[0], parts[5], parts[6]
        if not mod.startswith("xpt_"):
            continue
        cname = "Ccpl_" + name.replace("[", "_").replace("]", "_").replace(".", "_")
        caps.append(f"{cname} {mod} {bus} {COUPLING_F}")
    return caps


def wrap_ports(name: str, ports: list[str], width: int = 120) -> list[str]:
    lines = [f".subckt {name}"]
    for port in ports:
        if len(lines[-1]) + 1 + len(port) > width:
            lines.append("+")
        lines[-1] += " " + port
    return lines


def pad_model_from_tnt(text: str) -> list[str]:
    subckts = _parse(text)
    if "pad_model" not in subckts:
        raise SystemExit("tnt's library has no pad_model to copy")
    ports, body = subckts["pad_model"]
    return wrap_ports("pad_model", ports) + body + [".ends", ""]


def build() -> str:
    source = SOURCE.read_text()
    subckts = _parse(source)
    missing = [n for n in WANTED if n not in subckts]
    if missing:
        raise SystemExit(f"source netlist is missing {missing}")

    out: list[str] = [
        "* Generated by tools/build_kang_device_library.py -- do not edit by hand.",
        "*",
        "* Andrew Kang's mini-MOSbius (tt_um_mosbius) as mosbius/simulate.py",
        "* needs it: the real switch matrix, the row-coupling capacitance, and",
        "* the Tiny Tapeout pad model. Source is his own committed netlist,",
        "* ttsky25a-minimosbius/xschem/simulation/tt_um_mosbius.spice.",
        "*",
        "* Two renamings from that source, so this block and tnt's speak the",
        "* same language and simulate.py needs no special cases:",
        "*   bus_A_int[n], bus_B_int[n]  ->  bus_A[n], bus_B[n]   (the bus rows)",
        "*   bus_A[1..5]                 ->  pad_ua1..pad_ua5     (the package pins)",
        "* The rows are also promoted to ports, because the bus-wire capacitance",
        "* is attached from outside this block.",
        "*",
        f"* The {COUPLING_F} row-coupling capacitors below come from this part's",
        "* own layout: a whole-chip extraction finds 137 of them with a median",
        "* of 46.16 fF, against 43.74 fF for the 150 on tnt's, whose published",
        "* figure is 43.19 fF. The value written here is that published figure",
        "* scaled by the ratio, so both parts stay on the one calibration a",
        "* silicon measurement was fitted against. tools/extract_bus_caps.sh",
        "* re-measures it; mosbius/chips/__init__.py has the reasoning.",
        "",
    ]

    ports, body = subckts["mosbius"]
    ports = rename_bus_nodes(ports) + BUS_ROWS
    body = [" ".join(rename_bus_nodes(line.split())) if line.strip() else line
            for line in body]

    caps = coupling_caps(body)
    out += wrap_ports("mosbius", ports)
    out += ["* Row-coupling caps (see tools/build_kang_device_library.py)"]
    out += caps
    out += [""]
    out += body
    out += [".ends", ""]

    out += pad_model_from_tnt(TNT_LIBRARY.read_text())

    for name in WANTED:
        if name == "mosbius":
            continue
        p, b = subckts[name]
        out += wrap_ports(name, p) + b + [".ends", ""]

    text = "\n".join(out).rstrip("\n") + "\n"
    _verify(text, len(caps))
    return text


def _verify(text: str, n_caps: int) -> None:
    """Structural checks, so a source-format change fails loudly here rather
    than as a strange simulation result later.
    """
    subckts = _parse(text)
    for name in (*WANTED, "pad_model"):
        if name not in subckts:
            raise SystemExit(f"built library is missing .subckt {name}")

    ports = subckts["mosbius"][0]
    for row in BUS_ROWS:
        if row not in ports:
            raise SystemExit(f"{row} is not a port of the built mosbius block")
    for k in range(1, 6):
        if f"pad_ua{k}" not in ports:
            raise SystemExit(f"pad_ua{k} is not a port of the built mosbius block")
    if any(re.fullmatch(r"bus_[AB]_int\[\d\]", p) for p in ports):
        raise SystemExit("an _int bus name survived into the port list")

    # Comment lines are exempt: the header above names the old nodes in order
    # to explain the renaming, and checking those would fail on its own prose.
    circuit = [l for l in text.split("\n") if not l.startswith("*")]
    if any("_int[" in l for l in circuit):
        raise SystemExit("an _int bus name survived into the circuit")

    # 144 crosspoint switches: 167 matrix bits less 6 row shorts, 12 rail
    # ties and 5 package-pin connects. Asserted rather than assumed, because
    # a miscount here is a silently wrong amount of capacitance.
    if n_caps != 144:
        raise SystemExit(f"expected 144 row-coupling caps, built {n_caps}")

    n_open = text.count("\n.subckt ")
    n_close = text.count("\n.ends")
    if n_open != n_close:
        raise SystemExit(f".subckt/.ends mismatch: {n_open} vs {n_close}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="verify the committed library matches, write nothing")
    args = ap.parse_args()

    if not SOURCE.exists():
        print(f"error: {SOURCE} not found -- did you run "
              f"'git submodule update --init'?", file=sys.stderr)
        return 1

    text = build()

    if args.check:
        if not OUT.exists():
            print(f"{OUT} does not exist", file=sys.stderr)
            return 1
        if OUT.read_text() != text:
            print(f"{OUT} differs from what this script builds", file=sys.stderr)
            return 1
        print(f"OK: {OUT} matches.")
        return 0

    OUT.write_text(text)
    print(f"Wrote {OUT}: {len(text.splitlines())} lines, "
          f"144 row-coupling caps, pad model included.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
