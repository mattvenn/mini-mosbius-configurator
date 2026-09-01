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

from mosbius import messages
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
    message = messages.CHECK_E1_SUPPLY_SHORT.format(
        n=n, plural="es" if n != 1 else "", path=format_path(path),
    )
    return [Finding(code="E1", severity=ERROR, message=message)]


def _check_e2_ibias_short(graph: Graph, comp: dict[str, int]) -> list[Finding]:
    findings = []
    for rail in ("VAPWR", "VGND"):
        if comp["ibias"] != comp[rail]:
            continue
        path = _shortest_path(graph, "ibias", rail)
        n = len(path)
        message = messages.CHECK_E2_IBIAS_SHORT.format(
            rail=rail, n=n, plural="es" if n != 1 else "", path=format_path(path),
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
            n = len(path)
            message = messages.CHECK_E3_PIN_INTO_RAIL.format(
                pin=pin, rail=rail, n=n, plural="es" if n != 1 else "",
                path=format_path(path),
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
            n = len(path)
            message = messages.CHECK_E4_PIN_CONTENTION.format(
                a=a, b=b, n=n, plural="es" if n != 1 else "",
                path=format_path(path),
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
        n = len(path)
        path_text = (
            format_path(path) if path else messages.CHECK_W1_SAME_NET.format(name=name)
        )
        message = messages.CHECK_W1_SHORTED_CHANNEL.format(
            name=name, n=n, plural="es" if n != 1 else "", path=path_text,
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
            headline = messages.CHECK_W2_HEADLINE_ONE.format(names=names)
            intro = messages.CHECK_W2_INTRO_ONE
        else:
            headline = messages.CHECK_W2_HEADLINE_MANY.format(names=names)
            intro = messages.CHECK_W2_INTRO_MANY

        if all(t.endswith((".g", ".inp", ".inm")) for t in terminals):
            why = messages.CHECK_W2_WHY_ALL_GATES
        else:
            why = messages.CHECK_W2_WHY_NOTHING_REACHES

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
            hint = messages.CHECK_W2_HINT_UNTIED_TAIL.format(bits=bits)

        message = messages.CHECK_W2_BODY.format(
            headline=headline, intro=intro, why=why, hint=hint,
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
        message = messages.CHECK_W3_PARTLY_WIRED.format(
            name=name, used=', '.join(used), unused=', '.join(unused),
            has_have='has' if len(used) == 1 else 'have',
            is_are='is' if len(unused) == 1 else 'are',
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
        it_them = "it" if len(empty) == 1 else "them"
        sentences.append(messages.CHECK_I1_SENTENCE_EMPTY.format(
            names=_join_and(empty), verb=verb, it_them=it_them,
        ))
    if bonded:
        pins = _join_and([detail[seg][1] for seg in bonded])
        if len(bonded) == 1:
            sentences.append(messages.CHECK_I1_SENTENCE_BONDED_ONE.format(
                seg=bonded[0], pins=pins,
            ))
        else:
            sentences.append(messages.CHECK_I1_SENTENCE_BONDED_MANY.format(
                names=_join_and(bonded), pins=pins,
            ))
    if wired:
        verb = "has" if len(wired) == 1 else "have"
        each = "" if len(wired) == 1 else " each"
        sentences.append(messages.CHECK_I1_SENTENCE_WIRED.format(
            names=_join_and(wired), verb=verb, each=each,
        ))

    plural = len(subjects) > 1
    headline = messages.CHECK_I1_HEADLINE.format(
        subjects=_join_and(subjects), do_does="do" if plural else "does",
    )
    consequence = ("none of these segments is" if plural else "this segment isn't")
    return _wrap(
        "INFO -- ", headline,
        " ".join(sentences),
        messages.CHECK_I1_PARAGRAPH2.format(consequence=consequence),
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
    return messages.CHECK_D1_WHY_COSTS_PAIR.format(
        tail_bit=_PAIR_TAIL_BIT[kind],
        other_rail=OTHER_RAIL[wrong_rail],
        wrong_rail=wrong_rail,
        independent_slots=_INDEPENDENT_SLOTS[kind],
        router_label=_ROUTER_LABEL[kind],
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
            subject = messages.CHECK_D1_SUBJECT_ONE.format(names=names, kind=kind, wrong=wrong)
        else:
            subject = messages.CHECK_D1_SUBJECT_MANY.format(n=n, kind=kind, wrong=wrong, names=names)

        if home not in wired_nets:
            message = messages.CHECK_D1_RAILS_SHORTED.format(
                subject=subject, home=home, kind=kind, wrong=wrong,
            )
            findings.append(Finding(code="D1", severity=ERROR, message=message))
            continue

        message = messages.CHECK_D1_SOURCE_ON_WRONG_RAIL.format(
            wrong=wrong, home=home, subject=subject, kind=kind,
            why_costs_pair=_why_it_costs_the_pair(kind, wrong), names=names,
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
            subject = messages.CHECK_D2_SUBJECT_ONE.format(names=names, kind=kind, rail=rail, nets=nets)
        else:
            subject = messages.CHECK_D2_SUBJECT_MANY.format(n=n, kind=kind, rail=rail, nets=nets, names=names)

        top, bottom = ("source", "drain") if kind == "pmos" else ("drain", "source")
        other_kind = "nmos" if kind == "pmos" else "pmos"
        message = messages.CHECK_D2_DRAIN_SOURCE_SWAPPED.format(
            names=names, subject=subject, kind=kind, rail=rail,
            source_tie=SOURCE_TIE_EXAMPLE[kind], kind_upper=kind.upper(),
            top=top, bottom=bottom, other_kind=other_kind,
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
                found = messages.CHECK_D3_FOUND_NONE.format(node=node)
            else:
                found = messages.CHECK_D3_FOUND_SOME.format(
                    n=len(halves), fet_symbol=fet_symbol, names=_name_list(halves),
                )
            message = messages.CHECK_D3_TAIL_WRONG_ARITY.format(
                tail_name=tail.name, symbol=symbol, node=node,
                fet_symbol=fet_symbol, found=found, tail_bit=_TAIL_BIT[kind],
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
            message = messages.CHECK_D4_TAIL_ON_RAIL.format(
                tail_name=tail.name, rail=rail, symbol=symbol, tail_bit=_TAIL_BIT[kind],
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
        headline = messages.CHECK_R1_HEADLINE_ONE.format(name=name, prop=prop, requested=requested, role=role)
        intro = messages.CHECK_R1_INTRO_ONE.format(name=name, role=role)
    else:
        names, role_list = _join_and(subjects), _join_and(roles)
        headline = messages.CHECK_R1_HEADLINE_MANY.format(
            names=names, prop=prop, requested=requested, role_list=role_list,
        )
        intro = messages.CHECK_R1_INTRO_MANY.format(names=names, role_list=role_list)
    return _wrap(
        "WARNING -- ", headline,
        messages.CHECK_R1_PARAGRAPH_DROPPED.format(
            intro=intro, kind=kind, prop=prop, requested=requested,
        ),
        messages.CHECK_R1_PARAGRAPH_INSTEAD.format(
            prop=prop, effective=effective, geometry=geometry, prog=prog,
        ),
        messages.CHECK_R1_PARAGRAPH_WHY.format(prop=prop, effective=effective, requested=requested),
        messages.CHECK_R1_PARAGRAPH_FIX.format(prop=prop, effective=effective),
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
        headline = messages.CHECK_R2_HEADLINE_ONE.format(name=name, requested=requested, role=role)
        intro = messages.CHECK_R2_INTRO_ONE.format(name=name, role=role)
    else:
        names, role_list = _join_and(subjects), _join_and(roles)
        headline = messages.CHECK_R2_HEADLINE_MANY.format(
            names=names, requested=requested, role_list=role_list,
        )
        intro = messages.CHECK_R2_INTRO_MANY.format(names=names, role_list=role_list)
    return _wrap(
        "WARNING -- ", headline,
        messages.CHECK_R2_PARAGRAPH_DROPPED.format(intro=intro),
        messages.CHECK_R2_PARAGRAPH_ALTERNATIVES,
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
    ibias_uA = ibias * 1e6
    return _wrap(
        "WARNING -- ", messages.CHECK_R3_HEADLINE.format(nets=nets, amps=amps),
        messages.CHECK_R3_PARAGRAPH_SINKS.format(
            devices=devices, amps=amps, ibias_uA=ibias_uA, nets=nets,
        ),
        messages.CHECK_R3_PARAGRAPH_DISAGREE,
        messages.CHECK_R3_PARAGRAPH_FIX.format(tail_symbol=one.tail_symbol, rail=one.rail),
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


# Devices that copy the chip's bias reference, and so need one to exist.
# Every mirror leg, both tail banks and the OTA tail gate on it.
BIAS_REFERENCED_KINDS = ("nsink", "psource", "ntail", "ptail", "ota")


def _check_b1_bias_generator(design: MosbiusDesign) -> list[Finding]:
    """Exactly one bias generator per design, and only when one is needed.

    `ibias` (pin ua[0]) is a current input; the chip turns it into the
    gate voltage every mirror leg, tail bank and the OTA tail copies, and
    that conversion happens once per chip. Getting the count wrong is
    quiet and expensive in both directions, which is why this is an error
    rather than a warning: two references halve the current between them
    (measured -99 uA a leg where -200 uA was right), and none leaves every
    mirror gate wherever the DC solver happens to put it.
    """
    users = sorted({d.kind for d in design.devices if d.kind in BIAS_REFERENCED_KINDS})
    count = design.bias_generators
    if count == 1 or (count == 0 and not users):
        return []

    drew = _join_and([f"mosbius_{k}" for k in users])
    if count == 0:
        message = _wrap(
            "IMPOSSIBLE -- ", messages.CHECK_B1_NO_GENERATOR_HEADLINE,
            messages.CHECK_B1_NO_GENERATOR_DREW.format(drew=drew),
            messages.CHECK_B1_NO_GENERATOR_GAP,
            messages.CHECK_B1_NO_GENERATOR_FIX,
        )
    else:
        message = _wrap(
            "IMPOSSIBLE -- ", messages.CHECK_B1_TOO_MANY_HEADLINE.format(count=count),
            messages.CHECK_B1_TOO_MANY_SHARE,
            messages.CHECK_B1_TOO_MANY_FIX,
        )
    return [Finding(code="B1", severity=ERROR, message=message)]


def check_design(design: MosbiusDesign) -> SafetyReport:
    """Run the netlist-level checks against `design`, before routing."""
    return SafetyReport(
        findings=_check_b1_bias_generator(design)
        + _check_d1_source_on_wrong_rail(design)
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
