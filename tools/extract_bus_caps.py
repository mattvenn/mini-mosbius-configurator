#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Measure a mini-MOSbius's bus-row capacitance from its own layout.

Every bus row in the switch matrix is a long piece of metal running the width
of the chip, and in an as-routed simulation it would otherwise be a zero-length
ideal wire. Loading it correctly is what closed the ring-oscillator
investigation on tnt's part, moving a simulated 93.5 MHz to 37.6 MHz against a
30 MHz measurement, so these are not decorative numbers.

This reads a *flat* ngspice netlist written by magic's `ext2spice`, works out
which extracted net is which bus row, and sums the capacitance on each. Run it
on both parts with the same magic settings and the two sets are comparable; run
it on one part only and you have a number whose sole meaning is "bigger than
nothing". tools/extract_bus_caps.sh does the magic half for both parts.

## Why identifying the row is the whole job

A bus row is formed by abutment across the matrix columns, so inside a column
it has no name of its own -- magic calls it something like `li_n88_4556#`.
Nothing in either layout labels the rows. Guessing from a switch's position in
its column does not work either: the switches inside a column are not in row
order, and assuming they were is how an earlier measurement of tnt's
`bus_B[2]` came to be taken on a node that was not electrically `bus_B[2]` at
all (see the comment above `_TNT_BUS_WIRE_CAP` in mosbius/chips/__init__.py).

So the rows are identified from the circuit, in four steps, each of which fails
loudly rather than quietly returning the wrong node:

1. **The twelve busiest switched nets are the twelve bus rows.** A row reaches
   one net per crosspoint; nothing else in either chip fans out like that. The
   gap below the twelfth is checked, not assumed.
2. **A package pin names its row.** The analog pins are the one thing the
   layout does label, and `Chip.pins.rows` says which row each reaches. That
   mapping is not the obvious one -- on tnt, `ua[2]` is on `bus_A[3]` and
   `ua[4]` is on the *other* bus side -- so it is read from the chip
   description rather than assumed.
3. **`cfg_bus_short[n]` names the partner.** One switch joins `bus_A[n]` to
   `bus_B[n]`, so every pin-anchored row hands over its opposite number.
4. **The rail taps name what is left.** Both parts have rows that no pin
   reaches, and the bit map says which rails each of those taps. A tap is a
   switch channel to VAPWR or VGND, which is visible in the netlist.

Then every row's switch count is checked against what the bit map predicts. The
bit map comes from the chip's own configurator geometry, never from the layout,
so agreement there is independent confirmation rather than the identification
marking its own homework.
"""

from __future__ import annotations

import argparse
import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mosbius.chips import CHIPS, Chip  # noqa: E402

# magic writes capacitor values with an ngspice SI suffix.
_SUFFIX = {"": 1.0, "a": 1e-18, "f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6}

# The pass transistors inside `tt_asw_3v3`. Every matrix connection is one of
# these, so they are the only devices that say anything about bus topology.
_PASS_FET_MODELS = ("sky130_fd_pr__nfet_g5v0d10v5", "sky130_fd_pr__pfet_g5v0d10v5")

_RAILS = ("VGND", "VAPWR", "VDPWR", "VSUBS", "0")


def parse_value(text: str) -> float | None:
    """A SPICE element value like `1.234f`, as farads."""
    m = re.fullmatch(r"([0-9.eE+-]+)([a-zA-Z]*)", text.strip())
    if not m:
        return None
    try:
        magnitude = float(m.group(1))
    except ValueError:
        return None
    scale = _SUFFIX.get(m.group(2).lower()[:1] if m.group(2) else "")
    return None if scale is None else magnitude * scale


class Netlist:
    """The switch transistors and capacitors of a flat ext2spice netlist."""

    def __init__(self, path: Path):
        self.switches: list[tuple[str, str]] = []
        self.caps: list[tuple[str, str, float]] = []
        for line in path.read_text().splitlines():
            if not line or line[0] in "*.+":
                continue
            f = line.split()
            if line[0] in "Xx" and len(f) >= 6 and f[5] in _PASS_FET_MODELS:
                self.switches.append((f[1], f[3]))  # drain, source
            elif line[0] in "Cc" and len(f) >= 4:
                value = parse_value(f[3])
                if value is not None:
                    self.caps.append((f[1], f[2], value))
        partners: dict[str, set[str]] = collections.defaultdict(set)
        for drain, source in self.switches:
            if drain != source:
                partners[drain].add(source)
                partners[source].add(drain)
        self.partners = partners

    def degree(self, net: str) -> int:
        """How many distinct nets `net` reaches through a switch channel.

        Distinct nets, not devices: magic splits one drawn transistor into many
        parallel ones, so a device count reports finger geometry rather than
        topology.
        """
        return len(self.partners.get(net, ()))

    def capacitance_on(self, net: str) -> float:
        """Total capacitance from `net` to everything else, in farads."""
        return sum(v for a, b, v in self.caps if net in (a, b) and a != b)


class RowFacts:
    """What the chip's bit map says about each bus row, before looking."""

    def __init__(self, chip: Chip):
        self.chip = chip
        self.crosspoints: collections.Counter = collections.Counter()
        self.rails: dict[tuple[str, int], collections.Counter] = (
            collections.defaultdict(collections.Counter)
        )
        for mb in chip.matrix_bits.values():
            key = (mb.bus, mb.row)
            if mb.crosspoint is not None:
                self.crosspoints[key] += 1
            if getattr(mb, "rail", None):
                self.rails[key][mb.rail] += 1
        self.all_rows = [(side, row) for side in ("A", "B") for row in range(1, 7)]
        self.row_of_pin = dict(chip.pins.rows)
        self.pin_of_row = {v: k for k, v in chip.pins.rows.items()}

    def expected_degree(self, side: str, row: int) -> int:
        """Switch channels the bit map says this row carries.

        Its crosspoints, plus the one `cfg_bus_short` joining it to the other
        side, plus any rail taps, plus -- only on the part where a package pin
        reaches its row through a switch rather than a bond wire -- that pin.
        """
        key = (side, row)
        pin_switch = 1 if key in self.pin_of_row and self.chip.pins.switched else 0
        return self.crosspoints[key] + 1 + sum(self.rails[key].values()) + pin_switch

    def rails_tapped(self, side: str, row: int) -> set[str]:
        return {r for r in ("VAPWR", "VGND") if self.rails[(side, row)][r]}


def twelve_bus_rows(net: Netlist) -> list[str]:
    """The twelve nets that are bus rows, busiest first."""
    ranked = sorted(
        ((n, len(p)) for n, p in net.partners.items() if n not in _RAILS),
        key=lambda kv: -kv[1],
    )
    if len(ranked) < 13:
        raise SystemExit("too few switched nets here for this to be a matrix")
    if ranked[11][1] <= ranked[12][1]:
        raise SystemExit(
            f"cannot separate the 12 bus rows from the rest of the chip: the "
            f"12th busiest net reaches {ranked[11][1]} others and the 13th "
            f"reaches {ranked[12][1]}, so there is no gap to cut at. Nothing "
            f"below this point would be a measurement."
        )
    return [n for n, _ in ranked[:12]]


def identify(net: Netlist, facts: RowFacts) -> dict[tuple[str, int], str]:
    """Map every (side, row) to the extracted net that is that bus row."""
    candidates = set(twelve_bus_rows(net))
    found: dict[tuple[str, int], str] = {}

    # 1. Package pins. Where the pin is bonded straight to the row, the pin's
    #    own labelled net IS the row; where a switch sits between them, the row
    #    is the one bus row on the far side of that switch.
    for pin, (side, row) in facts.row_of_pin.items():
        label = f"ua[{facts.chip.ua_index[pin]}]"
        if facts.chip.pins.switched:
            reached = [n for n in net.partners.get(label, ()) if n in candidates]
            if len(reached) != 1:
                raise SystemExit(
                    f"{pin}, labelled {label} in the layout, reaches "
                    f"{len(reached)} bus rows through a switch where exactly "
                    f"one was expected. Either the layout does not label that "
                    f"pin, or this netlist is not the part --part names."
                )
            row_net = reached[0]
        else:
            row_net = label
        if row_net not in candidates:
            raise SystemExit(
                f"{pin} lands on {row_net}, which is not one of the twelve "
                f"busiest switched nets and so is not a bus row. The "
                f"identification has gone wrong; no numbers are reported."
            )
        found[(side, row)] = row_net

    # 2. The cfg_bus_short switch is the only device with a bus row on both
    #    ends, so it hands over the opposite side of every row found above.
    for (side, row), row_net in list(found.items()):
        other = "B" if side == "A" else "A"
        joined = [n for n in net.partners[row_net] if n in candidates]
        if len(joined) != 1:
            raise SystemExit(
                f"bus_{side}[{row}] has {len(joined)} bus rows on the far end "
                f"of a switch where only its cfg_bus_short was expected."
            )
        found[(other, row)] = joined[0]

    # 3. What is left is the row on each side that no package pin reaches. The
    #    bit map says which rails each of those taps, and a tap is visible here
    #    as a switch channel to VAPWR or VGND.
    leftover = sorted(candidates - set(found.values()))
    missing = [k for k in facts.all_rows if k not in found]
    if len(leftover) != len(missing):
        raise SystemExit(
            f"{len(leftover)} nets left over for {len(missing)} unidentified "
            f"rows {missing}: {leftover}"
        )
    for key in missing:
        want = facts.rails_tapped(*key)
        fits = [
            n
            for n in leftover
            if {r for r in ("VAPWR", "VGND") if r in net.partners[n]} == want
        ]
        if len(fits) != 1:
            raise SystemExit(
                f"bus_{key[0]}[{key[1]}] taps {sorted(want) or 'no rail'} "
                f"according to the bit map, and {len(fits)} of the leftover "
                f"nets match that, so it cannot be told apart: {leftover}"
            )
        found[key] = fits[0]
        leftover.remove(fits[0])
    return found


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Sum the real capacitance on each switch-matrix bus row, "
        "from a flat magic ext2spice netlist of a whole mini-MOSbius."
    )
    ap.add_argument("netlist", type=Path, help="flat .spice written by ext2spice")
    ap.add_argument(
        "--part",
        choices=sorted(CHIPS),
        required=True,
        help="which mini-MOSbius this netlist is of",
    )
    args = ap.parse_args()

    if not args.netlist.exists():
        raise SystemExit(f"no such netlist: {args.netlist}")

    chip = CHIPS[args.part]
    net = Netlist(args.netlist)
    facts = RowFacts(chip)
    print(
        f"{args.netlist}\n{chip.title}: {len(net.switches)} switch "
        f"transistors, {len(net.caps)} capacitors"
    )

    found = identify(net, facts)

    print("\nRows, and their switch count against the bit map's prediction:")
    problems = []
    for key in facts.all_rows:
        side, row = key
        want, got = facts.expected_degree(side, row), net.degree(found[key])
        pin = facts.pin_of_row.get(key, "")
        print(
            f"  bus_{side}[{row}]  {got:3d} switches (bit map: {want:3d})  "
            f"{pin:8s}{found[key]}"
        )
        if want != got:
            problems.append(
                f"bus_{side}[{row}] carries {got} switch channels in the "
                f"layout but the bit map predicts {want}"
            )
    if problems:
        print(
            "\nThe layout and the bit map disagree, so the rows above are not "
            "identified and no capacitance is reported:",
            file=sys.stderr,
        )
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 1
    print(
        "\nAll twelve agree with the bit map, which comes from the chip's "
        "configurator geometry and not from this layout."
    )

    print("\nCapacitance per row:")
    for key in facts.all_rows:
        print(f"  bus_{key[0]}[{key[1]}]  {net.capacitance_on(found[key]) * 1e15:8.2f} fF")

    print("\nAs a Python dict, for mosbius/chips/__init__.py:")
    for key in facts.all_rows:
        farads = net.capacitance_on(found[key])
        print(f'    "bus_{key[0]}[{key[1]}]": {farads * 1e15:.2f}e-15,')
    return 0


if __name__ == "__main__":
    sys.exit(main())
