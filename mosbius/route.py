# SPDX-License-Identifier: Apache-2.0
"""Route a MosbiusDesign onto the switch matrix (SPEC.md Sec 3.2, Sec 3.4).

Two decisions, in order (Sec 3.4's "spend the constrained resource
first"):

1. Device allocation: which hardware instance (nfeta vs nfetb vs the
   dpn+/dpn- diff-pair halves, etc.) each generic device request becomes.
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

from dataclasses import dataclass, field

from mosbius.bitmap import MATRIX_BITS
from mosbius.model import (
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
    "nfeta": "A", "nfetb": "B", "dpn+": "A", "dpn-": "B",
    "pfeta": "A", "pfetb": "B", "dpp+": "A", "dpp-": "B",
    "mirn_a": "A", "mirn_b": "B", "mirp_a": "A", "mirp_b": "B",
}

NMOS_INDEPENDENT_ROLES = ("nfeta", "nfetb")
NMOS_PAIR_ROLES = ("dpn+", "dpn-")
PMOS_INDEPENDENT_ROLES = ("pfeta", "pfetb")
PMOS_PAIR_ROLES = ("dpp+", "dpp-")
NSINK_ROLES = ("mirn_a", "mirn_b")
PSOURCE_ROLES = ("mirp_a", "mirp_b")

# (role -> device-setting field) for the ctrl_*_source free rail tie
# (SPEC.md Sec 2.11/2.12). The 4 independent FETs each have their own tie;
# the diff-pair halves share ONE tie per pair (ctrl_dpn_source/
# ctrl_dpp_source) that ties their common tail to its rail -- correct
# whether one half is used standalone (Traps #3) or, harmlessly, if both
# are (their pass-1 pairing only happens for a non-rail shared source, so
# this bit is never set for that case; see _allocate_fets).
SOURCE_TIE_PIN = {
    "nfeta": "ctrl_nfeta_source", "nfetb": "ctrl_nfetb_source",
    "pfeta": "ctrl_pfeta_source", "pfetb": "ctrl_pfetb_source",
    "dpn+": "ctrl_dpn_source", "dpn-": "ctrl_dpn_source",
    "dpp+": "ctrl_dpp_source", "dpp-": "ctrl_dpp_source",
}
SOURCE_TIE_RAIL = {
    "nfeta": "VGND", "nfetb": "VGND", "pfeta": "VAPWR", "pfetb": "VAPWR",
    "dpn+": "VGND", "dpn-": "VGND", "dpp+": "VAPWR", "dpp-": "VAPWR",
}

# (role -> width/ratio setting field, step) for the 4 FETs + 4 mirrors.
WIDTH_SETTING = {
    "nfeta": ("ctrl_nfeta_width", 1), "nfetb": ("ctrl_nfetb_width", 1),
    "pfeta": ("ctrl_pfeta_width", 1), "pfetb": ("ctrl_pfetb_width", 1),
    "mirn_a": ("ctrl_mirn_a", 1), "mirn_b": ("ctrl_mirn_b", 1),
    "mirp_a": ("ctrl_mirp_a", 1), "mirp_b": ("ctrl_mirp_b", 1),
}
DEFAULT_WIDTH = 1  # mosbius_nmos/pmos/nsink/psource's own template default

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


# ---------------------------------------------------------------------------
# Step 1: device allocation.
# ---------------------------------------------------------------------------

def _allocate_fets(
    requests: list[DeviceRequest], pair_roles: tuple[str, str], independent_roles: tuple[str, str],
    pair_rail: str, label: str,
) -> dict[str, str]:
    """Assign each FET request to nfeta/nfetb/dpn+/dpn- (or the PMOS
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

    Independent slots (nfeta/nfetb) are tried first since they place no
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
            f"  Your circuit needs {len(requests)} {label} transistors ({names}),\n"
            f"  but the chip has only {len(independent_roles)} with a source you can\n"
            f"  route anywhere ({', '.join(independent_roles)}), plus "
            f"{len(pair_roles)} diff-pair\n"
            f"  halves ({', '.join(pair_roles)}) that are only usable by two "
            f"transistors\n"
            f"  sharing a source, or standalone if tied to {pair_rail}.\n\n"
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
            f"{len(NSINK_ROLES)}\n  (mirn_a, mirn_b)."
        )
    for d, role in zip(nsink, NSINK_ROLES):
        roles[d.name] = role

    if len(psource) > len(PSOURCE_ROLES):
        raise RouteError(
            f"DOESN'T FIT -- too many current sources\n\n"
            f"  {len(psource)} mosbius_psource devices requested, but the chip has "
            f"only {len(PSOURCE_ROLES)}\n  (mirp_a, mirp_b)."
        )
    for d, role in zip(psource, PSOURCE_ROLES):
        roles[d.name] = role

    if len(ota) > 1:
        raise RouteError(
            f"DOESN'T FIT -- only one OTA on this chip\n\n"
            f"  {len(ota)} mosbius_ota devices requested, but there's exactly one "
            f"(otan)."
        )
    for d in ota:
        roles[d.name] = "otan"

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
    for dev_name, role in roles.items():
        if role in WIDTH_SETTING:
            pin, step = WIDTH_SETTING[role]
            dev = next(d for d in design.devices if d.name == dev_name)
            w = dev.properties.get("w") or dev.properties.get("ratio") or DEFAULT_WIDTH
            lsb, msb = encode_cycler(w, step)
            if lsb:
                bits.add(setting_bit(pin, 0))
            if msb:
                bits.add(setting_bit(pin, 1))

    return RoutedDesign(
        config=SwitchConfig(bits=frozenset(bits)),
        device_roles=roles,
        net_rows=net_rows,
    )
