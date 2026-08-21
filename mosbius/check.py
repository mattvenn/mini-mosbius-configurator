# SPDX-License-Identifier: Apache-2.0
"""The circuit safety checker (SPEC.md Sec 3.1).

Two entry points, because there are two things worth checking and they
see different information.

`check()` runs on a SwitchConfig -- from a routed design or pasted in from
anywhere, including the web configurator -- and finds shorts, contention
and other hazards before a bitstream reaches real silicon. It asks "is
this bitstream dangerous?", and it is the mandatory pre-upload gate.

`check_routing()` runs on what the router decided -- which role each
device became, and the width that role can actually be built at. It asks
"did the router have to quietly change your circuit?", which neither of
the other two can see: the netlist does not know the roles yet, and the
bitstream no longer knows what was asked for.

`check_design()` runs on a MosbiusDesign, i.e. on the netlist, *before*
routing. It asks "is this circuit wrong?" -- a question the switch graph
cannot answer, because a fault in the schematic can be gone by the time
the netlist is written (D1 below is exactly that case) and because a
design that fails to route never produces a SwitchConfig to check at all.

Every finding follows SPEC.md Sec 1.1: state what happened, why the hardware
behaves that way, and what to try instead. A bare "short detected" teaches a
beginner nothing.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from mosbius.netlist import IMPLICIT_PINS, MosbiusDesign
from mosbius.route import FIXED_GEOMETRY, DeviceWidth
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
# Design checks: these run on the netlist, not on a SwitchConfig.
# ---------------------------------------------------------------------------

# Which rail each FET kind's body sits on. This is a silicon fact, not a
# choice: the body is hard-wired on the chip, which is why the symbols
# supply it from their own template rather than from a drawn wire
# (mosbius_nmos.sym: template="... b=VGND", mosbius_pmos.sym: b=VAPWR,
# both with extra="b"). A FET's source belongs on the same rail.
BODY_RAIL = {"nmos": "VGND", "pmos": "VAPWR"}
OTHER_RAIL = {"VAPWR": "VGND", "VGND": "VAPWR"}

# Per-kind vocabulary for D1's messages: the shared diff-pair tail tie,
# the two independent slots, and the word the router's own "DOESN'T FIT"
# message uses -- so the two diagnostics visibly describe one situation.
_PAIR_TAIL_BIT = {"nmos": "ctrl_dpn_source", "pmos": "ctrl_dpp_source"}
_INDEPENDENT_SLOTS = {"nmos": "nmos_a and nmos_b", "pmos": "pmos_a and pmos_b"}
_ROUTER_LABEL = {"nmos": "NMOS", "pmos": "PMOS"}


def _name_list(devices: list) -> str:
    return ", ".join(d.name for d in devices)


def _why_it_costs_the_pair(kind: str, wrong_rail: str) -> str:
    """The paragraph that connects D1 to the failure the user actually saw.

    A source on the wrong rail does not merely look odd -- it makes the two
    diff-pair halves unusable, because their shared tail has no matrix
    terminal of its own and its one tie goes to the *right* rail. So the
    first thing the user sees is the allocator running out of transistors,
    which points at circuit size instead of at the wiring.
    """
    return (
        f"  It also costs you the two differential-pair halves. Their shared\n"
        f"  tail has no terminal on the switch matrix (SPEC.md Sec 2.12), so the\n"
        f"  only way to give it a voltage is {_PAIR_TAIL_BIT[kind]}, and that bit\n"
        f"  ties it to {OTHER_RAIL[wrong_rail]}. A half therefore cannot take a device whose\n"
        f"  source is on {wrong_rail}, which leaves only {_INDEPENDENT_SLOTS[kind]}. That is\n"
        f"  why this first shows up as \"DOESN'T FIT -- not enough "
        f"{_ROUTER_LABEL[kind]} with\n  independent sources\".\n\n"
    )


def _check_d1_source_on_wrong_rail(design: MosbiusDesign) -> list[Finding]:
    """A FET whose source sits on the rail opposite its own body.

    Two readings, distinguished by whether the correct rail appears
    anywhere else in the design:

    - It appears nowhere. Then the two rails were wired together in the
      schematic: xschem merged them into one net, kept one of the two
      names, and every wire of the other name came back renamed. The body
      is the one connection that cannot be merged -- it is a template
      string, not a wire -- so it still reads the original rail, and that
      disagreement is the only surviving trace of the short. ERROR: the
      circuit as drawn ties 3.3V to ground.

    - It appears elsewhere. Then the rails are fine and these particular
      devices are wired wrongly, usually a vertically flipped symbol.
      WARN, not ERROR: the router *can* reach the opposite rail from a
      source terminal through a bus row and a cfg_bus_pwr tap, so this is
      routable, just almost certainly not what was meant. Same reasoning
      as TODO.md Sec 9 keeps the drain/source-swap hint a hint.
    """
    wired_nets = {
        net
        for d in design.devices
        for terminal, net in d.terminals.items()
        if terminal not in IMPLICIT_PINS
    }

    findings = []
    for kind in ("nmos", "pmos"):
        home = BODY_RAIL[kind]
        wrong = OTHER_RAIL[home]
        offenders = [
            d for d in design.devices
            if d.kind == kind and d.terminals.get("s") == wrong
        ]
        if not offenders:
            continue

        names = _name_list(offenders)
        n = len(offenders)
        if n == 1:
            subject = f"  {names} is a mosbius_{kind} with its source on {wrong}"
        else:
            subject = (
                f"  {n} of your mosbius_{kind} devices have their source on "
                f"{wrong}:\n    {names}"
            )

        if home not in wired_nets:
            message = (
                f"DANGEROUS -- VAPWR and VGND are joined somewhere in your schematic\n\n"
                f"{subject}\n\n"
                f"  Meanwhile {home} does not appear on a single device terminal\n"
                f"  anywhere in this netlist.\n\n"
                f"  Why that combination means the rails are shorted: a "
                f"mosbius_{kind}'s\n"
                f"  body is hard-wired to {home} on silicon, and its source belongs on\n"
                f"  that same rail. The body still reads {home} here because it is not a\n"
                f"  wire you drew -- it comes from the symbol's own template\n"
                f"  (mosbius_{kind}.sym, template=\"... b={home}\" with extra=\"b\"), so it\n"
                f"  is the one connection xschem cannot merge with anything else.\n"
                f"  Everything you did draw as {home} came back as {wrong} instead.\n\n"
                f"  That is what happens when the two rails are wired together: xschem\n"
                f"  merges them into a single net, keeps one of the two names, and the\n"
                f"  short itself vanishes from the netlist before this tool ever sees\n"
                f"  it. Nothing here can find it by looking at connectivity, because\n"
                f"  by then there is only one rail left to look at.\n\n"
                f"  On real silicon this ties the 3.3V supply straight to ground and\n"
                f"  draws unlimited current, so nothing is routed or uploaded from\n"
                f"  here.\n\n"
                f"  To fix: find the wire joining {wrong} and {home} in your schematic,\n"
                f"  delete it, and press Netlist again. Both rail names should then be\n"
                f"  back on the terminals you drew them on."
            )
            findings.append(Finding(code="D1", severity=ERROR, message=message))
            continue

        message = (
            f"WARNING -- source on {wrong} where {home} is expected\n\n"
            f"{subject}.\n"
            f"  A mosbius_{kind}'s body is hard-wired to {home} on silicon "
            f"(that is what\n"
            f"  mosbius_{kind}.sym's template=\"... b={home}\" records), and its source\n"
            f"  belongs on the same rail.\n\n"
            f"{_why_it_costs_the_pair(kind, wrong)}"
            f"  The usual cause is a symbol flipped vertically: mosbius_nmos has its\n"
            f"  source at the bottom and its drain at the top, and mosbius_pmos is\n"
            f"  the other way up.\n\n"
            f"  This is a warning rather than a hard stop because the router can\n"
            f"  still reach {wrong} from a source terminal, through a bus row and a\n"
            f"  cfg_bus_pwr tap -- so the circuit may well route. It just probably\n"
            f"  is not the circuit you meant to draw.\n\n"
            f"  To fix: wire the source of {names} to {home}."
        )
        findings.append(Finding(code="D1", severity=WARN, message=message))

    return findings


def _check_r1_width_dropped(device_widths: dict[str, DeviceWidth],
                            device_roles: dict[str, str]) -> list[Finding]:
    """A width the schematic asked for that the assigned role cannot carry
    (TODO.md Sec 5).

    The diff-pair halves have no width bits -- their geometry is fixed in
    silicon -- so a device the allocator puts on one keeps its w= in the
    netlist, has it ignored in the bitstream, and used to be told nothing.
    The reason that is worth a warning rather than a footnote is the value
    it is dropped *to*: a half is the equivalent of w=4, not w=1, so a
    schematic that looks symmetric is built asymmetric.
    """
    findings = []
    for name in sorted(device_widths):
        width = device_widths[name]
        if not width.dropped:
            continue
        role = device_roles[name]
        geometry = FIXED_GEOMETRY.get(role, "a geometry fixed in silicon")
        kind = "NMOS" if role.startswith("n") else "PMOS"
        prog = "nmos_prog.sch" if kind == "NMOS" else "pmos_prog.sch"
        message = (
            f"WARNING -- {name}'s {width.prop}={width.requested} was ignored: "
            f"{role} has a fixed width\n\n"
            f"  The router put {name} on {role}, one of the two halves of the\n"
            f"  {kind} differential pair. Those halves have no width bits on the\n"
            f"  chip -- their geometry is built in silicon -- so there is nothing\n"
            f"  in the bitstream that could carry {width.prop}={width.requested}, "
            f"and it was dropped.\n\n"
            f"  What you get instead is {width.prop}={width.effective}. A half is "
            f"{geometry},\n"
            f"  which is exactly the geometry of a programmable FET at its maximum\n"
            f"  {width.prop}={width.effective} ({prog}'s 1x always-on slice plus its "
            f"switchable 1x\n  and 2x slices).\n\n"
            f"  Why this matters: it is built at {width.prop}={width.effective} "
            f"where your schematic says\n"
            f"  {width.prop}={width.requested}. In a circuit that looks symmetric "
            f"-- the three stages of a\n"
            f"  ring oscillator, say -- the stages that land on the programmable\n"
            f"  FETs come out at the width you asked for and this one does not, and\n"
            f"  the mismatch exists only on silicon, not in the drawing.\n\n"
            f"  To fix: set the other devices of the same kind to "
            f"{width.prop}={width.effective} as well, so\n"
            f"  every stage matches deliberately -- examples/ringosc/README.md does\n"
            f"  exactly that. They match in W/L, though not in parasitics: the\n"
            f"  programmable FET's 1x and 2x slices sit behind drain switches and\n"
            f"  the diff-pair half does not."
        )
        findings.append(Finding(code="R1", severity=WARN, message=message))
    return findings


def check_routing(routed) -> SafetyReport:
    """Run the post-routing checks against a RoutedDesign.

    Typed loosely on purpose: this only needs `.device_widths` and
    `.device_roles`, and taking the object by duck type keeps check.py
    from importing the router's result class.
    """
    return SafetyReport(
        findings=_check_r1_width_dropped(routed.device_widths, routed.device_roles)
    )


def check_design(design: MosbiusDesign) -> SafetyReport:
    """Run the netlist-level checks against `design`, before routing."""
    return SafetyReport(findings=_check_d1_source_on_wrong_rail(design))


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
