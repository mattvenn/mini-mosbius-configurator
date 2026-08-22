# SPDX-License-Identifier: Apache-2.0
"""Parse an xschem-netlisted SPICE file for a design built on
minimosbius_template.sch into a MosbiusDesign (SPEC.md Sec 3, architecture
diagram: "xschem -n (netlist) -> MosbiusDesign").

A design instantiates only the seven generic devices from xschem/mosbius_lib
(mosbius_nmos, mosbius_pmos, mosbius_nsink, mosbius_psource, mosbius_ota,
mosbius_ntail, mosbius_ptail). Each netlists as a flat instance line:

    <inst> <net> <net> ... <net> mosbius_<kind> <prop>=<value> ...

with a pin order fixed by that symbol's own declaration (SPEC.md Sec 3.4).
Net names reaching one of the design's fixed ports (ibias, ua1..ua5,
VAPWR, VDPWR, VGND -- SPEC.md Sec 3.1b) need no special marking: the net
literally being named e.g. "ua2" *is* the connection request.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Pin order for each generic device, exactly as declared in its .sym
# (xschem/mosbius_lib/mosbius_*.sym B{} box order, then its `extra` order
# -- confirmed by netlisting each symbol directly, see M2 notes and
# TODO.md's tail-symbol work order (was Sec 2, closed 2026-08-22).
DEVICE_PINS: dict[str, tuple[str, ...]] = {
    "nmos": ("g", "d", "s", "b"),
    "pmos": ("g", "d", "s", "b"),
    "nsink": ("out", "ibias", "b"),
    "psource": ("out", "ibias", "b"),
    "ota": ("inp", "inm", "outp", "outm", "ibias", "bn", "bp"),
    "ntail": ("d", "g", "s"),
    "ptail": ("d", "g", "s"),
}

# Terminals the symbols supply implicitly, via xschem's `extra` attribute
# (see any mosbius_*.sym header): the body ties, the shared `ibias`
# reference, and -- for the two tail banks -- the gate and source as
# well (TODO.md was Sec 2, closed 2026-08-22). All of these are
# hard-wired on silicon, so none are ever drawn on the schematic and the
# router has nothing to do with them -- but they DO appear on the
# netlist's instance line, so DEVICE_PINS above still counts them.
#
# Keyed by (kind, terminal) rather than terminal name alone: mosbius_ntail/
# mosbius_ptail's implicit "g"/"s" are spelled the same as mosbius_nmos/
# mosbius_pmos's real, drawn "g"/"s" -- a flat set of names would wrongly
# hide a genuinely-wired FET source from check.py's D1 (mosbius/check.py's
# `wired_nets`), which is exactly the kind of drift this design avoids.
IMPLICIT_PINS = frozenset({
    ("nmos", "b"), ("pmos", "b"),
    ("nsink", "b"), ("nsink", "ibias"),
    ("psource", "b"), ("psource", "ibias"),
    ("ota", "bn"), ("ota", "bp"), ("ota", "ibias"),
    ("ntail", "g"), ("ntail", "s"),
    ("ptail", "g"), ("ptail", "s"),
})

# xschem symbol name -> device kind.
SYMBOL_KIND = {
    "mosbius_nmos": "nmos",
    "mosbius_pmos": "pmos",
    "mosbius_nsink": "nsink",
    "mosbius_psource": "psource",
    "mosbius_ota": "ota",
    "mosbius_ntail": "ntail",
    "mosbius_ptail": "ptail",
}

# The design block's fixed port list (SPEC.md Sec 3.1b) -- a net with one
# of these exact names IS a connection to that chip pin, no annotation
# needed.
PORT_NAMES = {"ibias", "ua1", "ua2", "ua3", "ua4", "ua5", "VAPWR", "VDPWR", "VGND"}


class NetlistError(ValueError):
    """The netlist doesn't look like a design built on minimosbius_template.sch."""


@dataclass(frozen=True)
class DeviceRequest:
    """One generic-device instance from the user's design."""

    name: str                     # instance name from the netlist, e.g. "M1"
    kind: str                     # "nmos" / "pmos" / "nsink" / "psource" / "ota"
    terminals: dict[str, str]     # pin name -> net name
    properties: dict[str, int]    # e.g. {"w": 2}, {"ratio": 1}, {"tail": 4}


@dataclass(frozen=True)
class MosbiusDesign:
    """The canonical in-memory model of a user's circuit (SPEC.md Sec 3):
    generic devices and how their terminals are wired together. Nets are
    implicit in DeviceRequest.terminals -- two terminals on the same net
    name are the same electrical node.
    """

    devices: list[DeviceRequest]

    def nets(self) -> set[str]:
        return {net for dev in self.devices for net in dev.terminals.values()}

    def port_nets(self) -> set[str]:
        return self.nets() & PORT_NAMES


# Matches one instance line: name, pins (2+ bare identifiers), a
# mosbius_<kind> symbol reference, then optional space-separated
# key=value properties. Deliberately does not try to parse general SPICE
# (subckt headers, comments, unrelated devices) -- only lines that end in
# a recognised mosbius_lib symbol name are device requests.
_INSTANCE_RE = re.compile(
    r"^\s*(?P<name>\S+)\s+(?P<nets>(?:\S+\s+)+?)"
    r"mosbius_(?P<kind>nmos|pmos|nsink|psource|ota|ntail|ptail)"
    r"(?P<props>(?:\s+\w+=\S+)*)\s*$"
)
_PROP_RE = re.compile(r"(\w+)=(\S+)")


def parse_netlist(text: str) -> MosbiusDesign:
    """Parse the text of an xschem-generated SPICE netlist of a design
    built on minimosbius_template.sch.
    """
    devices: list[DeviceRequest] = []
    for line in text.splitlines():
        if line.strip().startswith(("*", ".")):
            continue
        m = _INSTANCE_RE.match(line)
        if not m:
            continue
        kind = m.group("kind")
        pins = DEVICE_PINS[kind]
        nets = m.group("nets").split()
        if len(nets) != len(pins):
            raise NetlistError(
                f"{m.group('name')}: mosbius_{kind} takes {len(pins)} connections "
                f"({', '.join(pins)}) but the netlist gives {len(nets)}\n"
                f"  This usually means the .sym and this parser's DEVICE_PINS table "
                f"have drifted apart -- check xschem/mosbius_lib/mosbius_{kind}.sym."
            )
        terminals = dict(zip(pins, nets))
        properties = {k: int(v) for k, v in _PROP_RE.findall(m.group("props"))}
        devices.append(DeviceRequest(
            name=m.group("name"), kind=kind, terminals=terminals, properties=properties,
        ))

    if not devices:
        raise NetlistError(
            "no mosbius_nmos/mosbius_pmos/mosbius_nsink/mosbius_psource/mosbius_ota/"
            "mosbius_ntail/mosbius_ptail instances found in this netlist\n"
            "  Draw your circuit using the generic devices from xschem/mosbius_lib "
            "(SPEC.md Sec 3.4), not raw sky130 transistors -- the router only "
            "understands those seven."
        )
    return MosbiusDesign(devices=devices)
