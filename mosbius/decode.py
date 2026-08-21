# SPDX-License-Identifier: Apache-2.0
"""Bitstream -> nets -> devices (SPEC.md Sec 3.8).

Decoding is deterministic where routing (M3) is a search: bits give switch
states directly (bitmap.py), closed switches give an electrical graph
(model.py), and connected components of that graph *are* the nets. No
allocation or capacity reasoning is needed to go this direction.

This is also the strongest available check on the bit map (SPEC.md Sec 3.8):
decoding a bitstream known to work on real silicon and getting the expected
circuit back confirms the map against physical reality, not against the SVG
it might otherwise have been derived from.
"""

from __future__ import annotations

from dataclasses import dataclass

from mosbius.model import DEVICE_TERMINALS, EXTERNAL_PINS, SwitchConfig, connected_components


@dataclass(frozen=True)
class Net:
    name: str
    nodes: frozenset[str]  # every graph node (bus segment, crosspoint, rail, pin) on this net


@dataclass(frozen=True)
class DeviceInstance:
    name: str  # "nfeta", "ndiffpair+", "otan", "mirn_a", ...
    terminals: dict[str, str]  # terminal name -> net name, only terminals actually wired
    settings: dict[str, object]  # the subset of DeviceSettings relevant to this device


@dataclass(frozen=True)
class DecodedDesign:
    nets: list[Net]
    devices: list[DeviceInstance]
    ibias: float


# Which DeviceSettings fields belong to each device, so the summary shows
# only what's relevant (SPEC.md Sec 2.11/2.12).
_DEVICE_SETTINGS_FIELDS: dict[str, dict[str, str]] = {
    "nfeta": {"width": "nfeta_width", "source_tied_to_VGND": "nfeta_source"},
    "nfetb": {"width": "nfetb_width", "source_tied_to_VGND": "nfetb_source"},
    "pfeta": {"width": "pfeta_width", "source_tied_to_VAPWR": "pfeta_source"},
    "pfetb": {"width": "pfetb_width", "source_tied_to_VAPWR": "pfetb_source"},
    "mirn_a": {"ratio": "mirn_a_ratio"},
    "mirn_b": {"ratio": "mirn_b_ratio"},
    "mirp_a": {"ratio": "mirp_a_ratio"},
    "mirp_b": {"ratio": "mirp_b_ratio"},
    "ndiffpair+": {"tail": "dpn_tail", "shared_source_tied_to_VGND": "dpn_source"},
    "ndiffpair-": {"tail": "dpn_tail", "shared_source_tied_to_VGND": "dpn_source"},
    "pdiffpair+": {"tail": "dpp_tail", "shared_source_tied_to_VAPWR": "dpp_source"},
    "pdiffpair-": {"tail": "dpp_tail", "shared_source_tied_to_VAPWR": "dpp_source"},
    "otan": {
        "tail": "otan_tail",
        "diode_connect_via_outp": "otan_mode0",
        "diode_connect_via_outm": "otan_mode1",
    },
}


def _net_name(nodes: frozenset[str], counter: list[int]) -> str:
    """Any node touching a rail or an external pin takes that name
    (SPEC.md Sec 3.8 step 4); everything else gets net1, net2, ...
    Priority: a rail identifies the net more fundamentally than a pin that
    merely happens to be wired onto it, so rails are checked first.
    """
    for rail in ("VAPWR", "VGND", "VDPWR"):
        if rail in nodes:
            return rail
    if "ibias" in nodes or "ua[0]" in nodes:
        return "ibias"
    for pin in EXTERNAL_PINS:
        if pin in nodes:
            return pin
    counter[0] += 1
    return f"net{counter[0]}"


def decode(config: SwitchConfig) -> DecodedDesign:
    graph = config.build_graph()
    comp = connected_components(graph)

    # Group nodes by component id.
    by_component: dict[int, set[str]] = {}
    for node, cid in comp.items():
        by_component.setdefault(cid, set()).add(node)

    counter = [0]
    net_by_component: dict[int, str] = {}
    nets: list[Net] = []
    # Deterministic order: rails/pins first (by their fixed identity), then
    # auto-numbered nets in an order derived from sorted node names, so
    # decode() is reproducible for a given config.
    for cid in sorted(by_component, key=lambda c: sorted(by_component[c])[0]):
        nodes = frozenset(by_component[cid])
        name = _net_name(nodes, counter)
        net_by_component[cid] = name
        nets.append(Net(name=name, nodes=nodes))

    crosspoint_to_net: dict[str, str] = {}
    for node, cid in comp.items():
        if node.startswith("xpt_"):
            crosspoint_to_net[node] = net_by_component[cid]

    settings = config.device_settings()
    devices: list[DeviceInstance] = []
    for dev_name, terminals in DEVICE_TERMINALS.items():
        wired = {
            t: crosspoint_to_net[xpt]
            for t, xpt in terminals.items()
            if graph.get(xpt)  # SPEC.md Sec 3.8 step 6: drop fully-isolated devices
        }
        if not wired:
            continue
        dev_settings = {
            label: getattr(settings, field_name)
            for label, field_name in _DEVICE_SETTINGS_FIELDS[dev_name].items()
        }
        devices.append(DeviceInstance(name=dev_name, terminals=wired, settings=dev_settings))

    return DecodedDesign(nets=nets, devices=devices, ibias=config.ibias)


# ---------------------------------------------------------------------------
# Readable summary (SPEC.md Sec 3.8 "Readable summary" output form).
# ---------------------------------------------------------------------------

def format_summary(decoded: DecodedDesign) -> str:
    lines = []
    if decoded.devices:
        lines.append("Devices in use")
        for dev in decoded.devices:
            terms = "  ".join(f"{t}={net}" for t, net in dev.terminals.items())
            settings = "  ".join(f"{k}={v}" for k, v in dev.settings.items())
            lines.append(f"  {dev.name:<11} {terms}  {settings}")
    else:
        lines.append("Devices in use\n  (none -- this config wires nothing to a live device)")

    # Only nets that actually carry a device terminal are worth showing --
    # SPEC.md Sec 3.8 step 6 drops fully-isolated devices for the same
    # reason: an unused crosspoint sitting in its own singleton "net"
    # because nothing touches it isn't useful to a reader.
    net_terminals: dict[str, list[str]] = {}
    for dev in decoded.devices:
        for t, net_name in dev.terminals.items():
            net_terminals.setdefault(net_name, []).append(f"{dev.name}.{t}")

    lines.append("")
    lines.append("Nets")
    for net in decoded.nets:
        if net.name not in net_terminals:
            continue
        pins = sorted(n for n in net.nodes if n in EXTERNAL_PINS)
        segs = sorted(n for n in net.nodes if n.startswith("bus_"))
        pin_desc = f"{pins[0]} ({segs[0]})  " if pins and segs else ""
        terms = "  ".join(net_terminals[net.name])
        lines.append(f"  {net.name:<8} {pin_desc}{terms}")

    lines.append("")
    lines.append(f"ibias = {decoded.ibias * 1e6:.1f} uA")
    return "\n".join(lines)
