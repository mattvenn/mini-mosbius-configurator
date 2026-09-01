# SPDX-License-Identifier: Apache-2.0
"""Parse an xschem-netlisted SPICE file for a design built on
mini_mosbius.sch into a MosbiusDesign (SPEC.md Sec 3, architecture
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

from pathlib import Path

import re
from dataclasses import dataclass

from mosbius import messages

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
    """The netlist doesn't look like a design built on mini_mosbius.sch."""


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
    # How many bias generators the sheet carries. Not a device request --
    # the router never places it, since the chip's bias section is fixed
    # hardware -- but the count has to be exactly one, so check.py needs
    # it. See _count_bias_generators().
    bias_generators: int = 0

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

# The chip's bias generator, in the two forms a sheet can carry it: a
# mosbius_bias symbol, or the three transistors drawn by hand (which is
# what mini_mosbius.sch and the older examples still do). Both are
# recognised by the one device that has to be unique -- the reference
# diode, an NMOS with its drain and gate both on `ibias`. Everything else
# in the generator is a copy of that, and copies may be duplicated
# harmlessly.
_BIAS_BLOCK_RE = re.compile(r"^\s*\S+\s+.*\bmosbius_bias\s*$")
_BIAS_DIODE_RE = re.compile(
    r"^\s*\S+\s+(?P<d>\S+)\s+(?P<g>\S+)\s+\S+\s+\S+\s+sky130_fd_pr__nfet"
)


def _count_bias_generators(lines: list[str]) -> int:
    """How many bias references the design block contains.

    `ibias` (pin ua[0]) is a current input, and the chip turns it into the
    gate voltage every mirror leg, tail bank and the OTA tail copies. That
    conversion happens exactly once per chip. Two references halve the
    reference current between them -- two diodes in parallel on one node,
    measured at -99 uA a leg where -200 uA was right -- and none leaves
    every mirror gate whereever the solver puts it.
    """
    count = 0
    for line in lines:
        if line.strip().startswith(("*", ".")):
            continue
        if _BIAS_BLOCK_RE.match(line):
            count += 1
            continue
        m = _BIAS_DIODE_RE.match(line)
        if m and m.group("d") == m.group("g") == "ibias":
            count += 1
    return count


class StaleNetlistError(ValueError):
    """The netlist is older than the schematic it was generated from, so
    routing it would route a circuit the user is no longer looking at.

    Silent staleness is the expensive kind of wrong here: the router
    happily succeeds, reports a bitstream, and the user compares it
    against a drawing that says something else. It has to be an error
    rather than a warning for that reason -- a warning scrolls past.
    """


def schematic_for_netlist(netlist_path: Path) -> Path | None:
    """The .sch that produced `netlist_path`, or None if it cannot be
    found on this machine.

    xschem writes its source as the netlist's first line,
    `** sch_path: /foss/designs/.../ring.sch`. That path is written from
    inside whatever filesystem xschem ran in -- which for nearly everyone
    here is the IIC-OSIC-TOOLS container they also route from, so it
    resolves directly. When it does not (a netlist copied between
    machines, or a container mounted at a different point), fall back to
    a same-named .sch beside the netlist or under examples/, and give up
    quietly rather than guessing: a missed check is a much smaller harm
    than a false alarm telling someone their fresh netlist is stale.
    """
    try:
        first = netlist_path.read_text().split("\n", 1)[0]
    except OSError:
        return None
    if not first.startswith("** sch_path:"):
        return None
    recorded = Path(first[len("** sch_path:"):].strip())
    if recorded.is_file():
        return recorded

    name = recorded.name
    here = netlist_path.resolve().parent
    for candidate in (here / name, *sorted(here.parent.glob(f"examples/*/{name}"))):
        if candidate.is_file():
            return candidate
    return None


def check_netlist_fresh(netlist_path: Path) -> None:
    """Raise StaleNetlistError if `netlist_path` predates its schematic.

    Called before parsing, because a stale netlist is not a parse problem
    and its symptoms turn up much later -- as a routing failure that does
    not match the drawing, or worse, as a successful route of the wrong
    circuit.
    """
    sch = schematic_for_netlist(netlist_path)
    if sch is None:
        return
    if sch.stat().st_mtime <= netlist_path.stat().st_mtime:
        return
    raise StaleNetlistError(
        messages.NETLIST_STALE.format(
            netlist_path=netlist_path, sch=sch, sch_name=sch.name,
        )
    )


def _design_block(text: str) -> list[str]:
    """The lines of the design itself, without the symbol bodies below it.

    xschem writes the design as a commented-out `**.subckt` / `**.ends`
    pair at the top of the file, then appends a real `.subckt` for every
    symbol the design used. Only the first block is the circuit the user
    drew; the rest is the library.

    That distinction matters because `mosbius_ota.sch` builds its tail
    bank out of a `mosbius_nsink`, passing the OTA's own parameter
    through:

        XMtail net1 ibias bn mosbius_nsink ratio=tail

    Scanning the whole file matched that line, tried `int("tail")` and
    raised a ValueError traceback -- and, with the int() made tolerant,
    would still have counted a current sink the schematic never drew.
    Every OTA design hit it; the FET symbols never did, because their
    bodies hold raw sky130 devices rather than mosbius_* ones.

    Hand-written netlists (this project's own tests, mostly) have no
    `**.subckt` marker at all, so a file without one is read whole, the
    way it always was.
    """
    lines = text.splitlines()
    start = next(
        (i for i, l in enumerate(lines) if l.strip().startswith("**.subckt")), None
    )
    if start is None:
        return lines
    end = next(
        (i for i, l in enumerate(lines[start:], start) if l.strip().startswith("**.ends")),
        len(lines),
    )
    return lines[start:end]


def parse_netlist(text: str) -> MosbiusDesign:
    """Parse the text of an xschem-generated SPICE netlist of a design
    built on mini_mosbius.sch.
    """
    # A routed design JSON is the other file `build/` holds for the same
    # design, one character away in the name (`ring.mosbius.json` vs
    # `ring.spice`), so it is the file most likely to arrive here by
    # mistake -- and "no mosbius_* instances found" would be a true but
    # unhelpful thing to say about it.
    if text.lstrip().startswith("{") and '"bitstream"' in text:
        raise NetlistError(messages.NETLIST_ROUTED_JSON_GIVEN)

    block = _design_block(text)
    devices: list[DeviceRequest] = []
    for line in block:
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
                messages.NETLIST_PIN_COUNT_MISMATCH.format(
                    name=m.group("name"), kind=kind, n_pins=len(pins),
                    pin_names=", ".join(pins), n_nets=len(nets),
                )
            )
        terminals = dict(zip(pins, nets))
        properties = {k: int(v) for k, v in _PROP_RE.findall(m.group("props"))}
        devices.append(DeviceRequest(
            name=m.group("name"), kind=kind, terminals=terminals, properties=properties,
        ))

    if not devices:
        raise NetlistError(messages.NETLIST_NO_DEVICES_FOUND)
    return MosbiusDesign(
        devices=devices, bias_generators=_count_bias_generators(block),
    )
