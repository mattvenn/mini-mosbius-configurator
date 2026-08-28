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

import textwrap
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

from mosbius.netlist import IMPLICIT_PINS, PORT_NAMES, MosbiusDesign
from mosbius.route import FIXED_GEOMETRY, DeviceTail, DeviceWidth
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
    message: str          # full beginner-facing text for THIS finding alone, ready to print

    # The two fields below exist only so several near-identical findings can
    # be shown as one (TODO.md was Sec 3, closed 2026-08-22): a check that
    # fires on N similar devices still returns N Findings -- `program.py`'s
    # gate and every test that counts by code depends on that -- but a
    # display layer (merge_findings() below) can collapse a same-`merge_key`
    # group into a single re-rendered block naming every `subject`, instead
    # of printing the same explanation N times. Both default to "never
    # merges", so every check that doesn't opt in is completely unaffected.
    subject: str = ""                                    # this finding's short id, e.g. "XM5"
    merge_key: tuple | None = None                        # same (code, merge_key) => mergeable
    render: Callable[[list[str]], str] | None = field(default=None, repr=False, compare=False)
    # render(subjects) rebuilds the message for an arbitrary nonempty list of
    # subjects, correctly pluralised -- render([this.subject]) == this.message.


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


def _join_and(items: list[str]) -> str:
    """'A', 'A and B', or 'A, B and C' -- the natural-language list join
    used everywhere a merged finding names several subjects at once."""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + f" and {items[-1]}"


# Message bodies are wrapped here rather than by hand. A merged finding's
# first sentence names every subject, so its length depends on how many
# devices or segments merged -- hand-placed newlines were chosen for the
# one-subject case and left that first line running to 127 characters in
# an empty config's I1 block, against a body wrapped at 68.
_WIDTH = 74


def _wrap(prefix: str, headline: str, *paragraphs: str) -> str:
    """`prefix` is the severity tag ("INFO -- "); continuation lines of the
    headline hang under the text, not the tag. Body paragraphs are indented
    two spaces and separated by a blank line."""
    out = [textwrap.fill(prefix + headline, width=_WIDTH,
                         subsequent_indent=" " * len(prefix))]
    out += [textwrap.fill(par, width=_WIDTH,
                          initial_indent="  ", subsequent_indent="  ")
            for par in paragraphs]
    return "\n\n".join(out)


def merge_findings(findings: list[Finding]) -> list[Finding]:
    """Collapse findings sharing (code, merge_key) into one, naming every
    subject and explaining once (TODO.md was Sec 3, closed 2026-08-22) --
    the SR latch used to print two near-identical 23-line R1 warnings, 21
    of those lines identical.

    Display-only: `findings` (and hence `SafetyReport.findings`) keeps one
    entry per offending device -- `program.py`'s gate and every per-code
    test depend on that -- so this runs at the point a report is about to
    be printed (`cli.py`'s `_format_report`, `watch.py`'s `_report`), not
    inside a check function. A finding with `merge_key=None` (every check
    that hasn't opted in) always passes through unchanged, alone in its
    own group of one. Order is first-occurrence, same as the input.
    """
    groups: dict[tuple[str, tuple], list[Finding]] = {}
    order: list[Finding | tuple[str, tuple]] = []
    for f in findings:
        if f.merge_key is None:
            order.append(f)
            continue
        key = (f.code, f.merge_key)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(f)

    merged = []
    for item in order:
        if isinstance(item, Finding):
            merged.append(item)
            continue
        group = groups[item]
        if len(group) == 1:
            merged.append(group[0])
            continue
        subjects = [f.subject for f in group]
        text = group[0].render(subjects)
        merged.append(Finding(code=group[0].code, severity=group[0].severity, message=text))
    return merged


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


def _render_i1(subjects: list[str], detail: dict[str, tuple[str, str | None]]) -> str:
    """The I1 explanation for one or several bus segments at once.

    Every subject is a segment with fewer than the two connections it
    needs, so this renders a single block however those connections are
    mixed, and gives the reason once. Grouping by raw connection count
    (the first cut at TODO.md was Sec 3, closed 2026-08-22) printed the
    same explanation twice over, differing only in "with zero" versus
    "with only one".

    A segment's one connection is spelled out rather than counted,
    because the usual reason a segment sits at one is its package-pin
    bond wire -- permanent silicon the schematic never drew. Reporting
    that as "has only one connection" reads as a plain error to someone
    who connected nothing to it: they are right that their circuit put
    nothing there, and the message has to say where the connection came
    from, not just how many there are.
    """
    empty = [seg for seg in subjects if detail[seg][0] == "none"]
    bonded = [seg for seg in subjects if detail[seg][0] == "bond"]
    wired = [seg for seg in subjects if detail[seg][0] == "switch"]

    sentences = []
    if empty:
        verb = "has" if len(empty) == 1 else "have"
        sentences.append(f"{_join_and(empty)} {verb} nothing connected to "
                         f"{'it' if len(empty) == 1 else 'them'} at all.")
    if bonded:
        pins = _join_and([detail[seg][1] for seg in bonded])
        if len(bonded) == 1:
            sentences.append(
                f"{bonded[0]} is connected only to its package pin ({pins}) -- "
                f"that bond wire is part of the chip rather than something "
                f"the schematic added, so it joins the segment to nothing else.")
        else:
            sentences.append(
                f"{_join_and(bonded)} are connected only to their package pins "
                f"({pins}) -- those bond wires are part of the chip rather "
                f"than something the schematic added, so each joins its "
                f"segment to nothing else.")
    if wired:
        verb = "has" if len(wired) == 1 else "have"
        each = "" if len(wired) == 1 else " each"
        sentences.append(f"{_join_and(wired)} {verb} just one connection{each}.")

    plural = len(subjects) > 1
    headline = f"{_join_and(subjects)} {'do' if plural else 'does'} nothing"
    consequence = ("none of these segments is" if plural else "this segment isn't")
    return _wrap(
        "INFO -- ", headline,
        " ".join(sentences),
        "A bus segment needs at least two connections (to actually join two "
        f"things) to have any effect, so {consequence} wiring anything "
        f"together.",
    )


def _check_i1_sparse_bus(graph: Graph) -> list[Finding]:
    def classify(seg: str) -> tuple[str, str | None]:
        """What the segment's single connection actually is -- a package-pin
        bond wire is silicon, and saying so is the difference between a
        useful note and one that looks wrong to whoever drew the circuit."""
        edges = graph.get(seg, [])
        if not edges:
            return ("none", None)
        if len(edges) == 1 and edges[0].label.endswith("(bond wire)"):
            return ("bond", edges[0].neighbor)
        return ("switch", None)

    detail = {seg: classify(seg) for seg in BUS_SEGMENTS}
    sparse = [seg for seg in BUS_SEGMENTS if len(graph.get(seg, [])) < 2]

    def render(subjects: list[str]) -> str:
        return _render_i1(subjects, detail)

    # One merge group for every sparse segment, whatever it is connected
    # to: _render_i1 describes each kind separately and explains once.
    return [Finding(
        code="I1", severity=INFO, message=render([seg]),
        subject=seg, merge_key=(), render=render,
    ) for seg in sparse]


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

# The free source-to-rail ties, for D2: naming them is what makes "it
# costs a bus row" checkable rather than something to take on trust.
SOURCE_TIE_EXAMPLE = {
    "nmos": "ctrl_nfeta_source / ctrl_nfetb_source",
    "pmos": "ctrl_pfeta_source / ctrl_pfetb_source",
}


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
      as D2 below keeps the drain/source-swap hint a hint.
    """
    wired_nets = {
        net
        for d in design.devices
        for terminal, net in d.terminals.items()
        if (d.kind, terminal) not in IMPLICIT_PINS
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


def _check_d2_drain_and_source_swapped(design: MosbiusDesign) -> list[Finding]:
    """A FET whose drain sits on its own body's rail while its source sits
    on an ordinary internal net -- almost always a symbol drawn upside
    down, with drain and source exchanged.

    Worth a check of its own because of how it presents. The allocator
    sees a perfectly ordinary request -- a transistor whose source has to
    be routed somewhere -- and there are only two FETs per polarity whose
    source can go anywhere, so three of these come back as "DOESN'T FIT --
    not enough PMOS with independent sources". Every word of that is true
    and every word points at the size of the circuit instead of at the
    wiring. This costs 15 minutes to unpick from the message alone.

    A hint rather than an error, and deliberately narrow: a source on an
    internal net is exactly right in a cascode or a source follower, so it
    fires only when the *drain* is on the matching rail as well, which is
    the combination with no sensible reading. Narrow in one more way: a
    source on a `ua[]` pin is left alone too, so the reversed inverter in
    examples/inverter/README.md (output on ua2) still passes silently.
    That case costs a bus row rather than the circuit, and with a package
    pin in play there are shapes that legitimately look like this.

    It lives here, in the netlist-level checks, rather than on the
    allocator's failure path, so it also fires on a design small enough to
    route.
    """
    findings = []
    for kind in ("nmos", "pmos"):
        rail = BODY_RAIL[kind]
        offenders = [
            d for d in design.devices
            if d.kind == kind
            and d.terminals.get("d") == rail
            and d.terminals.get("s") not in PORT_NAMES
        ]
        if not offenders:
            continue

        names = _name_list(offenders)
        nets = ", ".join(sorted({f"'{d.terminals['s']}'" for d in offenders}))
        n = len(offenders)
        if n == 1:
            subject = (
                f"  {names} is a mosbius_{kind} with its drain on {rail} and its\n"
                f"  source on {nets}, an ordinary net inside your circuit."
            )
        else:
            subject = (
                f"  {n} of your mosbius_{kind} devices have their drain on {rail} "
                f"and their\n  source on an ordinary net inside your circuit "
                f"({nets}):\n    {names}"
            )

        top, bottom = ("source", "drain") if kind == "pmos" else ("drain", "source")
        message = (
            f"WARNING -- drain and source look swapped on {names}\n\n"
            f"{subject}\n\n"
            f"  That is back to front for a common-source transistor. A "
            f"mosbius_{kind}'s\n  source belongs on {rail} -- the rail its body is "
            f"hard-wired to on\n  silicon -- and its drain is the end that drives "
            f"the rest of the\n  circuit. As drawn, these two are the other way "
            f"round.\n\n"
            f"  Why it is worth saying: nothing downstream can tell a reversed\n"
            f"  transistor from a deliberate one, so the request is taken at face\n"
            f"  value and costs you something either way.\n\n"
            f"  It costs a bus row even when it routes. Only the *source* terminal\n"
            f"  has a free tie to its rail:\n"
            f"    {SOURCE_TIE_EXAMPLE[kind]}\n"
            f"  With the source on an internal net that tie is unusable, so "
            f"reaching\n  {rail} from the drain instead has to spend a bus row and "
            f"a cfg_bus_pwr\n  tap.\n\n"
            f"  And it can cost you the circuit. The chip has only two "
            f"{kind.upper()} whose\n  source can be routed anywhere at all, so once "
            f"there are more than two\n  such requests the allocator gives up:\n"
            f"    \"DOESN'T FIT -- not enough {kind.upper()} with independent "
            f"sources\"\n"
            f"  which points at the size of your circuit rather than at the "
            f"wiring.\n\n"
            f"  The usual cause is a symbol flipped vertically: mosbius_{kind} has "
            f"its\n  {top} at the top and its {bottom} at the bottom, the opposite "
            f"way up\n  from mosbius_{'nmos' if kind == 'pmos' else 'pmos'}. A "
            f"schematic drawn before 2026-08-21 used the\n  older pin geometry, so "
            f"a symbol copied from one comes out reversed.\n\n"
            f"  This is a hint, not a hard stop: a source on an internal net is\n"
            f"  exactly right in a cascode or a source follower. It is flagged only\n"
            f"  because the drain is on {rail} as well, and that combination has no\n"
            f"  sensible reading.\n\n"
            f"  To fix: swap the two connections on {names}, so the source goes to\n"
            f"  {rail} and the drain carries the signal."
        )
        findings.append(Finding(code="D2", severity=WARN, message=message))

    return findings


# Per-kind vocabulary for D3/D4's messages (TODO.md was Sec 2, closed
# 2026-08-22): the FET kind a
# drawn tail's halves must be, the rail its drain must *not* be wired to,
# the bitstream field its tail= actually reaches, and its own symbol name.
_TAIL_FET_KIND = {"ntail": "nmos", "ptail": "pmos"}
_TAIL_RAIL = {"ntail": "VGND", "ptail": "VAPWR"}
_TAIL_BIT = {"ntail": "ctrl_dpn_tail", "ptail": "ctrl_dpp_tail"}
_TAIL_SYMBOL = {"ntail": "mosbius_ntail", "ptail": "mosbius_ptail"}


def _check_d3_tail_wrong_arity(design: MosbiusDesign) -> list[Finding]:
    """A drawn tail bank whose drain net isn't shared by exactly two
    same-polarity FET sources.

    Drawing a mosbius_ntail/mosbius_ptail declares a pair: the router
    claims the two FETs sourced on its drain net as the pair's two
    halves instead of inferring the pairing (TODO.md was Sec 2, closed
    2026-08-22). Anything
    other than exactly two leaves that declaration unable to mean
    anything -- zero or one means there is no pair to bias, three or
    more means the router cannot tell which two you meant.

    Skips a tail wired straight to its own rail -- D4 covers that with a
    more specific message, and it would otherwise also read as "wrong
    arity" here purely by coincidence of what else happens to share that
    rail.
    """
    findings = []
    for kind, fet_kind in _TAIL_FET_KIND.items():
        for tail in design.devices:
            if tail.kind != kind:
                continue
            node = tail.terminals["d"]
            if node == _TAIL_RAIL[kind]:
                continue
            halves = [
                d for d in design.devices
                if d.kind == fet_kind and d.terminals.get("s") == node
            ]
            if len(halves) == 2:
                continue

            symbol = _TAIL_SYMBOL[kind]
            fet_symbol = "mosbius_nmos" if fet_kind == "nmos" else "mosbius_pmos"
            if not halves:
                found = f"nothing else in the design has its source on '{node}'"
            else:
                found = (
                    f"{len(halves)} {fet_symbol} devices have their source there: "
                    f"{_name_list(halves)}"
                )
            message = (
                f"ERROR -- {tail.name}'s drain doesn't declare a pair\n\n"
                f"  {tail.name} is a {symbol}, and its drain is wired to "
                f"'{node}'.\n  Drawing a {symbol} declares that net's two "
                f"{fet_symbol} devices as a\n  differential pair -- but {found}.\n\n"
                f"  A {symbol} needs exactly two {fet_symbol} devices sharing its\n"
                f"  drain net as their source: those become the pair, and "
                f"{tail.name}'s\n  tail= reaches their shared tail current "
                f"({_TAIL_BIT[kind]}).\n\n"
                f"  To fix: wire {tail.name}'s drain to the shared source of "
                f"exactly two\n  {fet_symbol} devices, or remove {tail.name} if "
                f"you didn't mean to\n  draw a pair here."
            )
            findings.append(Finding(code="D3", severity=ERROR, message=message))
    return findings


def _check_d4_tail_on_rail(design: MosbiusDesign) -> list[Finding]:
    """A drawn tail bank whose drain is wired straight to its own rail.

    The tail bank's output is a genuine internal node -- the diff pair's
    shared source, which has no matrix terminal of its own (SPEC.md Sec
    2.12) -- never the rail itself. The rail-tie bit (ctrl_dp{n,p}_source)
    and the tail bank (ctrl_dp{n,p}_tail) are two different ways to bias
    that *same* node, and drawing a tail already picked the bank -- wiring
    its drain to the rail asks for both at once, which the hardware
    cannot do (TODO.md was Sec 2, closed 2026-08-22: "one or the other,
    never both").
    """
    findings = []
    for kind, rail in _TAIL_RAIL.items():
        offenders = [d for d in design.devices if d.kind == kind and d.terminals["d"] == rail]
        if not offenders:
            continue
        symbol = _TAIL_SYMBOL[kind]
        for tail in offenders:
            message = (
                f"ERROR -- {tail.name}'s drain is wired straight to {rail}\n\n"
                f"  {tail.name} is a {symbol}, and its drain -- the node its "
                f"tail bank\n  feeds -- is wired directly to {rail} instead of "
                f"to a genuine internal\n  net.\n\n"
                f"  That node is never the rail itself: it is the diff pair's "
                f"shared\n  source, which has no matrix terminal of its own "
                f"(SPEC.md Sec 2.12).\n  {_TAIL_BIT[kind]} (what {tail.name}'s "
                f"tail= sets) and the rail-tie bit\n  are two different ways to "
                f"bias that one node, and they are\n  alternatives, never both "
                f"at once.\n\n"
                f"  To fix: wire {tail.name}'s drain to the pair halves' actual\n"
                f"  shared source net, not to {rail}. If you meant the halves "
                f"tied\n  straight to {rail} instead (CLAUDE.md Traps #3), "
                f"remove {tail.name}\n  and wire their sources to {rail} "
                f"directly."
            )
            findings.append(Finding(code="D4", severity=ERROR, message=message))
    return findings


def _render_r1(subjects: list[str], device_roles: dict[str, str], prop: str,
                requested: int, effective: int, kind: str, geometry: str, prog: str) -> str:
    """The R1 explanation for one or several devices at once (TODO.md was
    Sec 3, closed 2026-08-22). Only the headline and the intro's first
    clause ever name a device/role -- everything from "Those halves..."
    onward is already subject-independent, so it appears once regardless
    of how many devices triggered this.

    Paragraphs are written unwrapped and `_wrap` breaks them, because the
    intro's length depends on how many devices merged: hand-placed
    newlines sized for one device left that line at 80 characters in the
    SR latch's two-device warning, against a body wrapped at 68.
    """
    roles = [device_roles[s] for s in subjects]
    if len(subjects) == 1:
        name, role = subjects[0], roles[0]
        headline = f"{name}'s {prop}={requested} was ignored: {role} has a fixed width"
        intro = f"The router put {name} on {role}, one of the two halves of the"
    else:
        names, role_list = _join_and(subjects), _join_and(roles)
        headline = (f"{names} had their {prop}={requested} ignored: "
                    f"{role_list} have a fixed width")
        intro = f"The router put {names} on {role_list}, the two halves of the"
    return _wrap(
        "WARNING -- ", headline,
        f"{intro} {kind} differential pair. Those halves have no width bits "
        f"on the chip -- their geometry is built in silicon -- so there is "
        f"nothing in the bitstream that could carry {prop}={requested}, and "
        f"it was dropped.",
        f"What you get instead is {prop}={effective}. A half is {geometry}, "
        f"which is exactly the geometry of a programmable FET at its maximum "
        f"{prop}={effective} ({prog}'s 1x always-on slice plus its switchable "
        f"1x and 2x slices).",
        f"Why this matters: it is built at {prop}={effective} where your "
        f"schematic says {prop}={requested}. In a circuit that looks "
        f"symmetric -- the three stages of a ring oscillator, say -- the "
        f"stages that land on the programmable FETs come out at the width "
        f"you asked for and this one does not, and the mismatch exists only "
        f"on silicon, not in the drawing.",
        f"To fix: set the other devices of the same kind to {prop}="
        f"{effective} as well, so every stage matches deliberately -- "
        f"examples/ringosc/README.md does exactly that. They match in W/L, "
        f"though not in parasitics: the programmable FET's 1x and 2x slices "
        f"sit behind drain switches and the diff-pair half does not.",
    )


def _check_r1_width_dropped(device_widths: dict[str, DeviceWidth],
                            device_roles: dict[str, str]) -> list[Finding]:
    """A width the schematic asked for that the assigned role cannot carry
    (the silently-dropped-width item, now closed).

    The diff-pair halves have no width bits -- their geometry is fixed in
    silicon -- so a device the allocator puts on one keeps its w= in the
    netlist, has it ignored in the bitstream, and used to be told nothing.
    The reason that is worth a warning rather than a footnote is the value
    it is dropped *to*: a half is the equivalent of w=4, not w=1, so a
    schematic that looks symmetric is built asymmetric.

    A design's two halves of one pair trigger this identically (same
    requested/effective width, same polarity) and are exactly the case
    `merge_findings` exists for -- but NMOS and PMOS halves never merge
    with each other, since their geometry differs (`kind` is part of the
    key), and neither do two pairs that asked for different widths.
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

        def render(subjects: list[str], _dr=device_roles, _p=width.prop,
                   _rq=width.requested, _ef=width.effective, _k=kind, _g=geometry,
                   _pr=prog) -> str:
            return _render_r1(subjects, _dr, _p, _rq, _ef, _k, _g, _pr)

        findings.append(Finding(
            code="R1", severity=WARN, message=render([name]),
            subject=name, merge_key=(width.prop, width.requested, width.effective, kind),
            render=render,
        ))
    return findings


def _render_r2(subjects: list[str], device_roles: dict[str, str], requested: int) -> str:
    """The R2 explanation for one or several devices at once -- same shape
    as `_render_r1`, including letting `_wrap` place the line breaks: only
    the headline and the intro's first clause ever name a device/role.
    """
    roles = [device_roles[s] for s in subjects]
    if len(subjects) == 1:
        name, role = subjects[0], roles[0]
        headline = f"{name}'s tail={requested} was ignored: {role} has no tail current"
        intro = (f"The router put {name} on {role}, which has no tail-current "
                 f"bit of its own")
    else:
        names, role_list = _join_and(subjects), _join_and(roles)
        headline = (f"{names} had their tail={requested} ignored: "
                    f"{role_list} have no tail current")
        intro = (f"The router put {names} on {role_list}, which have no "
                 f"tail-current bit of their own")
    return _wrap(
        "WARNING -- ", headline,
        f"{intro}, so there is nothing here for tail= to set and it was "
        f"dropped.",
        "Only mosbius_ota, mosbius_ntail and mosbius_ptail carry a tail you "
        "can write in the schematic. If you meant to change how hard this "
        "device drives, that is w= (1, 2, 3 or 4) on a "
        "mosbius_nmos/mosbius_pmos, or ratio= on a "
        "mosbius_nsink/mosbius_psource. If you meant a differential pair's "
        "tail current, that belongs on a mosbius_ntail/mosbius_ptail wired "
        "to the pair's shared source, not on either half.",
    )


def _check_r2_tail_dropped(device_tails: dict[str, DeviceTail],
                           device_roles: dict[str, str]) -> list[Finding]:
    """A tail current the schematic asked for that the assigned role has
    no bit for -- the same rule R1 enforces for widths, applied to the
    other setting a device can carry.

    Three symbols carry a tail= of their own: mosbius_ota, mosbius_ntail
    and mosbius_ptail (TODO.md was Sec 2, closed 2026-08-22). Everything
    else that ends up with tail= set means somebody typed the property on
    the wrong kind of device -- a diff-pair half's tail belongs to the
    pair as a whole, and is reached by wiring a mosbius_ntail/mosbius_ptail
    to its shared source, not by writing tail= on either half.

    Mergeable by requested value only (TODO.md was Sec 3, closed
    2026-08-22) -- the explanation itself never depends on role, so two
    devices asking for the same tail= merge even across NMOS/PMOS/mirror/
    OTA roles; two different requested values do not, rather than
    inventing a sentence that lists several numbers.
    """
    findings = []
    for name in sorted(device_tails):
        tail = device_tails[name]
        if not tail.dropped:
            continue

        def render(subjects: list[str], _dr=device_roles, _rq=tail.requested) -> str:
            return _render_r2(subjects, _dr, _rq)

        findings.append(Finding(
            code="R2", severity=WARN, message=render([name]),
            subject=name, merge_key=(tail.requested,), render=render,
        ))
    return findings


def _render_r3(subjects: list[str], undeclared, ibias: float) -> str:
    """The R3 explanation: a differential pair that will draw a tail
    current the schematic never asked for.

    `subjects` are the shared-source nets, so two pairs in one design (the
    NMOS one and the PMOS one) merge into a single block naming both.
    """
    one = undeclared[subjects[0]]
    nets = _join_and([f"'{s}'" for s in subjects])
    devices = _join_and(sorted({d for s in subjects for d in undeclared[s].devices}))
    amps = 2 * ibias * 1e6
    return _wrap(
        "WARNING -- ", f"the differential pair on {nets} will draw "
        f"{amps:.0f} uA you did not ask for",
        f"{devices} became differential-pair halves, and a pair's tail "
        f"current bank has no off state. Its smallest setting is one "
        f"always-on transistor (diff_n.sch M8, W=20 against the bias "
        f"reference's W=10), so the chip sinks 2 x ibias -- {amps:.0f} uA at "
        f"the {ibias * 1e6:.0f} uA this configuration uses -- out of "
        f"{nets}, whatever the schematic says. `mosbius decode` shows it as "
        f"tail=2.",
        f"Your as-drawn simulation has no such current in it, so the drawn "
        f"and routed halves of a testbench will disagree, and disagree more "
        f"the higher you set ibias.",
        f"Two ways to make them agree. Draw a {one.tail_symbol} on that "
        f"node and say which tail current you want (2, 4, 6 or 8 multiples "
        f"of ibias -- see examples/diffamp/), which puts the same current in "
        f"both. Or name that net {one.rail}, which closes the pair's free "
        f"source tie and shorts the tail bank out, leaving two ordinary "
        f"common-source FETs.",
    )


def _check_r3_undeclared_tail(routed) -> list[Finding]:
    """A pair drawing the hardware's minimum tail current with nothing in
    the schematic to say so.

    The rail-tied case is silent because the tie shorts the bank out, and
    the drawn-tail case is silent because the current is then declared.
    What is left is a pair floating on an internal net, which is exactly
    the case where the as-drawn model has no tail device at all.
    """
    undeclared = {u.net: u for u in getattr(routed, "undeclared_tails", ())}
    ibias = routed.config.ibias
    findings = []
    for net in sorted(undeclared):

        def render(subjects: list[str], _u=undeclared, _i=ibias) -> str:
            return _render_r3(subjects, _u, _i)

        findings.append(Finding(
            code="R3", severity=WARN, message=render([net]),
            subject=net, merge_key=(), render=render,
        ))
    return findings


def check_routing(routed) -> SafetyReport:
    """Run the post-routing checks against a RoutedDesign.

    Typed loosely on purpose: this only needs `.device_widths`,
    `.device_tails` and `.device_roles`, and taking the object by duck
    type keeps check.py from importing the router's result class.
    """
    return SafetyReport(
        findings=_check_r1_width_dropped(routed.device_widths, routed.device_roles)
        + _check_r2_tail_dropped(routed.device_tails, routed.device_roles)
        + _check_r3_undeclared_tail(routed)
    )


def check_design(design: MosbiusDesign) -> SafetyReport:
    """Run the netlist-level checks against `design`, before routing."""
    return SafetyReport(
        findings=_check_d1_source_on_wrong_rail(design)
        + _check_d2_drain_and_source_swapped(design)
        + _check_d3_tail_wrong_arity(design)
        + _check_d4_tail_on_rail(design)
    )


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
