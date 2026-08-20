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
# expose a source terminal (it's shared/internal, SPEC.md Sec 2.12) -- dpn+/
# dpp+ read the netlist's "inp"/"outp" as g/d, dpn-/dpp- read "inm"/"outm"
# as g/d. The 4 current mirrors expose one terminal, named "out". The OTA is
# used as one 5-transistor block with 4 terminals.
DEVICE_TERMINALS: dict[str, dict[str, str]] = {
    "nfeta": {"d": "xpt_nfeta_d", "g": "xpt_nfeta_g", "s": "xpt_nfeta_s"},
    "nfetb": {"d": "xpt_nfetb_d", "g": "xpt_nfetb_g", "s": "xpt_nfetb_s"},
    "pfeta": {"d": "xpt_pfeta_d", "g": "xpt_pfeta_g", "s": "xpt_pfeta_s"},
    "pfetb": {"d": "xpt_pfetb_d", "g": "xpt_pfetb_g", "s": "xpt_pfetb_s"},
    "dpn+": {"g": "xpt_dpn_inp", "d": "xpt_dpn_outp"},
    "dpn-": {"g": "xpt_dpn_inm", "d": "xpt_dpn_outm"},
    "dpp+": {"g": "xpt_dpp_inp", "d": "xpt_dpp_outp"},
    "dpp-": {"g": "xpt_dpp_inm", "d": "xpt_dpp_outm"},
    "mirn_a": {"out": "xpt_mirn_a"},
    "mirn_b": {"out": "xpt_mirn_b"},
    "mirp_a": {"out": "xpt_mirp_a"},
    "mirp_b": {"out": "xpt_mirp_b"},
    "otan": {
        "inp": "xpt_otan_inp", "outp": "xpt_otan_outp",
        "inm": "xpt_otan_inm", "outm": "xpt_otan_outm",
    },
}

# The 4 devices with an independently-routable source, for W1 (SPEC.md
# Sec 2.12: "eight FETs are freely usable singly").
INDEPENDENT_FETS = ("nfeta", "nfetb", "pfeta", "pfetb")

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
# Device settings: decode the raw cycler/toggle bits into named values.
# ---------------------------------------------------------------------------

# SPEC.md Sec 2.11: n = step * (1 + b_lsb + 2*b_msb). This formula is total
# and bijective over the 4 raw (b_lsb, b_msb) combinations for both step=1
# (n in 1..4) and step=2 (n in {2,4,6,8}) -- every raw bit pattern decodes to
# a valid setting, there is no "invalid cycler value".
def _decode_cycler(bits: dict[int, DeviceSettingBit], pin: str, step: int) -> int:
    lsb = 1 if _bit_for(bits, pin, 0) else 0
    msb = 1 if _bit_for(bits, pin, 1) else 0
    return step * (1 + lsb + 2 * msb)


# Index bit -> (pin, index) once, up front, instead of re-scanning
# DEVICE_SETTING_BITS on every field lookup.
_SETTING_BIT_BY_PIN_INDEX: dict[tuple[str, int], int] = {
    (sb.pin, sb.index): bit for bit, sb in DEVICE_SETTING_BITS.items()
}


def _bit_for(pin: str, index: int) -> int:
    try:
        return _SETTING_BIT_BY_PIN_INDEX[(pin, index)]
    except KeyError:
        raise KeyError(f"no bit found for {pin}[{index}]") from None


def _single(closed: frozenset[int], pin: str) -> bool:
    return _bit_for(pin, 0) in closed


def _decode_cycler(closed: frozenset[int], pin: str, step: int) -> int:
    lsb = 1 if _bit_for(pin, 0) in closed else 0
    msb = 1 if _bit_for(pin, 1) in closed else 0
    return step * (1 + lsb + 2 * msb)


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
            otan_mode0=_bit_for("ctrl_otan_mode", 0) in closed,
            otan_mode1=_bit_for("ctrl_otan_mode", 1) in closed,
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
