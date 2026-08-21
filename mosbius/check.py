# SPDX-License-Identifier: Apache-2.0
"""The circuit safety checker (SPEC.md Sec 3.1).

Runs on a SwitchConfig -- from a routed design or pasted in from anywhere,
including the web configurator -- and finds shorts, contention and other
hazards before a bitstream reaches real silicon.

Every finding follows SPEC.md Sec 1.1: state what happened, why the hardware
behaves that way, and what to try instead. A bare "short detected" teaches a
beginner nothing.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from mosbius.model import (
    DEVICE_DC_PATHS,
    DEVICE_TERMINALS,
    EXTERNAL_PINS,
    INDEPENDENT_FETS,
    TERMINAL_BY_CROSSPOINT,
    DeviceSettings,
    Edge,
    Graph,
    SwitchConfig,
    connected_components,
)

ERROR = "ERROR"
WARN = "WARN"
INFO = "INFO"

BUS_SEGMENTS = [f"bus_{side}[{row}]" for side in ("A", "B") for row in range(1, 7)]


@dataclass(frozen=True)
class Finding:
    code: str            # "E1".."E4", "W1".."W3", "I1"
    severity: str         # ERROR / WARN / INFO
    message: str          # full beginner-facing text, ready to print


@dataclass(frozen=True)
class SafetyReport:
    findings: list[Finding]

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == WARN]

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)


# ---------------------------------------------------------------------------
# Shortest-path for error reporting (connected_components() lives in model.py).
# ---------------------------------------------------------------------------

def _shortest_path(graph: Graph, start: str, end: str) -> list[tuple[str, str, str]] | None:
    """BFS shortest path start->end as a list of (from, label, to) hops."""
    if start == end:
        return []
    prev: dict[str, tuple[str, str]] = {}  # node -> (prev_node, label)
    seen = {start}
    q = deque([start])
    while q:
        node = q.popleft()
        for edge in graph.get(node, []):
            if edge.neighbor in seen:
                continue
            seen.add(edge.neighbor)
            prev[edge.neighbor] = (node, edge.label)
            if edge.neighbor == end:
                # reconstruct
                hops = []
                cur = end
                while cur != start:
                    p, label = prev[cur]
                    hops.append((p, label, cur))
                    cur = p
                hops.reverse()
                return hops
            q.append(edge.neighbor)
    return None


def format_path(hops: list[tuple[str, str, str]]) -> str:
    """Render a switch path the way SPEC.md Sec 1.1's example does:

        VAPWR --(cfg_bus_pwr[6])--  bus_B[6]
              --(cfg_bus_short[6])- bus_A[6]
              --(cfg_bus_pwr[3])--  VGND
    """
    if not hops:
        return ""
    start = hops[0][0]
    pad = " " * len(start)
    lines = [f"{start} --({hops[0][1]})--  {hops[0][2]}"]
    for _from, label, to in hops[1:]:
        lines.append(f"{pad} --({label})--  {to}")
    return "\n".join(f"    {line}" for line in lines)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_e1_supply_short(graph: Graph, comp: dict[str, int]) -> list[Finding]:
    if comp["VAPWR"] != comp["VGND"]:
        return []
    path = _shortest_path(graph, "VAPWR", "VGND")
    n = len(path)
    message = (
        f"DANGEROUS -- supply short\n\n"
        f"  VAPWR is joined to VGND through {n} closed switch{'es' if n != 1 else ''}:\n\n"
        f"{format_path(path)}\n\n"
        f"  This draws unlimited current from the 3.3V supply straight to ground.\n"
        f"  On real silicon that can damage the chip, so the upload is blocked.\n\n"
        f"  Why it happened: closing every switch on that path ties VAPWR and\n"
        f"  VGND together somewhere in the matrix -- often a bus_short switch\n"
        f"  joining a VAPWR-tapped row to a VGND-tapped one, or two rail taps\n"
        f"  landing on the same bus segment via different switches.\n\n"
        f"  To fix: open one of the switches on the path above -- moving the\n"
        f"  net to another row is usually enough."
    )
    return [Finding(code="E1", severity=ERROR, message=message)]


def _check_e2_ibias_short(graph: Graph, comp: dict[str, int]) -> list[Finding]:
    findings = []
    for rail in ("VAPWR", "VGND"):
        if comp["ibias"] != comp[rail]:
            continue
        path = _shortest_path(graph, "ibias", rail)
        message = (
            f"DANGEROUS -- ibias shorted to {rail}\n\n"
            f"  ibias (ua[0]) is joined to {rail} through {len(path)} closed switch"
            f"{'es' if len(path) != 1 else ''}:\n\n"
            f"{format_path(path)}\n\n"
            f"  ibias is a current *input* (SPEC.md Sec 3.4b) that biases every\n"
            f"  mirror and tail on the chip. Tying it to a rail forces whatever\n"
            f"  current source drives it directly into {rail}, and every device\n"
            f"  that depends on ibias loses its bias point.\n\n"
            f"  To fix: open one of the switches on the path above."
        )
        findings.append(Finding(code="E2", severity=ERROR, message=message))
    return findings


def _check_e3_driven_pin_into_rail(graph: Graph, comp: dict[str, int]) -> list[Finding]:
    findings = []
    for pin in ("ua[1]", "ua[2]", "ua[3]", "ua[4]", "ua[5]"):
        for rail in ("VAPWR", "VGND"):
            if comp[pin] != comp[rail]:
                continue
            path = _shortest_path(graph, pin, rail)
            message = (
                f"DANGEROUS -- {pin} shorted to {rail}\n\n"
                f"  {pin} is joined to {rail} through {len(path)} closed switch"
                f"{'es' if len(path) != 1 else ''}:\n\n"
                f"{format_path(path)}\n\n"
                f"  {pin} is a package pin the demoboard can drive as a stimulus.\n"
                f"  If it ever is, this path sends that drive straight into\n"
                f"  {rail} -- a hard short the demoboard's output stage may not\n"
                f"  survive.\n\n"
                f"  To fix: open one of the switches on the path above, or route\n"
                f"  this net through a different bus segment."
            )
            findings.append(Finding(code="E3", severity=ERROR, message=message))
    return findings


def _check_e4_pin_contention(graph: Graph, comp: dict[str, int]) -> list[Finding]:
    findings = []
    pins = ["ua[1]", "ua[2]", "ua[3]", "ua[4]", "ua[5]"]
    seen_pairs = set()
    for i, a in enumerate(pins):
        for b in pins[i + 1:]:
            if comp[a] != comp[b]:
                continue
            pair = (a, b)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            path = _shortest_path(graph, a, b)
            message = (
                f"DANGEROUS -- {a} and {b} are tied together\n\n"
                f"  They're joined through {len(path)} closed switch"
                f"{'es' if len(path) != 1 else ''}:\n\n"
                f"{format_path(path)}\n\n"
                f"  Both are package pins the demoboard can drive independently.\n"
                f"  If it ever drives them to different voltages, this path\n"
                f"  shorts them together.\n\n"
                f"  To fix: open one of the switches on the path above, or route\n"
                f"  these nets through different bus segments."
            )
            findings.append(Finding(code="E4", severity=ERROR, message=message))
    return findings


def _check_w1_shorted_channel(graph: Graph, comp: dict[str, int]) -> list[Finding]:
    findings = []
    for name in INDEPENDENT_FETS:
        d = DEVICE_TERMINALS[name]["d"]
        s = DEVICE_TERMINALS[name]["s"]
        if comp[d] != comp[s]:
            continue
        path = _shortest_path(graph, d, s)
        message = (
            f"WARNING -- {name}'s drain and source are tied together\n\n"
            f"  They're joined through {len(path)} closed switch"
            f"{'es' if len(path) != 1 else ''}:\n\n"
            f"{format_path(path) if path else f'    ({name}.d and {name}.s are the same net)'}\n\n"
            f"  This shorts out {name}'s channel -- current flows straight\n"
            f"  through instead of being modulated by the gate, so the\n"
            f"  transistor does nothing useful.\n\n"
            f"  To fix: route {name}'s drain and source to different nets."
        )
        findings.append(Finding(code="W1", severity=WARN, message=message))
    return findings


def _biasing_graph(graph: Graph, settings: DeviceSettings) -> Graph:
    """`graph` plus the DC paths that run *through* devices (model.py's
    DEVICE_DC_PATHS) rather than through the switch matrix.

    For W2 only. Every other check asks "are these shorted together", and
    a transistor channel is not a short -- add these edges to E1's graph
    and every working inverter becomes a VAPWR-VGND short.
    """
    augmented: Graph = {node: list(edges) for node, edges in graph.items()}
    for path in DEVICE_DC_PATHS:
        if path.setting is not None and not getattr(settings, path.setting):
            continue
        augmented.setdefault(path.a, []).append(Edge(neighbor=path.b, label=path.label))
        augmented.setdefault(path.b, []).append(Edge(neighbor=path.a, label=path.label))
    return augmented


def _terminal_name(node: str) -> str:
    return TERMINAL_BY_CROSSPOINT.get(node, node)


def _check_w2_floating_crosspoint(
    graph: Graph, comp: dict[str, int], settings: DeviceSettings,
) -> list[Finding]:
    """A net with no DC path to anything that pins its voltage.

    A rail obviously pins it. So does an external ua[] pin: those are
    listed alongside the rails as fixed nodes in SPEC.md Sec 3.1's graph
    model precisely because the demoboard can hold them at a defined
    voltage -- a gate or drain reachable only through ua[1] isn't floating,
    it's an ordinary input/output.

    So does a transistor channel that reaches a rail, which is why this
    runs against _biasing_graph() rather than the switch graph. Without
    that, every internal node of a multi-stage design fires: the output of
    an inverter reaches a rail only through its own two transistors, so on
    a 3-stage ring oscillator this check used to produce eight warnings,
    all false, telling the user to break their circuit. Nets are grouped
    too -- one finding per net, not one per crosspoint on it.

    What still fires, and should: a net whose terminals are all gates.
    Nothing can ever set its voltage.
    """
    bias = _biasing_graph(graph, settings)
    bias_comp = connected_components(bias)
    anchors = {"VAPWR", "VGND", *EXTERNAL_PINS}
    anchor_comps = {bias_comp[a] for a in anchors if a in bias_comp}

    # Group the wired crosspoints into nets, using the *switch* graph --
    # that is what "one net" means everywhere else (decode.py agrees).
    nets: dict[int, list[str]] = {}
    for node, edges in graph.items():
        if not node.startswith("xpt_") or not edges:
            continue  # unused crosspoint, not a floating one -- fine
        nets.setdefault(comp[node], []).append(node)

    findings = []
    for _cid, nodes in sorted(nets.items(), key=lambda kv: sorted(kv[1])):
        # The biasing graph is a superset, so every node here shares one
        # biasing component -- testing the first is testing all of them.
        if bias_comp[nodes[0]] in anchor_comps:
            continue
        terminals = sorted(_terminal_name(n) for n in nodes)
        names = ", ".join(terminals)
        if len(terminals) == 1:
            headline = f"WARNING -- nothing biases {names}"
            intro = "  It has a closed switch on it, but the net it sits on\n"
        else:
            headline = f"WARNING -- nothing biases the net joining {names}"
            intro = "  These terminals are wired together, but the net they form\n"

        if all(t.endswith((".g", ".inp", ".inm")) for t in terminals):
            why = (
                "  Every terminal on it is a gate, so nothing can set its\n"
                "  voltage -- there is no transistor channel to a rail here,\n"
                "  and no switch to one either.\n\n"
            )
        else:
            why = (
                "  Nothing reaches it: not a closed switch to a rail or a\n"
                "  ua[] pin, and not a transistor channel that gets to one\n"
                "  either (a drain only conducts to a rail if its own source\n"
                "  is tied to one).\n\n"
            )

        # If a diff-pair half is on this net, its untied tail is the whole
        # reason the channel leads nowhere -- and that is one bit to flip.
        untied = sorted({
            path.setting for path in DEVICE_DC_PATHS
            for node in nodes
            if path.a == node and path.setting and not getattr(settings, path.setting)
        })
        hint = ""
        if untied:
            bits = ", ".join(f"ctrl_{name}" for name in untied)
            hint = (
                f"\n\n  Most likely fix here: {bits} is off, so the shared\n"
                f"  diff-pair tail on this net's transistor is floating too. The\n"
                f"  tail has no matrix terminal of its own (SPEC.md Sec 2.12) --\n"
                f"  that bit is the only way to tie it to a rail, and with it set\n"
                f"  the half works as an ordinary common-source FET."
            )

        message = (
            f"{headline}\n\n"
            f"{intro}"
            f"  has no DC path to VAPWR, VGND, or a ua[] pin.\n\n"
            f"{why}"
            f"  In SPICE it floats and settles at an arbitrary voltage; on\n"
            f"  real silicon leakage pulls it somewhere uncontrolled, slowly.\n\n"
            f"  To fix: connect it to something that drives it -- a drain\n"
            f"  whose transistor has its source on a rail, a mirror output,\n"
            f"  or a ua[] pin you can drive from the demoboard.{hint}"
        )
        findings.append(Finding(code="W2", severity=WARN, message=message))
    return findings


def _check_w3_unconnected_terminal(graph: Graph) -> list[Finding]:
    findings = []
    for name, terminals in DEVICE_TERMINALS.items():
        used = [f"{name}.{t}" for t, xpt in terminals.items() if graph.get(xpt)]
        unused = [f"{name}.{t}" for t, xpt in terminals.items() if not graph.get(xpt)]
        if not used or not unused:
            continue
        message = (
            f"WARNING -- {name} is partly wired\n\n"
            f"  {', '.join(used)} {'has' if len(used) == 1 else 'have'} a closed\n"
            f"  switch, but {', '.join(unused)} {'is' if len(unused) == 1 else 'are'}\n"
            f"  left with no connection at all.\n\n"
            f"  A transistor with a floating terminal isn't doing the job it\n"
            f"  looks like it's doing -- an unconnected gate floats to an\n"
            f"  arbitrary voltage, an unconnected drain/source leaves the\n"
            f"  device conducting nowhere.\n\n"
            f"  To fix: either wire up {', '.join(unused)}, or remove {name}\n"
            f"  from the design if it isn't meant to be used."
        )
        findings.append(Finding(code="W3", severity=WARN, message=message))
    return findings


def _check_i1_sparse_bus(graph: Graph) -> list[Finding]:
    findings = []
    for seg in BUS_SEGMENTS:
        degree = len(graph.get(seg, []))
        if degree >= 2:
            continue
        count = "zero" if degree == 0 else "only one"
        message = (
            f"INFO -- {seg} does nothing\n\n"
            f"  {seg} has {degree} connection{'s' if degree != 1 else ''}. "
            f"A bus segment needs at least\n"
            f"  two (to actually join two things) to have any effect -- with "
            f"{count},\n"
            f"  this switch setting isn't wiring anything together."
        )
        findings.append(Finding(code="I1", severity=INFO, message=message))
    return findings


# ---------------------------------------------------------------------------

def check(config: SwitchConfig) -> SafetyReport:
    """Run every SPEC.md Sec 3.1 check against `config` and return the report."""
    graph = config.build_graph()
    comp = connected_components(graph)

    findings: list[Finding] = []
    findings += _check_e1_supply_short(graph, comp)
    findings += _check_e2_ibias_short(graph, comp)
    findings += _check_e3_driven_pin_into_rail(graph, comp)
    findings += _check_e4_pin_contention(graph, comp)
    findings += _check_w1_shorted_channel(graph, comp)
    findings += _check_w2_floating_crosspoint(graph, comp, config.device_settings())
    findings += _check_w3_unconnected_terminal(graph)
    findings += _check_i1_sparse_bus(graph)
    return SafetyReport(findings=findings)
