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

# Which cfga_/cfgb_ switch pin each device terminal is wired to, and which
# bus side that puts it on. Both are *derived* from bitmap.py rather than
# transcribed, for the reason this module's docstring gives: a bit-map
# correction there must not silently drift out of sync with the router.
#
# Side is a property of the terminal, not of the device. Eleven of the
# twelve FET/mirror roles sit wholly on one side, but the OTA straddles
# both -- inp/outp on side A, inm/outm on side B -- so no single value
# could ever describe it. Asking for a *role's* side is what used to raise
# KeyError('ota') the moment anyone routed one, until 2026-08-21.
def _derive_terminal_tables() -> tuple[dict[tuple[str, str], str], dict[tuple[str, str], str]]:
    by_crosspoint: dict[str, tuple[str, str]] = {}
    for mb in MATRIX_BITS.values():
        if mb.crosspoint is None:
            continue  # cfg_bus_short/cfg_bus_pwr: no device terminal behind them
        known = by_crosspoint.setdefault(mb.crosspoint, (mb.pin, mb.bus))
        if known != (mb.pin, mb.bus):
            raise AssertionError(
                f"{mb.crosspoint} is reached by two different switch pins, "
                f"{known} and {(mb.pin, mb.bus)} -- bitmap.py disagrees with itself"
            )

    pins: dict[tuple[str, str], str] = {}
    sides: dict[tuple[str, str], str] = {}
    for role, terminals in DEVICE_TERMINALS.items():
        for terminal, crosspoint in terminals.items():
            pin, side = by_crosspoint[crosspoint]
            pins[(role, terminal)] = pin
            sides[(role, terminal)] = side
    return pins, sides


TERMINAL_PIN, TERMINAL_SIDE = _derive_terminal_tables()

# The word a beginner would use for each terminal: the schematic says "g",
# a diagnostic should say "gate" (CLAUDE.md: spell it out, and match the
# vocabulary the user already has).
TERMINAL_WORD = {
    "g": "gate", "d": "drain", "s": "source", "out": "output",
    "inp": "+ input", "inm": "- input", "outp": "+ output", "outm": "- output",
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

# (role -> tail-current setting field, step) for the devices whose tail
# current a schematic can actually set. The cycler takes 2/4/6/8 rather
# than 1..4 -- step=2 (SPEC.md Sec 2.11).
#
# The OTA carries its own tail= property (mosbius_ota.sym, template=
# "name=X1 tail=2 ..."). Until 2026-08-21 the router read only w= and
# ratio=, so writing tail=4 changed the netlist and changed no bit at all
# -- masked by the coincidence that an all-zero cycler decodes to
# step*(1+0) = 2, exactly the symbol's own default, so the one value
# anybody tries first was accidentally right.
#
# "ntail"/"ptail" are the drawn tail-bank roles (TODO.md Sec 2, closed
# 2026-08-22): a mosbius_ntail/mosbius_ptail instance's own tail=, not
# either FET half's -- the tail belongs to the pair as a whole, and these
# are the one device each polarity has that represents it.
TAIL_SETTING = {
    "ota": ("ctrl_otan_tail", 2),
    "ntail": ("ctrl_dpn_tail", 2),
    "ptail": ("ctrl_dpp_tail", 2),
}
DEFAULT_TAIL = 2  # mosbius_ota.sym's own template default

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
    for. `requested` is None when the symbol carries no
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


@dataclass(frozen=True)
class DeviceTail:
    """What tail current a device ended up with, versus what the schematic
    asked for -- the same shape as DeviceWidth, for the same reason: a
    property that cannot reach the bitstream has to be said out loud.

    `requested` is None when the symbol carries no tail property at all
    (every symbol except mosbius_ota/mosbius_ntail/mosbius_ptail);
    `effective` is None when the role has no tail current in the first
    place (a single FET, a mirror leg).
    """

    requested: int | None      # what the netlist said, None if unset
    effective: int | None      # what the chip will actually be set to
    programmable: bool         # False when no bit can carry it

    @property
    def dropped(self) -> bool:
        """A tail was asked for, cannot be programmed, and differs from
        what the hardware will do anyway.
        """
        return (
            not self.programmable
            and self.requested is not None
            and self.requested != self.effective
        )


def device_tail(dev: DeviceRequest, role: str) -> DeviceTail:
    """The tail-current story for one allocated device."""
    requested = dev.properties.get("tail")
    if role in TAIL_SETTING:
        return DeviceTail(requested, requested or DEFAULT_TAIL, True)
    return DeviceTail(requested, None, False)


def device_tails(design: MosbiusDesign, roles: dict[str, str]) -> dict[str, DeviceTail]:
    """The tail-current story for every device, keyed by instance name."""
    by_name = {d.name: d for d in design.devices}
    return {name: device_tail(by_name[name], role) for name, role in roles.items()}


def _encode_setting(value: int, step: int, *, device: str, prop: str) -> tuple[int, int]:
    """encode_cycler, with the ValueError turned into a routing failure
    that names the device and says what it could have been instead.

    A cycler is two bits, so a setting is one of exactly four values
    (SPEC.md Sec 2.11) -- there is no rounding to a nearest legal one,
    because silently building a different transistor than the schematic
    draws is the failure mode this whole file is trying to avoid.
    """
    try:
        return encode_cycler(value, step)
    except ValueError:
        valid = list(range(1, 5)) if step == 1 else list(range(2, 9, 2))
        options = ", ".join(str(v) for v in valid[:-1]) + f" or {valid[-1]}"
        raise RouteError(
            f"DOESN'T FIT -- {device}'s {prop}={value} is not a setting this "
            f"chip has\n\n"
            f"  {prop}= is stored as a 2-bit cycler: n = {step} * (1 + b_lsb + "
            f"2*b_msb)\n  (SPEC.md Sec 2.11). That gives exactly four settings, "
            f"{options},\n  and nothing in between.\n\n"
            f"  Nothing is rounded to the nearest one on your behalf: the chip "
            f"would\n  then be built to a different {prop} than your schematic "
            f"shows, which is\n  the kind of silent difference this tool exists "
            f"to prevent.\n\n"
            f"  To fix: set {prop}= to one of {options} on {device} in the "
            f"schematic,\n  and press Netlist again."
        ) from None


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

ALL_SIX_ROWS = frozenset(range(1, 7))

# The rows an internal net spanning *both* sides can ever use: free of a
# ua[] bond wire on side A and on side B at once. Derived, because which
# rows those are is a consequence of the pin map (SPEC.md Sec 2.10) rather
# than an independent fact -- today it comes out as row 6 alone.
ROWS_FREE_ON_BOTH_SIDES: frozenset[int] = frozenset(
    row for row in ALL_SIX_ROWS
    if ("A", row) in _FREE_ROWS and ("B", row) in _FREE_ROWS
)


def _derive_rows_by_pin() -> dict[str, frozenset[int]]:
    rows: dict[str, set[int]] = {}
    for pin, row in _MATRIX_BIT_BY_PIN_ROW:
        rows.setdefault(pin, set()).add(row)
    return {pin: frozenset(r) for pin, r in rows.items()}


# Which bus rows each switch pin can reach at all. Most crosspoints have a
# switch to all six rows; the differential-pair and OTA *inputs* have
# switches to rows 1-3 only (SPEC.md Sec 2.12, CLAUDE.md trap 6). Derived
# from the bit map, so this is the hardware talking, not a transcription.
_ROWS_BY_PIN: dict[str, frozenset[int]] = _derive_rows_by_pin()


def rows_reachable(pin: str) -> frozenset[int]:
    """The bus rows `pin`'s crosspoint has a switch to."""
    return _ROWS_BY_PIN.get(pin, frozenset())


def _fmt_rows(rows) -> str:
    rows = sorted(rows)
    if not rows:
        return "no row at all"
    if len(rows) == 1:
        return f"row {rows[0]}"
    return "rows " + ", ".join(str(r) for r in rows[:-1]) + f" and {rows[-1]}"


def _describe_touch(t: "_Touch") -> str:
    """A device terminal in the words the user drew it in: instance name,
    the terminal's ordinary name, and the hardware slot it was allocated
    to (CLAUDE.md: translate the chip's own identifiers before printing).
    """
    return f"{t.device}'s {TERMINAL_WORD.get(t.terminal, t.terminal)} ({t.role}.{t.terminal})"


def _reach_lines(touches: list["_Touch"]) -> str:
    lines = []
    for t in sorted(touches, key=lambda t: (t.device, t.terminal)):
        rows = rows_reachable(t.pin)
        reach = "all six rows" if rows == ALL_SIX_ROWS else f"only bus {_fmt_rows(rows)}"
        lines.append(f"    {_describe_touch(t)} -- reaches {reach}")
    return "\n".join(lines)


# Why a terminal might reach fewer than six rows. Repeated in every
# reach-related message, because it is the fact that makes the failure
# make sense and the reader may be meeting it for the first time.
_WHY_LIMITED_REACH = (
    "  Why some terminals reach fewer rows than others: the differential\n"
    "  pair's and the OTA's *input* crosspoints have a switch to three bus\n"
    "  rows only, not to all six (SPEC.md Sec 2.12). Every other terminal on\n"
    "  the chip reaches all six.\n"
)


def _shared_reach(touches: list["_Touch"]) -> frozenset[int]:
    """The rows every one of these terminals can reach."""
    shared = ALL_SIX_ROWS
    for t in touches:
        shared &= rows_reachable(t.pin)
    return frozenset(shared)


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
    # sticky path recomputes them rather than growing the file's schema.
    device_widths: dict[str, DeviceWidth] = field(default_factory=dict)
    device_tails: dict[str, DeviceTail] = field(default_factory=dict)


def format_device_roles(routed) -> list[str]:
    """The route table: which hardware each device became, and the width
    it will actually be built at -- the width the router really programmed,
    not the one the schematic asked for.
    """
    lines = []
    for name, role in sorted(routed.device_roles.items()):
        width = routed.device_widths.get(name)
        note = ""
        if width is not None and width.effective is not None:
            note = f"  {width.prop}={width.effective}"
            if not width.programmable:
                note += " (fixed)"
        # Only the roles whose tail the bitstream really carries: a tail
        # printed against a device that cannot set one would read as a
        # promise the hardware does not make (R2 covers that case).
        tail = routed.device_tails.get(name)
        if tail is not None and tail.programmable and tail.effective is not None:
            note += f"  tail={tail.effective}"
        lines.append(f"  {name:<12} -> {role:<12}{note}")
    return lines


# ---------------------------------------------------------------------------
# Step 1: device allocation.
# ---------------------------------------------------------------------------

def _allocate_fets(
    requests: list[DeviceRequest], pair_roles: tuple[str, str], independent_roles: tuple[str, str],
    pair_rail: str, label: str, tail: DeviceRequest | None = None,
) -> dict[str, str]:
    """Assign each FET request to nmos_a/nmos_b/ndiffpair+/ndiffpair- (or the PMOS
    equivalents). Three cases can use the diff-pair role:

    - A drawn mosbius_ntail/mosbius_ptail (`tail`, TODO.md was Sec 2,
      closed 2026-08-22): its
      drain net names the pair directly, so the two FETs sourced on it
      *are* the pair rather than something pass 1 has to infer. This
      replaces pass 1 for that net, and it goes first: a user who drew a
      tail said which two devices are the pair, and that is not a guess
      to second-guess.
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

    Independent slots (nmos_a/nmos_b) are tried first (after any drawn
    tail's pair is placed) since they place no restriction on the source
    net at all.
    """
    roles: dict[str, str] = {}
    remaining_pair = list(pair_roles)
    remaining_indep = list(independent_roles)
    unassigned: list[DeviceRequest] = list(requests)

    # Pass 0: a drawn tail claims its two halves outright. A malformed
    # tail (drain not shared by exactly two same-polarity sources, or
    # wired straight to the rail instead of a real internal node) is not
    # applied here -- mosbius/check.py's check_design (D-series ERRORs)
    # is what explains that to the user and stops the CLI before routing
    # is even attempted; this is only a backstop against a caller that
    # routes without checking first, so it degrades to "ignore the tail
    # for pairing" rather than raising, and pass 1-3 below decide those
    # FETs' roles as if no tail had been drawn.
    if tail is not None and tail.terminals["d"] != pair_rail:
        halves = [d for d in requests if d.terminals.get("s") == tail.terminals["d"]]
        if len(halves) == 2:
            roles[halves[0].name] = remaining_pair.pop(0)
            roles[halves[1].name] = remaining_pair.pop(0)
            unassigned.remove(halves[0])
            unassigned.remove(halves[1])

    by_source: dict[str, list[DeviceRequest]] = {}
    for d in unassigned:
        by_source.setdefault(d.terminals["s"], []).append(d)

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
    ntail = [d for d in design.devices if d.kind == "ntail"]
    ptail = [d for d in design.devices if d.kind == "ptail"]

    if len(ntail) > 1:
        raise RouteError(
            f"DOESN'T FIT -- only one NMOS differential-pair tail on this chip\n\n"
            f"  {len(ntail)} mosbius_ntail devices requested, but there's exactly "
            f"one NMOS\n  tail bank (role ntail, ctrl_dpn_tail)."
        )
    if len(ptail) > 1:
        raise RouteError(
            f"DOESN'T FIT -- only one PMOS differential-pair tail on this chip\n\n"
            f"  {len(ptail)} mosbius_ptail devices requested, but there's exactly "
            f"one PMOS\n  tail bank (role ptail, ctrl_dpp_tail)."
        )

    roles.update(_allocate_fets(
        nmos, NMOS_PAIR_ROLES, NMOS_INDEPENDENT_ROLES, "VGND", "NMOS",
        tail=ntail[0] if ntail else None,
    ))
    roles.update(_allocate_fets(
        pmos, PMOS_PAIR_ROLES, PMOS_INDEPENDENT_ROLES, "VAPWR", "PMOS",
        tail=ptail[0] if ptail else None,
    ))
    for d in ntail:
        roles[d.name] = "ntail"
    for d in ptail:
        roles[d.name] = "ptail"

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


def _matrix_bit(touch: _Touch, row: int, net: str) -> int:
    """The chain bit closing `touch`'s crosspoint onto its side's `row`.

    Every (pin, row) pair that is missing from the bit map means the same
    thing -- the chip has no switch there -- so the lookup is wrapped once
    here rather than guarded at each call site. The row pickers below try
    to avoid ever asking for an unreachable row; this is the backstop that
    turns a slip into an explanation instead of a KeyError.
    """
    try:
        return _MATRIX_BIT_BY_PIN_ROW[(touch.pin, row)]
    except KeyError:
        reachable = rows_reachable(touch.pin)
        if net in PORT_ROW:
            # A port net's row is a bond wire, not a choice -- so the only
            # move is a different pin, and there is no point making the
            # reader work out which ones those are (SPEC.md Sec 2.10).
            usable = [pin for pin, (_s, r) in sorted(PORT_ROW.items()) if r in reachable]
            if len(usable) > 1:
                options = ", ".join(usable[:-1]) + f" or {usable[-1]}"
            elif usable:
                options = usable[0]
            else:
                options = "no package pin at all, on this chip"  # unreachable today
            why = (
                f"  '{net}' is a package pin, and its bus row is a permanent bond "
                f"wire\n  rather than something the router picks: {net} is always "
                f"bus_{PORT_ROW[net][0]}[{row}]\n  (SPEC.md Sec 2.10).\n\n"
                f"{_WHY_LIMITED_REACH}\n"
                f"  To fix: move this signal to a pin bonded to a row this "
                f"terminal can\n  reach ({options}), or arrange for the restricted "
                f"device not to be the\n  one sitting on this net."
            )
        else:
            why = (
                f"  '{net}' was placed on bus row {row}, which this terminal has no "
                f"switch\n  to.\n\n{_WHY_LIMITED_REACH}"
            )
        error = RouteError(
            f"DOESN'T FIT -- {_describe_touch(touch)} cannot reach "
            f"bus_{touch.side}[{row}]\n\n"
            f"  {touch.role}.{touch.terminal} reaches {_fmt_rows(reachable)}, "
            f"and nothing else.\n\n"
            f"{why}"
        )
        raise error from None


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
                       side=TERMINAL_SIDE[(role, terminal)],
                       pin=TERMINAL_PIN[(role, terminal)])
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

    def pick_free_row(side: str, net: str, touches: list[_Touch]) -> int:
        free = sorted(
            row for (s, row) in _FREE_ROWS
            if s == side and row_owner.get((s, row)) in (None, net)
        )
        if not free:
            raise RouteError(
                f"DOESN'T FIT -- no free bus_{side}[] row left for '{net}'\n\n"
                f"  All 6 rows on side {side} are already claimed by other nets, "
                f"ports\n  or rail taps. Try routing this net through the other "
                f"side, or freeing\n  up a row by sharing it with a net that's "
                f"already there."
            )
        # Not every row suits every terminal: a diff-pair or OTA input has
        # a switch to rows 1-3 only, so picking the lowest free row blind
        # is how this used to end in a KeyError.
        reachable = _shared_reach(touches)
        candidates = [row for row in free if row in reachable]
        if not candidates:
            raise RouteError(
                f"DOESN'T FIT -- no bus_{side}[] row that every device on "
                f"'{net}' can reach\n\n"
                f"  '{net}' connects:\n{_reach_lines(touches)}\n\n"
                f"  Free on side {side} right now: bus {_fmt_rows(free)}. The "
                f"terminals above can\n  share only bus {_fmt_rows(reachable)}, "
                f"and none of that is free.\n\n"
                f"{_WHY_LIMITED_REACH}\n"
                f"  Ideas:\n"
                f"    - Free up one of bus {_fmt_rows(reachable)} on side {side}, by "
                f"moving another\n      net elsewhere.\n"
                f"    - Give this net a package pin (name it ua1..ua5) if you can\n"
                f"      spare one: that pins it to the row the pin is bonded to,\n"
                f"      which may be a row the restricted terminal can reach.\n"
                f"    - Rearrange the circuit so the restricted device is not on\n"
                f"      this net at all -- only differential-pair and OTA inputs\n"
                f"      are limited."
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
            bits.add(_matrix_bit(t, row, net))
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
        reachable = _shared_reach(remaining)
        usable = [row for row in tappable if row in reachable]
        if not usable:
            unreachable_note = ""
            if tappable:
                unreachable_note = (
                    f"  The {rail} tap rows still free on side {side} are bus "
                    f"{_fmt_rows(tappable)},\n  but these terminals can share only "
                    f"bus {_fmt_rows(reachable)}:\n{_reach_lines(remaining)}\n\n"
                    f"{_WHY_LIMITED_REACH}\n"
                )
            raise RouteError(
                f"DOESN'T FIT -- no usable {rail} tap on side {side} for '{net}'\n\n"
                f"{unreachable_note}"
                f"  {rail} can only be reached from specific bus rows "
                f"(SPEC.md Sec 2.7),\n  and none of the ones this net could use is "
                f"available. If the device\n  has a source terminal, tying it "
                f"directly to {rail} costs no bus row\n  at all."
            )
        row = usable[0]
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
            row = pick_free_row(side, net, touches)
            claim_row(side, row, net)
            route_touches_on_row(touches, side, row, net)
            return
        # Spans both sides: need a free row on each side, joined by the
        # matching cfg_bus_short. Try every free A-row/B-row pair rather
        # than assuming row numbers line up between the two sides.
        a_rows = sorted(r for (s, r) in _FREE_ROWS if s == "A" and row_owner.get((s, r)) in (None, net))
        b_rows = sorted(r for (s, r) in _FREE_ROWS if s == "B" and row_owner.get((s, r)) in (None, net))
        both_free = sorted(set(a_rows) & set(b_rows))
        reachable = _shared_reach(touches)
        for row in both_free:
            if row not in reachable:
                continue  # some terminal here has no switch to this row
            claim_row("A", row, net)
            claim_row("B", row, net)
            bits.add(_BUS_SHORT_BIT_BY_ROW[row])
            for t in touches:
                bits.add(_matrix_bit(t, row, net))
            net_rows[net] = {"A": row, "B": row}
            return

        if both_free:
            # A row was free on both sides and still no good: some terminal
            # on this net cannot reach it. That is a rule rather than bad
            # luck, and it is worth saying which rule.
            raise RouteError(
                f"DOESN'T FIT -- '{net}' spans both bus sides and no row can "
                f"join them\n\n"
                f"  '{net}' connects:\n{_reach_lines(touches)}\n\n"
                f"  A net that touches both sides has to sit on the *same* row\n"
                f"  number on side A and on side B, bridged by cfg_bus_short. Free\n"
                f"  on both sides here: bus {_fmt_rows(both_free)}. The terminals "
                f"above can share\n  only bus {_fmt_rows(reachable)}.\n\n"
                f"{_WHY_LIMITED_REACH}\n"
                f"  And bus {_fmt_rows(ROWS_FREE_ON_BOTH_SIDES)} is the only row "
                f"ever free on both sides at once:\n  the others are permanently "
                f"bonded to a ua[] pin on one side or the\n  other (SPEC.md Sec "
                f"2.10). So this is a rule rather than a near miss:\n  a "
                f"differential-pair or OTA input can never sit on an internal net\n"
                f"  that spans both bus sides, whichever package pins you use.\n\n"
                f"  Ideas:\n"
                f"    - Get every device on '{net}' onto one bus side. Which side a\n"
                f"      device is on follows from the hardware slot it was given, so\n"
                f"      in practice this means changing which devices share a source.\n"
                f"    - Give the net a package pin (name it ua1..ua5). A port net is\n"
                f"      pinned to that pin's own row, which a restricted input may\n"
                f"      well reach, and the other side is still bridged with\n"
                f"      cfg_bus_short."
            )

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
    # is the failure that motivated reporting it at all.
    widths = device_widths(design, roles)
    tails = device_tails(design, roles)
    for dev_name, role in roles.items():
        if role in WIDTH_SETTING:
            pin, step = WIDTH_SETTING[role]
            lsb, msb = _encode_setting(
                widths[dev_name].effective, step,
                device=dev_name, prop=widths[dev_name].prop,
            )
            if lsb:
                bits.add(setting_bit(pin, 0))
            if msb:
                bits.add(setting_bit(pin, 1))
        if role in TAIL_SETTING:
            pin, step = TAIL_SETTING[role]
            lsb, msb = _encode_setting(
                tails[dev_name].effective, step, device=dev_name, prop="tail",
            )
            if lsb:
                bits.add(setting_bit(pin, 0))
            if msb:
                bits.add(setting_bit(pin, 1))

    return RoutedDesign(
        config=SwitchConfig(bits=frozenset(bits)),
        device_roles=roles,
        net_rows=net_rows,
        device_widths=widths,
        device_tails=tails,
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

    The stored routing is only reusable if its `device_roles` are keyed by
    the names this design actually uses. The topology hash deliberately
    ignores instance names, so a pure rename -- every device going from
    `M1` to `XM1` when the symbols gained `@spiceprefix`, say -- hashes identically and would otherwise be replayed with role
    keys naming devices that no longer exist. That used to surface as a
    route table quietly describing the wrong names, and now as a KeyError
    building the width table. Neither is a routing: re-solve instead.
    """
    topology = design_topology_hash(design)
    if not force:
        stored = load_routed_design(config_path)
        if stored is not None and stored.get("topology_hash") == topology and (
            set(stored["device_roles"]) == {d.name for d in design.devices}
        ):
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
                # matches a design whose w=/ratio=/tail= are unchanged too.
                device_widths=device_widths(design, roles),
                device_tails=device_tails(design, roles),
            )

    routed = route(design)
    save_routed_design(routed, design, config_path)
    return routed
