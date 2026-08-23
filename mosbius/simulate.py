# SPDX-License-Identifier: Apache-2.0
"""Turn a routed SwitchConfig into a ready-to-run, silicon-accurate SPICE
subcircuit (TODO.md Sec 1, closed 2026-08-23): the real switch matrix,
real row-coupling capacitance, real bus-wire capacitance, and real pad
models, all packaged as one self-contained
`.subckt <name>_mosbius ibias ua1 ua2 ua3 ua4 ua5 VAPWR VDPWR VGND ... .ends`
-- the same 9-pin port list every hand-drawn design in this project
already exposes via `devices/iopin.sym` (confirmed against
examples/ringosc/ring.sch), so a user can drop this straight into their
existing testbench in place of their ideal `mosbius_*`-symbol schematic
block (xschem's `spice_sym_def` instance property is the mechanism the
project's own author already uses for exactly this swap elsewhere, e.g.
github.com/mattvenn/tt08-analog-ring-osc's tb_ring.sch) and re-run their
own stimulus/analysis/probes completely unchanged.

The real switch matrix, row-coupling capacitance, and bus-wire
capacitance are properties of the fixed chip, not of any specific
design -- they're baked into mosbius/data/mosbius_device_library.spice
once (see tools/rebuild_mosbius_device_library.sh), not regenerated per
simulation. The one genuinely per-design piece is which package pins
(ua[1]..ua[5]) actually need a real pad_model instance, decided by
`used_external_pins()` below.
"""

from __future__ import annotations

import json
from pathlib import Path

from mosbius.model import DEFAULT_IBIAS, EXTERNAL_PINS, SwitchConfig, bus_node, connected_components
from mosbius.spice import render_bus_wire_caps, render_config_spice

DEVICE_LIBRARY_PATH = Path(__file__).parent / "data" / "mosbius_device_library.spice"


def _pin_net(pin: str) -> str:
    """"ua[1]" -> "ua1", matching every hand-drawn design's own iopin
    label -- mosbius/route.py's PORT_ROW does the same transform for the
    same reason.
    """
    return pin.replace("ua[", "ua").rstrip("]")


def used_external_pins(config: SwitchConfig) -> list[str]:
    """Which of the 5 real package pins (in "ua[1]".."ua[5]" form,
    EXTERNAL_PINS' own key format) this config's routing actually connects
    to a device -- i.e. a closed-switch path exists from the pin's bond
    wire to some device crosspoint.

    A pin's bond wire is always present in the graph (model.py's
    build_graph: "Fixed physical bonds: always present, not gated by any
    bit"), so a bare "is ua[N] in the graph" check would always be true.
    What actually distinguishes a used pin is whether its connected
    component reaches any crosspoint (an `xpt_*` node) at all --
    crosspoints are also always-present graph nodes, so reaching one means
    a real closed switch (or chain of them, including through a
    `cfg_bus_short` merge -- this needs no special-casing, `build_graph()`
    already models the short as a real edge and BFS just walks through
    it) connects the pin to it.
    """
    graph = config.build_graph()
    comp = connected_components(graph)
    by_component: dict[int, set[str]] = {}
    for node, cid in comp.items():
        by_component.setdefault(cid, set()).add(node)
    used = []
    for pin in EXTERNAL_PINS:
        nodes = by_component[comp[pin]]
        if any(n.startswith("xpt_") for n in nodes):
            used.append(pin)
    return used


def _mosbius_subckt_ports(library_text: str) -> list[str]:
    """The real, full port list of `.subckt mosbius`, straight from the
    device library text -- not re-derived or hand-copied, so a library
    rebuild can never silently drift out of sync with this module.
    """
    lines = library_text.split("\n")
    start = next(i for i, l in enumerate(lines) if l.startswith(".subckt mosbius "))
    header = [lines[start][len(".subckt mosbius "):]]
    i = start + 1
    while i < len(lines) and lines[i].startswith("+"):
        header.append(lines[i][1:])
        i += 1
    return " ".join(header).split()


def _wrap_call(nets: list[str], width: int = 10) -> str:
    lines = ["X1 " + " ".join(nets[:width])]
    rest = nets[width:]
    while rest:
        lines.append("+ " + " ".join(rest[:width]))
        rest = rest[width:]
    lines.append("+ mosbius")
    return "\n".join(lines)


def render_mosbius_wrapper(config: SwitchConfig, name: str) -> str:
    """A single self-contained SPICE subcircuit, `<name>_mosbius`, that
    behaves like `config` really does on real silicon -- real switch
    matrix, real row-coupling and bus-wire capacitance, real pad models on
    whichever package pins this config actually uses. Port list is always
    `ibias ua1 ua2 ua3 ua4 ua5 VAPWR VDPWR VGND`, matching every hand-drawn
    design in this project.
    """
    library_text = DEVICE_LIBRARY_PATH.read_text()
    ports = _mosbius_subckt_ports(library_text)

    # Reuse every mosbius subckt port name literally as the local net name
    # inside our own wrapper -- the same pattern the project's ad hoc
    # tools/run_*.sh scripts already used. This is what makes
    # render_config_spice()'s/render_bus_wire_caps()'s ties (which target
    # those same literal names) land on the real internal switch-matrix
    # nodes. VAPWR/VDPWR/VGND/ibias reusing their own names this way also
    # automatically coincides with this wrapper's own identically-named
    # ports (ordinary SPICE subcircuit scoping), no special-casing needed.
    used_pins = used_external_pins(config)
    pad_lines = [
        f"Xpad_{_pin_net(pin)} VGND {_pin_net(pin)} {bus_node(*EXTERNAL_PINS[pin])} pad_model"
        for pin in used_pins
    ]

    header = (
        f"* Generated by mosbius/simulate.py -- {name}_mosbius: the real\n"
        f"* switch matrix + row-coupling capacitance + bus-wire capacitance\n"
        f"* + real pad model(s) this config actually needs, self-contained\n"
        f"* (TODO.md Sec 1, closed 2026-08-23). Drop this into an existing\n"
        f"* testbench (e.g. via xschem's spice_sym_def instance property)\n"
        f"* in place of an ideal mosbius_* schematic block -- same 9-pin\n"
        f"* port list every hand-drawn design in this project already\n"
        f"* exposes via devices/iopin.sym.\n"
        f".subckt {name}_mosbius ibias ua1 ua2 ua3 ua4 ua5 VAPWR VDPWR VGND"
    )

    parts = [
        header,
        _wrap_call(ports),
        "",
        render_config_spice(config).rstrip("\n"),
        "",
        render_bus_wire_caps().rstrip("\n"),
        "",
        "* Real pad model(s) -- only for package pins this config's routing",
        "* actually uses; any other ua[] port simply stays unconnected",
        "* inside this subcircuit, which is fine for a SPICE port.",
        *(pad_lines if pad_lines else ["* (none -- this config uses no real package pin)"]),
        "",
        ".ends",
        "",
        library_text,
    ]
    return "\n".join(parts)


def name_from_routed_path(path: Path) -> str:
    """`<name>.mosbius.json` -> `<name>` (`mosbius route --out`'s own
    naming convention, per CLAUDE.md's own example,
    `build/ring.mosbius.json`). Falls back to the bare filename stem for
    anything else.
    """
    if path.name.endswith(".mosbius.json"):
        return path.name[: -len(".mosbius.json")]
    return path.stem


def simulate_from_routed_json(path: Path) -> tuple[str, str]:
    """Load a routed design JSON (as written by `mosbius route --out`) and
    return `(name, spice_text)` -- `spice_text` from
    `render_mosbius_wrapper`.
    """
    data = json.loads(path.read_text())
    config = SwitchConfig.from_bitstream(data["bitstream"], ibias=data.get("ibias", DEFAULT_IBIAS))
    name = name_from_routed_path(path)
    return name, render_mosbius_wrapper(config, name)
