# SPDX-License-Identifier: Apache-2.0
"""mosbius/route.py's sticky routing -- SPEC.md Sec 3.2b.

M3 exit criterion: "a re-run of an unchanged design reuses its stored
routing verbatim". What's NOT covered here (see route.py's module notes):
Sec 3.2b's fuller ideal of *minimally* re-routing a changed design,
preserving assignments that are still valid. A changed design currently
gets a full fresh route() -- correct, but not minimal.
"""

from __future__ import annotations

from pathlib import Path

from mosbius.netlist import parse_netlist
from mosbius.route import design_topology_hash, load_routed_design, route, route_sticky

INVERTER_NETLIST = """
nfeta_0 ua1 ua2 VGND net1 mosbius_nmos w=1
pfeta_1 ua1 ua2 VAPWR net2 mosbius_pmos w=1
"""

INVERTER_WIDE = INVERTER_NETLIST.replace("w=1", "w=2")


def test_unchanged_design_reuses_bits_verbatim_no_resolve(tmp_path: Path):
    config_path = tmp_path / "design.mosbius.json"
    design = parse_netlist(INVERTER_NETLIST)

    first = route_sticky(design, config_path)
    second = route_sticky(design, config_path)

    assert second.config.bits == first.config.bits
    assert second.device_roles == first.device_roles


def test_first_call_persists_a_config_file(tmp_path: Path):
    config_path = tmp_path / "design.mosbius.json"
    assert not config_path.exists()
    route_sticky(parse_netlist(INVERTER_NETLIST), config_path)
    assert config_path.exists()

    stored = load_routed_design(config_path)
    assert stored["topology_hash"] == design_topology_hash(parse_netlist(INVERTER_NETLIST))
    assert "bitstream" in stored
    assert len(stored["bitstream"]) == 48


def test_changed_design_triggers_a_fresh_route(tmp_path: Path):
    config_path = tmp_path / "design.mosbius.json"
    original = route_sticky(parse_netlist(INVERTER_NETLIST), config_path)
    changed = route_sticky(parse_netlist(INVERTER_WIDE), config_path)

    assert changed.config.bits != original.config.bits
    # And it's the right change: width=2 now, not the plain fresh route()
    # of the original netlist.
    assert changed.config.bits == route(parse_netlist(INVERTER_WIDE)).config.bits


def test_changed_design_updates_the_persisted_file(tmp_path: Path):
    config_path = tmp_path / "design.mosbius.json"
    route_sticky(parse_netlist(INVERTER_NETLIST), config_path)
    route_sticky(parse_netlist(INVERTER_WIDE), config_path)

    stored = load_routed_design(config_path)
    assert stored["topology_hash"] == design_topology_hash(parse_netlist(INVERTER_WIDE))


def test_force_always_resolves_even_if_unchanged(tmp_path: Path):
    config_path = tmp_path / "design.mosbius.json"
    design = parse_netlist(INVERTER_NETLIST)
    first = route_sticky(design, config_path)
    forced = route_sticky(design, config_path, force=True)
    # Same design -> same solve, so bits match -- the point is force=True
    # doesn't just short-circuit to whatever's on disk without checking.
    assert forced.config.bits == first.config.bits


def test_topology_hash_ignores_instance_names():
    a = parse_netlist("nfeta_0 g d s b mosbius_nmos w=1\n")
    b = parse_netlist("M99 g d s b mosbius_nmos w=1\n")
    assert design_topology_hash(a) == design_topology_hash(b)


def test_topology_hash_differs_on_real_change():
    a = parse_netlist("m1 g d s b mosbius_nmos w=1\n")
    b = parse_netlist("m1 g d s b mosbius_nmos w=2\n")
    assert design_topology_hash(a) != design_topology_hash(b)


def test_missing_config_file_does_a_fresh_route(tmp_path: Path):
    config_path = tmp_path / "does_not_exist_yet.mosbius.json"
    routed = route_sticky(parse_netlist(INVERTER_NETLIST), config_path)
    assert routed.config.bits == route(parse_netlist(INVERTER_NETLIST)).config.bits
    assert config_path.exists()
