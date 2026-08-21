# SPDX-License-Identifier: Apache-2.0
"""SwitchConfig: the canonical in-memory (and file) representation of a
mini-MOSbius configuration -- which of the 192 chain bits are set, plus the
bias current that goes with them (SPEC.md Sec 3.4b, Sec 3.6).

Also resolves the raw device-setting bits (widths, mirror ratios,
diff-pair/OTA tails, source ties, OTA mode) into human-readable values, and
builds the undirected electrical graph that mosbius/check.py and
mosbius/decode.py both walk -- nodes are bus segments, crosspoints, rails,
`ibias` and the external `ua[]` pins; edges are closed switches plus the
fixed physical bonds (SPEC.md Sec 3.1, Sec 2.10).
"""

from __future__ import annotations

from dataclasses import dataclass

from mosbius import bitstream
from mosbius.bitmap import DEVICE_SETTING_BITS, MATRIX_BITS

# Default bias current: upstream's testbenches drive `ibias` with 100 uA
# (SPEC.md Sec 3.4b). This is just a starting point -- every mirror ratio and
# every diff-pair/OTA tail scales with whatever value is actually stored.
DEFAULT_IBIAS = 100e-6

# SPEC.md Sec 2.10 -- VERIFIED external analog pin map, straight from
# ttsky-mini-mosbius/src/project.v `assign ua[k] = bus_X[n];`.
EXTERNAL_PINS = {
    "ua[1]": ("A", 1),
    "ua[2]": ("A", 3),
    "ua[3]": ("A", 5),
    "ua[4]": ("B", 2),
    "ua[5]": ("B", 4),
}

RAILS = ("VAPWR", "VGND", "VDPWR")

# Every device's terminal names -> crosspoint node (SPEC.md Sec 2.12 device
# inventory). Shared by mosbius/check.py (W1/W3) and mosbius/decode.py
# (per-device net reporting) so the topology is defined in exactly one place.
#
# The 4 independent FETs expose d/g/s. The diff-pair halves and OTA don't
# expose a source terminal (it's shared/internal, SPEC.md Sec 2.12) -- ndiffpair+/
# pdiffpair+ read the netlist's "inp"/"outp" as g/d, ndiffpair-/pdiffpair- read "inm"/"outm"
# as g/d. The 4 current mirrors expose one terminal, named "out". The OTA is
# used as one 5-transistor block with 4 terminals.
DEVICE_TERMINALS: dict[str, dict[str, str]] = {
    "nmos_a": {"d": "xpt_nfeta_d", "g": "xpt_nfeta_g", "s": "xpt_nfeta_s"},
    "nmos_b": {"d": "xpt_nfetb_d", "g": "xpt_nfetb_g", "s": "xpt_nfetb_s"},
    "pmos_a": {"d": "xpt_pfeta_d", "g": "xpt_pfeta_g", "s": "xpt_pfeta_s"},
    "pmos_b": {"d": "xpt_pfetb_d", "g": "xpt_pfetb_g", "s": "xpt_pfetb_s"},
    "ndiffpair+": {"g": "xpt_dpn_inp", "d": "xpt_dpn_outp"},
    "ndiffpair-": {"g": "xpt_dpn_inm", "d": "xpt_dpn_outm"},
    "pdiffpair+": {"g": "xpt_dpp_inp", "d": "xpt_dpp_outp"},
    "pdiffpair-": {"g": "xpt_dpp_inm", "d": "xpt_dpp_outm"},
    "nsink_a": {"out": "xpt_mirn_a"},
    "nsink_b": {"out": "xpt_mirn_b"},
    "psource_a": {"out": "xpt_mirp_a"},
    "psource_b": {"out": "xpt_mirp_b"},
    "ota": {
        "inp": "xpt_otan_inp", "outp": "xpt_otan_outp",
        "inm": "xpt_otan_inm", "outm": "xpt_otan_outm",
    },
}

# The 4 devices with an independently-routable source, for W1 (SPEC.md
# Sec 2.12: "eight FETs are freely usable singly").
INDEPENDENT_FETS = ("nmos_a", "nmos_b", "pmos_a", "pmos_b")

# The four FET source-tie bits: setting one shorts that FET's own source
# crosspoint directly to its rail, bypassing the bus entirely (SPEC.md
# Sec 2.11, Sec 2.12). ctrl_dpp_source/ctrl_dpn_source (the other two source
# ties) tie the *shared* diff-pair source node to a rail -- that node has no
# matrix terminal and nothing else can ever reach it (SPEC.md Sec 2.12: "no
# matrix terminals"), so it can never participate in a short and is tracked
# only as a DeviceSettings flag, not a graph edge.
FET_SOURCE_TIE_TO_RAIL = {
    "ctrl_pfeta_source": ("xpt_pfeta_s", "VAPWR"),
    "ctrl_pfetb_source": ("xpt_pfetb_s", "VAPWR"),
    "ctrl_nfeta_source": ("xpt_nfeta_s", "VGND"),
    "ctrl_nfetb_source": ("xpt_nfetb_s", "VGND"),
}


def bus_node(side: str, row: int) -> str:
    return f"bus_{side}[{row}]"


# ---------------------------------------------------------------------------
# DC conduction *through* a device, as opposed to through the switch matrix.
# ---------------------------------------------------------------------------
#
# check.py's main graph has one kind of edge: a closed switch. That is the
# right model for "are these two things shorted together", which is what
# every ERROR check asks. It is the wrong model for "is this node's voltage
# defined", because a transistor channel carries DC and is not a switch --
# so the output of an inverter, which reaches a rail only through its own
# two transistors, looks unreachable.
#
# This table adds the missing edges, for that question only. Feeding them to
# E1 would make every working inverter a VAPWR-VGND short; feeding them to W1
# would make every transistor look like its channel is shorted. See
# check.py::_biasing_graph.
#
# `setting` names a DeviceSettings field that must be True for the path to
# exist, or None if it always does.


@dataclass(frozen=True)
class DCPath:
    a: str
    b: str
    label: str
    setting: str | None = None


DEVICE_DC_PATHS: tuple[DCPath, ...] = (
    # The four independent FETs: drain <-> source through the channel.
    # Whether that reaches a rail depends on where the source is routed,
    # which is the matrix's business -- so this only joins the two
    # crosspoints and lets the graph search finish the job.
    DCPath("xpt_nfeta_d", "xpt_nfeta_s", "nmos_a channel"),
    DCPath("xpt_nfetb_d", "xpt_nfetb_s", "nmos_b channel"),
    DCPath("xpt_pfeta_d", "xpt_pfeta_s", "pmos_a channel"),
    DCPath("xpt_pfetb_d", "xpt_pfetb_s", "pmos_b channel"),

    # The diff-pair halves have no source crosspoint at all -- the shared
    # tail has no matrix terminal (SPEC.md Sec 2.12) -- so their channel
    # leads somewhere reachable only when the tail is tied to its rail by
    # ctrl_dp{n,p}_source. With that bit clear the tail really is floating
    # and the drain really has no DC path, which is worth warning about.
    DCPath("xpt_dpn_outp", "VGND", "ndiffpair+ channel to its tied tail", "dpn_source"),
    DCPath("xpt_dpn_outm", "VGND", "ndiffpair- channel to its tied tail", "dpn_source"),
    DCPath("xpt_dpp_outp", "VAPWR", "pdiffpair+ channel to its tied tail", "dpp_source"),
    DCPath("xpt_dpp_outm", "VAPWR", "pdiffpair- channel to its tied tail", "dpp_source"),

    # Mirror legs: inside the block the mirror FET's source sits on the
    # rail, so `out` always has a DC path to it (that is what makes it a
    # current sink/source rather than a floating node).
    DCPath("xpt_mirn_a", "VGND", "nsink_a mirror leg"),
    DCPath("xpt_mirn_b", "VGND", "nsink_b mirror leg"),
    DCPath("xpt_mirp_a", "VAPWR", "psource_a mirror leg"),
    DCPath("xpt_mirp_b", "VAPWR", "psource_b mirror leg"),

    # The OTA's outputs are its PMOS load's drains, and that load's sources
    # are on VAPWR inside the block. Its inputs are gates and get nothing.
    DCPath("xpt_otan_outp", "VAPWR", "ota output stage"),
    DCPath("xpt_otan_outm", "VAPWR", "ota output stage"),
)


# Crosspoint node -> "device.terminal", so diagnostics can say `ndiffpair+.g`
# instead of `xpt_dpn_inp` (the same naming decode.py prints).
TERMINAL_BY_CROSSPOINT: dict[str, str] = {
    xpt: f"{device}.{terminal}"
    for device, terminals in DEVICE_TERMINALS.items()
    for terminal, xpt in terminals.items()
}


# ---------------------------------------------------------------------------
# Device settings: decode the raw cycler/toggle bits into named values.
# ---------------------------------------------------------------------------

# Index bit -> (pin, index) once, up front, instead of re-scanning
# DEVICE_SETTING_BITS on every field lookup.
_SETTING_BIT_BY_PIN_INDEX: dict[tuple[str, int], int] = {
    (sb.pin, sb.index): bit for bit, sb in DEVICE_SETTING_BITS.items()
}


def setting_bit(pin: str, index: int = 0) -> int:
    """The chain bit number for a device-setting pin's given bit index.
    Public: mosbius/route.py uses this to emit width/ratio/tail/source
    bits, the mirror image of what DeviceSettings.decode() reads.
    """
    try:
        return _SETTING_BIT_BY_PIN_INDEX[(pin, index)]
    except KeyError:
        raise KeyError(f"no bit found for {pin}[{index}]") from None


def _single(closed: frozenset[int], pin: str) -> bool:
    return setting_bit(pin, 0) in closed


def _decode_cycler(closed: frozenset[int], pin: str, step: int) -> int:
    lsb = 1 if setting_bit(pin, 0) in closed else 0
    msb = 1 if setting_bit(pin, 1) in closed else 0
    return step * (1 + lsb + 2 * msb)


def encode_cycler(n: int, step: int) -> tuple[int, int]:
    """Inverse of _decode_cycler: given a setting value (1-4 for step=1,
    2/4/6/8 for step=2), return the (lsb_bit_set, msb_bit_set) pair to
    close. SPEC.md Sec 2.11's formula is bijective over the 4 raw
    combinations, so every valid n has exactly one encoding.
    """
    valid = range(1, 5) if step == 1 else range(2, 9, 2)
    if n not in valid:
        raise ValueError(
            f"{n} is not a valid setting for step={step}\n"
            f"  Valid values are {list(valid)} (SPEC.md Sec 2.11: "
            f"n = step * (1 + b_lsb + 2*b_msb))."
        )
    k = n // step - 1
    return (k & 1, (k >> 1) & 1)


@dataclass(frozen=True)
class DeviceSettings:
    """All 30 non-matrix bits, decoded to their real-world meaning."""

    pfeta_width: int
    pfetb_width: int
    nfeta_width: int
    nfetb_width: int
    mirp_a_ratio: int
    mirp_b_ratio: int
    mirn_a_ratio: int
    mirn_b_ratio: int
    dpp_tail: int
    dpn_tail: int
    otan_tail: int
    pfeta_source: bool  # xpt_pfeta_s tied directly to VAPWR
    pfetb_source: bool  # xpt_pfetb_s tied directly to VAPWR
    nfeta_source: bool  # xpt_nfeta_s tied directly to VGND
    nfetb_source: bool  # xpt_nfetb_s tied directly to VGND
    dpp_source: bool  # PMOS diff-pair shared source tied to VAPWR
    dpn_source: bool  # NMOS diff-pair shared source tied to VGND
    otan_mode0: bool  # ctrl_otan_mode[0]: diode-connects the OTA via outp
    otan_mode1: bool  # ctrl_otan_mode[1]: diode-connects the OTA via outm

    @classmethod
    def decode(cls, closed: frozenset[int]) -> "DeviceSettings":
        return cls(
            pfeta_width=_decode_cycler(closed, "ctrl_pfeta_width", step=1),
            pfetb_width=_decode_cycler(closed, "ctrl_pfetb_width", step=1),
            nfeta_width=_decode_cycler(closed, "ctrl_nfeta_width", step=1),
            nfetb_width=_decode_cycler(closed, "ctrl_nfetb_width", step=1),
            mirp_a_ratio=_decode_cycler(closed, "ctrl_mirp_a", step=1),
            mirp_b_ratio=_decode_cycler(closed, "ctrl_mirp_b", step=1),
            mirn_a_ratio=_decode_cycler(closed, "ctrl_mirn_a", step=1),
            mirn_b_ratio=_decode_cycler(closed, "ctrl_mirn_b", step=1),
            dpp_tail=_decode_cycler(closed, "ctrl_dpp_tail", step=2),
            dpn_tail=_decode_cycler(closed, "ctrl_dpn_tail", step=2),
            otan_tail=_decode_cycler(closed, "ctrl_otan_tail", step=2),
            pfeta_source=_single(closed, "ctrl_pfeta_source"),
            pfetb_source=_single(closed, "ctrl_pfetb_source"),
            nfeta_source=_single(closed, "ctrl_nfeta_source"),
            nfetb_source=_single(closed, "ctrl_nfetb_source"),
            dpp_source=_single(closed, "ctrl_dpp_source"),
            dpn_source=_single(closed, "ctrl_dpn_source"),
            otan_mode0=setting_bit("ctrl_otan_mode", 0) in closed,
            otan_mode1=setting_bit("ctrl_otan_mode", 1) in closed,
        )


# ---------------------------------------------------------------------------
# The electrical graph.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Edge:
    neighbor: str
    label: str  # e.g. "cfga_nfeta_s[3]", "cfg_bus_short[6]", "ua[1] (pin)"


Graph = dict[str, list[Edge]]


def _add_edge(graph: Graph, a: str, b: str, label: str) -> None:
    graph.setdefault(a, []).append(Edge(neighbor=b, label=label))
    graph.setdefault(b, []).append(Edge(neighbor=a, label=label))


def connected_components(graph: Graph) -> dict[str, int]:
    """node -> component id, via BFS. Isolated nodes get their own id.

    Shared by mosbius/check.py (which nodes are shorted together) and
    mosbius/decode.py (which nodes form one electrical net).
    """
    from collections import deque

    comp: dict[str, int] = {}
    next_id = 0
    for start in graph:
        if start in comp:
            continue
        comp[start] = next_id
        q = deque([start])
        while q:
            node = q.popleft()
            for edge in graph.get(node, []):
                if edge.neighbor not in comp:
                    comp[edge.neighbor] = next_id
                    q.append(edge.neighbor)
        next_id += 1
    return comp


# ---------------------------------------------------------------------------
# SwitchConfig
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SwitchConfig:
    """A full 192-bit configuration: which chain bits are set, plus ibias.

    This is the file format described in SPEC.md Sec 3.6: inspectable,
    hand-editable, and the thing mosbius.spice/bitstream.py/check.py/
    decode.py all operate on. `schema` follows SPEC.md Sec 3.6's versioning
    promise from the first commit.
    """

    bits: frozenset[int]
    ibias: float = DEFAULT_IBIAS
    schema: int = 1

    def __post_init__(self):
        bad = [b for b in self.bits if not (0 <= b < bitstream.NUM_BITS)]
        if bad:
            raise ValueError(
                f"bit(s) {sorted(bad)} are out of range 0..{bitstream.NUM_BITS - 1}\n"
                f"  The mini-MOSbius config chain is exactly {bitstream.NUM_BITS} "
                f"bits (SPEC.md Sec 2.1)."
            )

    # -- construction / serialisation ------------------------------------

    @classmethod
    def from_bitstream(cls, hexstr: str, ibias: float = DEFAULT_IBIAS) -> "SwitchConfig":
        return cls(bits=bitstream.unpack(hexstr), ibias=ibias)

    def to_bitstream(self) -> str:
        return bitstream.pack(self.bits)

    def is_closed(self, bit: int) -> bool:
        return bit in self.bits

    # -- decoding ----------------------------------------------------------

    def device_settings(self) -> DeviceSettings:
        return DeviceSettings.decode(self.bits)

    def closed_matrix_switches(self):
        """MatrixBit entries for closed bits that carry a crosspoint (i.e.
        an actual cfga_*/cfgb_* switch -- excludes cfg_bus_short/cfg_bus_pwr,
        which are handled separately since they don't have a crosspoint)."""
        return [
            mb for bit, mb in MATRIX_BITS.items()
            if bit in self.bits and mb.crosspoint is not None
        ]

    def closed_bus_shorts(self):
        return [
            mb for bit, mb in MATRIX_BITS.items()
            if bit in self.bits and mb.pin == "cfg_bus_short"
        ]

    def closed_bus_pwr_taps(self):
        return [
            mb for bit, mb in MATRIX_BITS.items()
            if bit in self.bits and mb.pin == "cfg_bus_pwr"
        ]

    def build_graph(self) -> Graph:
        """The undirected electrical graph described in SPEC.md Sec 3.1."""
        graph: Graph = {}

        # Always-present nodes, even with no edges yet (so an unused
        # crosspoint/segment still shows up for I1/W2-style queries).
        for side in ("A", "B"):
            for row in range(1, 7):
                graph.setdefault(bus_node(side, row), [])
        for rail in RAILS:
            graph.setdefault(rail, [])
        graph.setdefault("ibias", [])
        for pin in EXTERNAL_PINS:
            graph.setdefault(pin, [])
        graph.setdefault("ua[0]", [])
        crosspoints = {mb.crosspoint for mb in MATRIX_BITS.values() if mb.crosspoint}
        for xpt in crosspoints:
            graph.setdefault(xpt, [])

        # Regular matrix switches: crosspoint <-> bus_<side>[row].
        for mb in self.closed_matrix_switches():
            label = f"{mb.pin}[{mb.index}]"
            _add_edge(graph, mb.crosspoint, bus_node(mb.bus, mb.row), label)

        # cfg_bus_short[n]: bus_A[n] <-> bus_B[n].
        for mb in self.closed_bus_shorts():
            label = f"cfg_bus_short[{mb.index}]"
            _add_edge(graph, bus_node("A", mb.row), bus_node("B", mb.row), label)

        # cfg_bus_pwr[n]: bus_<side>[row] <-> rail.
        for mb in self.closed_bus_pwr_taps():
            label = f"cfg_bus_pwr[{mb.index}]"
            _add_edge(graph, bus_node(mb.bus, mb.row), mb.rail, label)

        # FET source ties: xpt_*_s <-> rail (see FET_SOURCE_TIE_TO_RAIL docs).
        for pin, (xpt, rail) in FET_SOURCE_TIE_TO_RAIL.items():
            if _single(self.bits, pin):
                _add_edge(graph, xpt, rail, pin)

        # Fixed physical bonds: always present, not gated by any bit.
        for ua_pin, (side, row) in EXTERNAL_PINS.items():
            _add_edge(graph, ua_pin, bus_node(side, row), f"{ua_pin} (bond wire)")
        _add_edge(graph, "ua[0]", "ibias", "ua[0] (bond wire)")

        return graph
