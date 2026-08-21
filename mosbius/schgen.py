# SPDX-License-Identifier: Apache-2.0
"""Decoded circuit -> xschem schematic (SPEC.md Sec 3.8's "Generated .sch"
output form).

Places one mosbius_lib generic-device symbol per decoded device, in a row,
and routes each net as a dedicated horizontal "channel" below the row.
Every device-to-channel connection gets its own private vertical column
(a small unique sideways jog off the device's own pin, then straight down)
so unrelated wires can never accidentally touch: no two connections ever
share an (x, y) point unless they are genuinely on the same net.

This is deliberately not a general-purpose auto-router -- SPEC.md Sec 3.8
notes decoded circuits have at most 9 devices, so a predictable, provably
collision-free layout beats a clever one.
"""

from __future__ import annotations

from dataclasses import dataclass

from mosbius.decode import DecodedDesign
from mosbius.netlist import PORT_NAMES

# Each mosbius_lib symbol's pin -> local (x, y) offset, i.e. the exact
# coordinate of that pin when the symbol is placed at (0, 0) unrotated.
# These are authored coordinates (xschem/mosbius_lib/*.sym B{} boxes) --
# see the geometry notes in each .sym file's header.
#
# The body terminals (b / bn / bp) are absent on purpose: the symbols
# supply them implicitly via xschem's `extra` mechanism, so there is no
# pin to draw a wire to. See netlist.IMPLICIT_PINS.
#
# NMOS and PMOS differ: pmos3-style symbols put the source at the top
# (towards VAPWR) and the drain at the bottom, which is the reverse of
# nmos3.
_NMOS_PINS = {"g": (-20, 0), "d": (20, -30), "s": (20, 30)}
_PMOS_PINS = {"g": (-20, 0), "d": (20, 30), "s": (20, -30)}
_NSINK_PINS = {"ibias": (-40, 0), "out": (0, -40)}
_PSOURCE_PINS = {"ibias": (-40, 0), "out": (0, 40)}
_OTA_PINS = {
    "inp": (-70, -25), "inm": (-70, 25),
    "outp": (70, -15), "outm": (70, 15),
    "ibias": (-30, 70),
}

# Device name -> (symbol name, pin-offset table, property template).
# ndiffpair+/ndiffpair-/pdiffpair+/pdiffpair- have no adjustable width in hardware (SPEC.md
# Sec 2.12: diff-pair transistors are fixed-size, only their shared tail
# current is configurable) -- rendered at a fixed representative width.
_DEVICE_SYMBOLS = {
    "nfeta": ("mosbius_nmos", _NMOS_PINS, lambda s: {"w": s.get("width", 4)}),
    "nfetb": ("mosbius_nmos", _NMOS_PINS, lambda s: {"w": s.get("width", 4)}),
    "pfeta": ("mosbius_pmos", _PMOS_PINS, lambda s: {"w": s.get("width", 4)}),
    "pfetb": ("mosbius_pmos", _PMOS_PINS, lambda s: {"w": s.get("width", 4)}),
    "ndiffpair+": ("mosbius_nmos", _NMOS_PINS, lambda s: {"w": 4}),
    "ndiffpair-": ("mosbius_nmos", _NMOS_PINS, lambda s: {"w": 4}),
    "pdiffpair+": ("mosbius_pmos", _PMOS_PINS, lambda s: {"w": 4}),
    "pdiffpair-": ("mosbius_pmos", _PMOS_PINS, lambda s: {"w": 4}),
    "mirn_a": ("mosbius_nsink", _NSINK_PINS, lambda s: {"ratio": s.get("ratio", 1)}),
    "mirn_b": ("mosbius_nsink", _NSINK_PINS, lambda s: {"ratio": s.get("ratio", 1)}),
    "mirp_a": ("mosbius_psource", _PSOURCE_PINS, lambda s: {"ratio": s.get("ratio", 1)}),
    "mirp_b": ("mosbius_psource", _PSOURCE_PINS, lambda s: {"ratio": s.get("ratio", 1)}),
    "otan": ("mosbius_ota", _OTA_PINS, lambda s: {"tail": s.get("tail", 2)}),
}

# nfeta/nfetb/ndiffpair+/ndiffpair- terminal "s" maps to mosbius_nmos's own "s" pin
# directly -- no renaming needed; PMOS/mirror/OTA terminal names already
# match their generic symbol's pin names one-to-one (SPEC.md Sec 2.12
# device inventory table uses the same g/d/s and in/out naming throughout).

DEVICE_PITCH = 500
JOG_STEP = 8
CHANNEL_BASE_Y = -1200
CHANNEL_PITCH = 60


@dataclass(frozen=True)
class _Connection:
    pin_x: int
    pin_y: int
    net: str
    # x of this device's rightmost pin. Jog columns start to the right of
    # it so a connection's vertical run can never sit on top of another
    # pin of the same device -- which is exactly what happens if columns
    # are measured from each pin individually and the counter grows past
    # the symbol's own width.
    jog_base_x: int


def _sym_props(name: str, value: object) -> str:
    return f"{name}={value}"


def _port_net_name(net: str) -> str:
    """decode.py names external pins "ua[N]" (matching bitmap.py/model.py's
    EXTERNAL_PINS, and the real chip's own bus-pin notation). But
    minimosbius_template.sch's ports -- what a design.sch's netlist, and
    therefore netlist.py/route.py, actually expect -- are plain "uaN" (no
    brackets; chosen to dodge xschem's bus-pin geometry, see M2 notes).
    Normalise here so a schgen'd schematic's ports match what route.py
    (M3) can consume, keeping SPEC.md Sec 3.8's "edit it, emit a new
    bitstream" round-trip possible.
    """
    if net.startswith("ua[") and net.endswith("]"):
        return "ua" + net[3:-1]
    return net


def generate_schematic(decoded: DecodedDesign, title: str = "decoded circuit") -> str:
    """Return the text of an xschem .sch file for `decoded`."""
    lines = [
        "v {xschem version=3.4.8RC file_version=1.2}",
        "G {}",
        "K {}",
        "V {}",
        "S {}",
        "E {}",
        f"T {{{title} -- generated by mosbius/schgen.py, do not hand-edit}} "
        f"0 -1500 0 0 0.3 0.3 {{}}",
    ]

    connections: list[_Connection] = []
    net_connections: dict[str, list[_Connection]] = {}

    component_lines = []
    for i, dev in enumerate(decoded.devices):
        if dev.name not in _DEVICE_SYMBOLS:
            raise ValueError(f"no schgen mapping for device {dev.name!r}")
        symname, pins, props_fn = _DEVICE_SYMBOLS[dev.name]
        origin_x = i * DEVICE_PITCH
        props = props_fn(dev.settings)
        prop_str = " ".join(_sym_props(k, v) for k, v in props.items())
        inst_name = f"{dev.name}_{i}"
        component_lines.append(
            f"C {{{symname}.sym}} {origin_x} 0 0 0 {{name={inst_name} {prop_str}}}"
        )
        for term, net in dev.terminals.items():
            if term not in pins:
                raise ValueError(f"{dev.name} has no pin {term!r} on {symname}")
            dx, dy = pins[term]
            net = _port_net_name(net)
            conn = _Connection(
                pin_x=origin_x + dx, pin_y=dy, net=net,
                jog_base_x=origin_x + max(px for px, _ in pins.values()),
            )
            connections.append(conn)
            net_connections.setdefault(net, []).append(conn)

    # Assign jog columns in contiguous per-net blocks (see module docstring)
    # so every net's channel spans a block of x disjoint from every other
    # net's -- crossing another net's channel row can never touch it.
    jog_x_by_conn: dict[int, int] = {}
    channel_y_by_net: dict[str, int] = {}
    counter = 0
    for net_index, (net, conns) in enumerate(sorted(net_connections.items())):
        channel_y_by_net[net] = CHANNEL_BASE_Y - net_index * CHANNEL_PITCH
        for conn in conns:
            jog_x_by_conn[id(conn)] = counter
            counter += 1

    wire_lines = []
    for conn in connections:
        jog_col = jog_x_by_conn[id(conn)]
        jog_x = conn.jog_base_x + JOG_STEP + jog_col
        channel_y = channel_y_by_net[conn.net]
        # pin -> jog (horizontal), jog -> channel (vertical).
        wire_lines.append(f"N {conn.pin_x} {conn.pin_y} {jog_x} {conn.pin_y} {{\nlab={conn.net}}}")
        wire_lines.append(f"N {jog_x} {conn.pin_y} {jog_x} {channel_y} {{\nlab={conn.net}}}")

    for net, conns in net_connections.items():
        min_x = min(c.jog_base_x + JOG_STEP + jog_x_by_conn[id(c)] for c in conns)
        max_x = max(c.jog_base_x + JOG_STEP + jog_x_by_conn[id(c)] for c in conns)
        channel_y = channel_y_by_net[net]
        if min_x != max_x:
            wire_lines.append(f"N {min_x} {channel_y} {max_x} {channel_y} {{\nlab={net}}}")
        # A net touching a real chip pin/rail gets an external port there
        # too, so the generated schematic stays connected to the outside
        # world exactly like the design block it was decoded from.
        if net in PORT_NAMES:
            anchor_x = min_x
            wire_lines.append(
                f"C {{devices/iopin.sym}} {anchor_x} {channel_y} 0 1 "
                f"{{name=port_{net} lab={net}}}"
            )

    lines.extend(wire_lines)
    lines.extend(component_lines)
    return "\n".join(lines) + "\n"
