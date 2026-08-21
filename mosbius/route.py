# SPDX-License-Identifier: Apache-2.0
"""Route a MosbiusDesign onto the switch matrix (SPEC.md Sec 3.2, Sec 3.4).

Two decisions, in order (Sec 3.4's "spend the constrained resource
first"):

1. Device allocation: which hardware instance (nmos_a vs nmos_b vs the
   ndiffpair+/ndiffpair- halves, etc.) each generic device request becomes.
   FET pairs that already share a source net are mapped onto a diff pair
   preferentially, since that hardware is *only* useful as a shared-source
   pair -- using it for anything else wastes the one thing it's good for.

2. Net allocation: which bus row (and, if a net spans both sides, which
   cfg_bus_short row) each net lands on. Port nets (ua1..ua5) and rail
   nets get their row chosen for them by the hardware (Sec 2.10): a port
   net's row is exactly the one physically bonded to that pin, and a rail
   connection prefers a device's own free ctrl_*_source tie over spending
   a bus row at all.

All the row/bit tables below are derived from bitmap.py/model.py at
import time rather than re-transcribed, so a bit-map correction there
can't silently drift out of sync with the router.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from mosbius import bitstream
from mosbius.bitmap import MATRIX_BITS
from mosbius.model import (
    DEFAULT_IBIAS,
    DEVICE_TERMINALS,
    EXTERNAL_PINS,
    SwitchConfig,
    encode_cycler,
    setting_bit,
)
from mosbius.netlist import DeviceRequest, MosbiusDesign

SCHEMA = 1  # router version, stored in RoutedDesign for SPEC.md Sec 3.2b


class RouteError(ValueError):
    """A design cannot be routed onto the switch matrix, explained in
    SPEC.md Sec 1.1 terms: what ran out, why, what to try instead.
    """


# ---------------------------------------------------------------------------
# Hardware roles (SPEC.md Sec 2.12 device inventory).
# ---------------------------------------------------------------------------

ROLE_SIDE = {
    "nmos_a": "A", "nmos_b": "B", "ndiffpair+": "A", "ndiffpair-": "B",
    "pmos_a": "A", "pmos_b": "B", "pdiffpair+": "A", "pdiffpair-": "B",
    "nsink_a": "A", "nsink_b": "B", "psource_a": "A", "psource_b": "B",
}

NMOS_INDEPENDENT_ROLES = ("nmos_a", "nmos_b")
NMOS_PAIR_ROLES = ("ndiffpair+", "ndiffpair-")
PMOS_INDEPENDENT_ROLES = ("pmos_a", "pmos_b")
PMOS_PAIR_ROLES = ("pdiffpair+", "pdiffpair-")
NSINK_ROLES = ("nsink_a", "nsink_b")
PSOURCE_ROLES = ("psource_a", "psource_b")

# Role names as written by routers before 2026-08-21, when the diff-pair
# halves were called dpn+/dpp- and so on. Nothing about the hardware or the
# bitstream changed -- only what the tool calls them out loud -- so an old
# .mosbius.json is still perfectly reusable; it just needs its labels
# translated on the way in so the report does not print two vocabularies.
LEGACY_ROLE_NAMES = {
    "dpn+": "ndiffpair+", "dpn-": "ndiffpair-",
    "dpp+": "pdiffpair+", "dpp-": "pdiffpair-",
    "nfeta": "nmos_a", "nfetb": "nmos_b",
    "pfeta": "pmos_a", "pfetb": "pmos_b",
    "mirn_a": "nsink_a", "mirn_b": "nsink_b",
    "mirp_a": "psource_a", "mirp_b": "psource_b",
    "otan": "ota",
}

# (role -> device-setting field) for the ctrl_*_source free rail tie
# (SPEC.md Sec 2.11/2.12). The 4 independent FETs each have their own tie;
# the diff-pair halves share ONE tie per pair (ctrl_dpn_source/
# ctrl_dpp_source) that ties their common tail to its rail -- correct
# whether one half is used standalone (Traps #3) or, harmlessly, if both
# are (their pass-1 pairing only happens for a non-rail shared source, so
# this bit is never set for that case; see _allocate_fets).
SOURCE_TIE_PIN = {
    "nmos_a": "ctrl_nfeta_source", "nmos_b": "ctrl_nfetb_source",
    "pmos_a": "ctrl_pfeta_source", "pmos_b": "ctrl_pfetb_source",
    "ndiffpair+": "ctrl_dpn_source", "ndiffpair-": "ctrl_dpn_source",
    "pdiffpair+": "ctrl_dpp_source", "pdiffpair-": "ctrl_dpp_source",
}
SOURCE_TIE_RAIL = {
    "nmos_a": "VGND", "nmos_b": "VGND", "pmos_a": "VAPWR", "pmos_b": "VAPWR",
    "ndiffpair+": "VGND", "ndiffpair-": "VGND", "pdiffpair+": "VAPWR", "pdiffpair-": "VAPWR",
}

# (role -> width/ratio setting field, step) for the 4 FETs + 4 mirrors.
WIDTH_SETTING = {
    "nmos_a": ("ctrl_nfeta_width", 1), "nmos_b": ("ctrl_nfetb_width", 1),
    "pmos_a": ("ctrl_pfeta_width", 1), "pmos_b": ("ctrl_pfetb_width", 1),
    "nsink_a": ("ctrl_mirn_a", 1), "nsink_b": ("ctrl_mirn_b", 1),
    "psource_a": ("ctrl_mirp_a", 1), "psource_b": ("ctrl_mirp_b", 1),
}
DEFAULT_WIDTH = 1  # mosbius_nmos/pmos/nsink/psource's own template default

# The roles WIDTH_SETTING does *not* cover, and the width they are fixed
# at anyway. A diff-pair half has no width bits on the chip -- its
# geometry is built in silicon -- so a w= written against one is dropped,
# and it is dropped in favour of a value that is emphatically not w=1.
#
# Verified against the read-only submodule rather than taken on trust:
#
#   nmos_prog.sch  W=10 nf=2 always-on + switchable W=10 nf=2 and W=20 nf=4
#                  -> w=1 is W=10 nf=2, and its maximum w=4 is W=40 nf=8
#   diff_n.sch     M1/M2 are W=40 nf=8            -> exactly that w=4
#   pmos_prog.sch  W=30 nf=4 + W=30 nf=4 + W=60 nf=8
#                  -> w=1 is W=30 nf=4, maximum w=4 is W=120 nf=16
#   diff_p.sch     M3/M4 are W=120 nf=16          -> exactly that w=4
FIXED_WIDTH = {
    "ndiffpair+": 4, "ndiffpair-": 4,
    "pdiffpair+": 4, "pdiffpair-": 4,
}

# The sky130 geometry behind each fixed role, for diagnostics that have to
# show their working (CLAUDE.md: say why the hardware behaves that way).
FIXED_GEOMETRY = {
    "ndiffpair+": "W=40 nf=8 (diff_n.sch M1/M2)",
    "ndiffpair-": "W=40 nf=8 (diff_n.sch M1/M2)",
    "pdiffpair+": "W=120 nf=16 (diff_p.sch M3/M4)",
    "pdiffpair-": "W=120 nf=16 (diff_p.sch M3/M4)",
}

# Which schematic property a kind's width comes from, so a report can echo
# the word the user actually typed rather than normalising it to "w".
WIDTH_PROPERTY = {
    "nmos": "w", "pmos": "w", "nsink": "ratio", "psource": "ratio",
}


@dataclass(frozen=True)
class DeviceWidth:
    """What width a device ended up with, versus what the schematic asked
    for (TODO.md Sec 5). `requested` is None when the symbol carries no
    width property at all (mosbius_ota); `effective` is None when the role
    has neither width bits nor a known fixed geometry.
    """

    prop: str                  # "w" or "ratio" -- the schematic's own word
    requested: int | None      # what the netlist said, None if unset
    effective: int | None      # what the chip will actually build
    programmable: bool         # False when the role's geometry is fixed

    @property
    def dropped(self) -> bool:
        """A width was asked for, cannot be programmed, and differs from
        what the hardware is fixed at -- i.e. something was really lost.
        Asking for exactly the fixed width loses nothing and is silent.
        """
        return (
            not self.programmable
            and self.requested is not None
            and self.requested != self.effective
        )


def device_width(dev: DeviceRequest, role: str) -> DeviceWidth:
    """The width story for one allocated device."""
    # `or` rather than an explicit None test, to keep the exact fallback
    # order the bit-emission loop below has always used.
    requested = dev.properties.get("w") or dev.properties.get("ratio")
    prop = WIDTH_PROPERTY.get(dev.kind, "w")
    if role in WIDTH_SETTING:
        return DeviceWidth(prop, requested, requested or DEFAULT_WIDTH, True)
    return DeviceWidth(prop, requested, FIXED_WIDTH.get(role), False)


def device_widths(design: MosbiusDesign, roles: dict[str, str]) -> dict[str, DeviceWidth]:
    """The width story for every device, keyed by instance name."""
    by_name = {d.name: d for d in design.devices}
    return {name: device_width(by_name[name], role) for name, role in roles.items()}

# Pin name for a (role, terminal): matches xpt_<suffix> crosspoints
# (model.DEVICE_TERMINALS) with the side-appropriate cfga_/cfgb_ prefix --
# this is exactly the naming SPEC.md Sec 2.8 confirms holds everywhere.
def _pin_name(role: str, terminal: str) -> str:
    crosspoint = DEVICE_TERMINALS[role][terminal]
    prefix = "cfga_" if ROLE_SIDE[role] == "A" else "cfgb_"
    return prefix + crosspoint.removeprefix("xpt_")


# bit for (pin, row), for every matrix signal that has a crosspoint
# (i.e. every ordinary cfga_*/cfgb_* switch -- excludes cfg_bus_short and
# cfg_bus_pwr, handled separately below since they have no crosspoint).
_MATRIX_BIT_BY_PIN_ROW: dict[tuple[str, int], int] = {
    (mb.pin, mb.row): bit for bit, mb in MATRIX_BITS.items() if mb.crosspoint is not None
}

# bit for cfg_bus_short[row].
_BUS_SHORT_BIT_BY_ROW: dict[int, int] = {
    mb.row: bit for bit, mb in MATRIX_BITS.items() if mb.pin == "cfg_bus_short"
}

# (side, row) -> (bit, rail) for cfg_bus_pwr taps (SPEC.md Sec 2.7).
_PWR_TAP_BY_SIDE_ROW: dict[tuple[str, int], tuple[int, str]] = {
    (mb.bus, mb.row): (bit, mb.rail) for bit, mb in MATRIX_BITS.items() if mb.pin == "cfg_bus_pwr"
}

# "uaN" (route.py/netlist.py's port-net naming, SPEC.md Sec 3.1b) -> (side, row).
PORT_ROW: dict[str, tuple[str, int]] = {
    pin.replace("ua[", "ua").rstrip("]"): (side, row)
    for pin, (side, row) in EXTERNAL_PINS.items()
}

# Every (side, row) that's either port-pinned or rail-tappable, i.e. NOT
# free for an ordinary internal net without side effects (SPEC.md Sec
# 2.10: the pinned and rail-tappable sets are disjoint and exhaustive
# apart from one row). Internal nets must avoid the pinned set entirely
# (a permanent bond wire, not a switch -- using it always leaks the net
# to that pin) but MAY use a tappable row, as long as its pwr-tap bit is
# simply left open.
_PINNED_ROWS: set[tuple[str, int]] = set(PORT_ROW.values())
_TAPPABLE_ROWS: set[tuple[str, int]] = set(_PWR_TAP_BY_SIDE_ROW)
ALL_ROWS: set[tuple[str, int]] = {(side, row) for side in ("A", "B") for row in range(1, 7)}
_FREE_ROWS: set[tuple[str, int]] = ALL_ROWS - _PINNED_ROWS  # tappable + the one unencumbered row


@dataclass
class RoutedDesign:
    """The result of routing: the SwitchConfig, plus a human-readable
    route table (SPEC.md Sec 3.6: "record the route table, not just hex").
    """

    config: SwitchConfig
    device_roles: dict[str, str] = field(default_factory=dict)   # device name -> role
    net_rows: dict[str, dict[str, int]] = field(default_factory=dict)  # net -> {side: row}
    schema: int = SCHEMA
    # Not persisted: a pure function of (design, device_roles), so the
    # sticky path recomputes it rather than growing the file's schema.
    device_widths: dict[str, DeviceWidth] = field(default_factory=dict)


def format_device_roles(routed) -> list[str]:
    """The route table: which hardware each device became, and the width
    it will actually be built at (TODO.md Sec 5 -- reporting the width the
    router really programmed, not the one the schematic asked for).
    """
    lines = []
    for name, role in sorted(routed.device_roles.items()):
        width = routed.device_widths.get(name)
        note = ""
        if width is not None and width.effective is not None:
            note = f"  {width.prop}={width.effective}"
            if not width.programmable:
                note += " (fixed)"
        lines.append(f"  {name:<12} -> {role:<12}{note}")
    return lines


# ---------------------------------------------------------------------------
# Step 1: device allocation.
# ---------------------------------------------------------------------------

def _allocate_fets(
    requests: list[DeviceRequest], pair_roles: tuple[str, str], independent_roles: tuple[str, str],
    pair_rail: str, label: str,
) -> dict[str, str]:
    """Assign each FET request to nmos_a/nmos_b/ndiffpair+/ndiffpair- (or the PMOS
    equivalents). Two cases can use the diff-pair role for free:

    - Two devices that share a genuine *internal* (non-rail) source net:
      that net can only otherwise be realised by spending a bus row to
      physically tie two independent FETs' sources together, so the diff
      pair (whose two halves already share their source, for nothing) is
      strictly better. This is SPEC.md Sec 3.4's "spend the constrained
      resource first".
    - A device whose source is exactly the diff pair's own tail rail
      (VGND for NMOS, VAPWR for PMOS) can use a pair role *standalone*:
      CLAUDE.md's Traps #3 -- "with the tail tied to a rail each [half] is
      an ordinary common-source FET". Since ctrl_dpn_source/ctrl_dpp_source
      ties the *whole* shared tail to that one rail regardless of how many
      halves are in use, any number of such devices (up to 2) can each
      take a half, independently of whether they share a net object.

    Independent slots (nmos_a/nmos_b) are tried first since they place no
    restriction on the source net at all.
    """
    by_source: dict[str, list[DeviceRequest]] = {}
    for d in requests:
        by_source.setdefault(d.terminals["s"], []).append(d)

    roles: dict[str, str] = {}
    remaining_pair = list(pair_roles)
    remaining_indep = list(independent_roles)
    unassigned: list[DeviceRequest] = list(requests)

    # Pass 1: exact-2 groups sharing a non-rail source -- the only case
    # that *needs* the pair role rather than merely being allowed to use it.
    for src, group in by_source.items():
        if src != pair_rail and len(group) == 2 and remaining_pair:
            roles[group[0].name] = remaining_pair.pop(0)
            roles[group[1].name] = remaining_pair.pop(0)
            unassigned.remove(group[0])
            unassigned.remove(group[1])

    # Pass 2: independent slots, cheapest and most flexible, for whatever
    # is left (in netlist order, for determinism).
    still_unassigned: list[DeviceRequest] = []
    for d in unassigned:
        if remaining_indep:
            roles[d.name] = remaining_indep.pop(0)
        else:
            still_unassigned.append(d)

    # Pass 3: leftover devices whose source is the pair's own tail rail
    # can take a pair-role slot standalone.
    final_unassigned: list[DeviceRequest] = []
    for d in still_unassigned:
        if d.terminals["s"] == pair_rail and remaining_pair:
            roles[d.name] = remaining_pair.pop(0)
        else:
            final_unassigned.append(d)

    if final_unassigned:
        placed = ", ".join(f"{n} -> {r}" for n, r in roles.items())
        names = ", ".join(d.name for d in requests)
        raise RouteError(
            f"DOESN'T FIT -- not enough {label} with independent sources\n\n"
            f"  Your circuit needs {len(requests)} {label} transistors:\n"
            f"    {names}\n\n"
            f"  The chip has only {len(independent_roles)} of those whose source you can\n"
            f"  route wherever you like:\n"
            f"    {', '.join(independent_roles)}\n\n"
            f"  There are {len(pair_roles)} more, but they are the two halves of a\n"
            f"  differential pair and share one source between them:\n"
            f"    {', '.join(pair_roles)}\n"
            f"  So they suit two transistors that want a common source, or a\n"
            f"  single transistor if that shared source is tied to {pair_rail}.\n\n"
            f"  Currently placed: {placed if placed else '(none)'}.\n"
            f"  Couldn't place: {', '.join(d.name for d in final_unassigned)}.\n\n"
            f"  Ideas:\n"
            f"    - If two of these could share a source, they'd fit the pair.\n"
            f"    - A programmable current sink/source (mosbius_nsink/psource) can\n"
            f"      often replace a source-degenerated transistor."
        )

    return roles


def allocate_devices(design: MosbiusDesign) -> dict[str, str]:
    """Map each device request's name to a specific hardware role."""
    roles: dict[str, str] = {}

    nmos = [d for d in design.devices if d.kind == "nmos"]
    pmos = [d for d in design.devices if d.kind == "pmos"]
    nsink = [d for d in design.devices if d.kind == "nsink"]
    psource = [d for d in design.devices if d.kind == "psource"]
    ota = [d for d in design.devices if d.kind == "ota"]

    roles.update(_allocate_fets(nmos, NMOS_PAIR_ROLES, NMOS_INDEPENDENT_ROLES, "VGND", "NMOS"))
    roles.update(_allocate_fets(pmos, PMOS_PAIR_ROLES, PMOS_INDEPENDENT_ROLES, "VAPWR", "PMOS"))

    if len(nsink) > len(NSINK_ROLES):
        raise RouteError(
            f"DOESN'T FIT -- too many current sinks\n\n"
            f"  {len(nsink)} mosbius_nsink devices requested, but the chip has only "
            f"{len(NSINK_ROLES)}\n  (nsink_a, nsink_b)."
        )
    for d, role in zip(nsink, NSINK_ROLES):
        roles[d.name] = role

    if len(psource) > len(PSOURCE_ROLES):
        raise RouteError(
            f"DOESN'T FIT -- too many current sources\n\n"
            f"  {len(psource)} mosbius_psource devices requested, but the chip has "
            f"only {len(PSOURCE_ROLES)}\n  (psource_a, psource_b)."
        )
    for d, role in zip(psource, PSOURCE_ROLES):
        roles[d.name] = role

    if len(ota) > 1:
        raise RouteError(
            f"DOESN'T FIT -- only one OTA on this chip\n\n"
            f"  {len(ota)} mosbius_ota devices requested, but there's exactly one "
            f"(ota)."
        )
    for d in ota:
        roles[d.name] = "ota"

    return roles


# ---------------------------------------------------------------------------
# Step 2: net allocation (SPEC.md Sec 3.2) + Step 3: bit emission.
# ---------------------------------------------------------------------------

@dataclass
class _Touch:
    device: str
    role: str
    terminal: str
    side: str
    pin: str


def _apply_free_source_ties(design: MosbiusDesign, roles: dict[str, str]) -> tuple[set[int], set[tuple[str, str]]]:
    """Close every ctrl_*_source bit whose device's own "s" net is exactly
    that role's tail rail (SPEC.md Sec 3.2: "cheaper -- no bus consumed").
    Applies uniformly to independent FETs (their own source) and diff-pair
    halves used standalone (their shared tail, CLAUDE.md Traps #3) --
    return which (device, terminal) pairs were handled this way, so net
    collection skips them instead of also bus-routing the same source.
    """
    bits: set[int] = set()
    handled: set[tuple[str, str]] = set()
    for d in design.devices:
        role = roles[d.name]
        if role not in SOURCE_TIE_PIN or "s" not in d.terminals:
            continue
        if d.terminals["s"] == SOURCE_TIE_RAIL[role]:
            bits.add(setting_bit(SOURCE_TIE_PIN[role]))
            handled.add((d.name, "s"))
    return bits, handled


def _collect_touches(
    design: MosbiusDesign, roles: dict[str, str], handled: set[tuple[str, str]],
) -> dict[str, list[_Touch]]:
    by_net: dict[str, list[_Touch]] = {}
    for d in design.devices:
        role = roles[d.name]
        for terminal, net in d.terminals.items():
            if terminal not in DEVICE_TERMINALS[role]:
                continue  # e.g. a diff-pair half's generic "s" pin: no matrix terminal exists
            if (d.name, terminal) in handled:
                continue  # already tied to its rail for free -- see _apply_free_source_ties
            by_net.setdefault(net, []).append(
                _Touch(device=d.name, role=role, terminal=terminal,
                       side=ROLE_SIDE[role], pin=_pin_name(role, terminal))
            )
    return by_net


def route(design: MosbiusDesign) -> RoutedDesign:
    """Route `design` onto the switch matrix and return the resulting
    SwitchConfig plus a human-readable route table.
    """
    roles = allocate_devices(design)
    tie_bits, tied_terminals = _apply_free_source_ties(design, roles)
    touches_by_net = _collect_touches(design, roles, tied_terminals)

    bits: set[int] = set(tie_bits)
    net_rows: dict[str, dict[str, int]] = {}
    row_owner: dict[tuple[str, int], str] = {}   # (side, row) -> net claiming it

    def claim_row(side: str, row: int, net: str) -> None:
        key = (side, row)
        owner = row_owner.get(key)
        if owner is not None and owner != net:
            raise RouteError(
                f"DOESN'T FIT -- bus_{side}[{row}] is needed by both "
                f"'{net}' and '{owner}'\n\n"
                f"  Only one net can occupy a bus row at a time. Try moving one "
                f"of these\n  nets' devices to the other side of the chip, if the "
                f"device allocation allows it."
            )
        row_owner[key] = net

    def pick_free_row(side: str, net: str) -> int:
        candidates = sorted(
            row for (s, row) in _FREE_ROWS
            if s == side and row_owner.get((s, row)) in (None, net)
        )
        if not candidates:
            raise RouteError(
                f"DOESN'T FIT -- no free bus_{side}[] row left for '{net}'\n\n"
                f"  All 6 rows on side {side} are already claimed by other nets, "
                f"ports\n  or rail taps. Try routing this net through the other "
                f"side, or freeing\n  up a row by sharing it with a net that's "
                f"already there."
            )
        return candidates[0]

    def route_touches_on_row(touches: list[_Touch], side: str, row: int, net: str) -> None:
        """Close each touch's own crosspoint switch onto (side,row); for
        touches on the opposite side, first bridge with cfg_bus_short[row]
        (SPEC.md Sec 3.2: joining sides costs one bus_short row)."""
        opposite = "B" if side == "A" else "A"
        needs_short = any(t.side == opposite for t in touches)
        if needs_short:
            claim_row(opposite, row, net)
            bits.add(_BUS_SHORT_BIT_BY_ROW[row])
            net_rows.setdefault(net, {})[opposite] = row
        for t in touches:
            bits.add(_MATRIX_BIT_BY_PIN_ROW[(t.pin, row)])
        net_rows.setdefault(net, {})[side] = row

    # -- Rail nets (VAPWR/VGND): terminals with a free ctrl_*_source tie
    # were already handled and excluded before touches reached here (see
    # _apply_free_source_ties) -- SPEC.md Sec 3.2 "cheaper -- no bus
    # consumed". Whatever's left (mirror/OTA terminals, which have no
    # source tie at all) needs an ordinary bus row + cfg_bus_pwr tap.
    def route_rail_net(net: str, rail: str, touches: list[_Touch]) -> None:
        remaining = touches
        if not remaining:
            return
        side = remaining[0].side
        tappable = sorted(row for (s, row) in _TAPPABLE_ROWS if s == side
                           and _PWR_TAP_BY_SIDE_ROW[(s, row)][1] == rail
                           and row_owner.get((s, row)) in (None, net))
        if not tappable:
            raise RouteError(
                f"DOESN'T FIT -- no {rail} tap left on side {side} for '{net}'\n\n"
                f"  {rail} can only be reached from specific bus rows "
                f"(SPEC.md Sec 2.7),\n  and they're all claimed. If the device "
                f"has a source terminal, tying it\n  directly to {rail} costs no "
                f"bus row at all."
            )
        row = tappable[0]
        claim_row(side, row, net)
        bit, _ = _PWR_TAP_BY_SIDE_ROW[(side, row)]
        bits.add(bit)
        route_touches_on_row(remaining, side, row, net)

    def route_port_net(net: str, touches: list[_Touch]) -> None:
        side, row = PORT_ROW[net]
        claim_row(side, row, net)
        route_touches_on_row(touches, side, row, net)

    def route_internal_net(net: str, touches: list[_Touch]) -> None:
        sides_needed = {t.side for t in touches}
        if len(sides_needed) == 1:
            side = next(iter(sides_needed))
            row = pick_free_row(side, net)
            claim_row(side, row, net)
            route_touches_on_row(touches, side, row, net)
            return
        # Spans both sides: need a free row on each side, joined by the
        # matching cfg_bus_short. Try every free A-row/B-row pair rather
        # than assuming row numbers line up between the two sides.
        a_rows = sorted(r for (s, r) in _FREE_ROWS if s == "A" and row_owner.get((s, r)) in (None, net))
        b_rows = sorted(r for (s, r) in _FREE_ROWS if s == "B" and row_owner.get((s, r)) in (None, net))
        for row in sorted(set(a_rows) & set(b_rows)):
            claim_row("A", row, net)
            claim_row("B", row, net)
            bits.add(_BUS_SHORT_BIT_BY_ROW[row])
            for t in touches:
                bits.add(_MATRIX_BIT_BY_PIN_ROW[(t.pin, row)])
            net_rows[net] = {"A": row, "B": row}
            return
        raise RouteError(
            f"DOESN'T FIT -- '{net}' needs a free row on both sides, joined\n\n"
            f"  This net connects devices on both side A and side B, which needs "
            f"a\n  matching free row on each side plus a cfg_bus_short. No such "
            f"pair is\n  available -- every free row on at least one side is "
            f"already claimed."
        )

    for net in sorted(touches_by_net):
        touches = touches_by_net[net]
        if net == "VDPWR":
            raise RouteError(
                f"DOESN'T FIT -- VDPWR isn't reachable through the switch matrix\n\n"
                f"  VDPWR (1.8V) only powers the switches' own level-shifters "
                f"internally\n  -- no cfg_bus_pwr tap or source tie reaches it "
                f"(SPEC.md Sec 2.7 only\n  lists VAPWR/VGND taps). Route this "
                f"signal through VAPWR or VGND\n  instead, or reconsider whether "
                f"this net needs an explicit connection."
            )
        if net in ("VAPWR", "VGND"):
            route_rail_net(net, net, touches)
        elif net in PORT_ROW:
            route_port_net(net, touches)
        else:
            route_internal_net(net, touches)

    # -- Device settings: width/ratio for every allocated FET and mirror.
    # Driven off the same device_width() the route table reports from, so
    # the width shown and the width programmed cannot drift apart -- which
    # is the failure TODO.md Sec 5 is about in the first place.
    widths = device_widths(design, roles)
    for dev_name, role in roles.items():
        if role in WIDTH_SETTING:
            pin, step = WIDTH_SETTING[role]
            lsb, msb = encode_cycler(widths[dev_name].effective, step)
            if lsb:
                bits.add(setting_bit(pin, 0))
            if msb:
                bits.add(setting_bit(pin, 1))

    return RoutedDesign(
        config=SwitchConfig(bits=frozenset(bits)),
        device_roles=roles,
        net_rows=net_rows,
        device_widths=widths,
    )


# ---------------------------------------------------------------------------
# Sticky routing (SPEC.md Sec 3.2b, Sec 3.6): a design's routing is part of
# the design, not a fresh computation every run.
#
# What's implemented: an unchanged design's stored routing is reused
# byte-for-byte verbatim, no re-solve at all. What's NOT implemented yet:
# Sec 3.2b's fuller ideal for a *changed* design -- re-routing minimally,
# keeping every assignment that's still valid and only re-placing what
# actually moved. A changed design currently gets a full fresh route()
# instead. That's a real gap against the spec (an edit to one net could
# relocate unrelated nets' rows, which Sec 3.2b explicitly calls out as
# harmful for analog parasitics) -- flagged here rather than silently
# passed off as done.
# ---------------------------------------------------------------------------

def design_topology_hash(design: MosbiusDesign) -> str:
    """A hash over device kinds/properties/terminal-net-connectivity.

    Independent of *instance* names (device.name never appears below) and
    netlist line order, so re-netlisting the same schematic hashes the
    same even if xschem reorders instances or renumbers them.

    NOT independent of net *labels*: two designs that are electrically
    identical but use different wire-label text (including on a purely
    internal/floating net, e.g. an unused body pin auto-named "net1" vs
    "netA") hash differently and are treated as "changed". Re-netlisting
    the same unedited schematic file names nets deterministically, so
    this doesn't misfire on the SPEC.md Sec 3.2b "did I actually edit
    anything" case that matters in practice -- but a user renaming a wire
    label by hand, without touching connectivity, will trigger an
    unnecessary re-route. Fixing this needs real graph-isomorphism
    canonicalisation (net identity from which terminals touch it, not its
    string name), not implemented here.
    """
    canonical = sorted(
        (d.kind, tuple(sorted(d.terminals.items())), tuple(sorted(d.properties.items())))
        for d in design.devices
    )
    return hashlib.sha256(repr(canonical).encode()).hexdigest()[:16]


def save_routed_design(routed: RoutedDesign, design: MosbiusDesign, path: Path) -> None:
    """Persist a routing (SPEC.md Sec 3.6: the committed, human-readable
    config file -- route table, not just hex).
    """
    data = {
        "schema": routed.schema,
        "topology_hash": design_topology_hash(design),
        "bitstream": routed.config.to_bitstream(),
        "ibias": routed.config.ibias,
        "device_roles": routed.device_roles,
        "net_rows": routed.net_rows,
    }
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def load_routed_design(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def route_sticky(design: MosbiusDesign, config_path: Path, *, force: bool = False) -> RoutedDesign:
    """Route `design`, reusing the routing stored at `config_path` verbatim
    if the design's topology hasn't changed since it was written.
    `force=True` (SPEC.md Sec 3.2b's `--reroute`) always re-solves.
    """
    topology = design_topology_hash(design)
    if not force:
        stored = load_routed_design(config_path)
        if stored is not None and stored.get("topology_hash") == topology:
            roles = {
                dev: LEGACY_ROLE_NAMES.get(role, role)
                for dev, role in stored["device_roles"].items()
            }
            return RoutedDesign(
                config=SwitchConfig(
                    bits=bitstream.unpack(stored["bitstream"]),
                    ibias=stored.get("ibias", DEFAULT_IBIAS),
                ),
                device_roles=roles,
                net_rows=stored["net_rows"],
                schema=stored.get("schema", SCHEMA),
                # Safe to recompute rather than read back: the topology
                # hash covers device properties, so a stored routing only
                # matches a design whose w=/ratio= are unchanged too.
                device_widths=device_widths(design, roles),
            )

    routed = route(design)
    save_routed_design(routed, design, config_path)
    return routed
