# SPDX-License-Identifier: Apache-2.0
"""What differs between the two parts' device geometry, and how a drawn
sheet is told which one it is.

There are two differences. **Finger count:** every PMOS has the same total
width and length on tnt's mini-MOSbius and on Andrew Kang's, but his part
splits each into 1.5x as many fingers, so a finger is 5.0 um wide on his and
7.5 um on tnt's. **Bulk tie:** his generic transistors follow their own
source, through real deep-nwell isolation, where tnt's follow the rail.

The as-routed half of a simulation gets both from the part's own device
library, where the widths are literals and the bulk is already wired. The
as-drawn half gets them from `pmos_width_per_finger`, `rwell_rail` and
`rwell_source`, which `mosbius simulate` writes into the routed netlist as
global parameters -- so `--project` is the only place a part is ever named,
and the two halves of a drawn-versus-routed comparison cannot disagree
about which chip they are.

Nothing else in Python reads any of those three -- xschem and ngspice do --
so these tests are the join between the two halves. Without them a third
part could be added with no width per finger, or a PMOS drawn with a
literal finger count, or one of the well parameters renamed on one side
only, and the only symptom would be an as-drawn simulation quietly
modelling the wrong chip.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest

from mosbius.chips import CHIPS, KANG, TNT
from mosbius.simulate import (
    BULK_OPEN_OHMS,
    BULK_TIE_OHMS,
    render_drawn_geometry,
)

REPO = Path(__file__).resolve().parent.parent
LIB = REPO / "xschem" / "mosbius_lib"

PARAM = "pmos_width_per_finger"
# The other half of a part's geometry: which of {rail, own source} a drawn
# transistor's bulk follows, as two resistor values rather than a net
# choice, because a `.param` cannot carry a node. See
# Chip.bulk_follows_source, and PARTS.md for what it is worth on silicon.
WELL_PARAMS = ("rwell_rail", "rwell_source")
# Every sheet with a transistor whose source can leave a rail, and so every
# sheet that has to split its bulk: the two generic FETs, and the OTA's NMOS
# input pair, which shares one tub on the pair's own tail node. The value is
# the PDK symbol whose instances must land on the well -- on the OTA sheet
# that is the NMOS only, since its PMOS loads sit on the supply.
#
# Nothing else in the library needs it. The mirrors and the tail banks put
# every source on a rail, so bulk and source are the same node either way.
WELL_SPLIT_SHEETS = {
    "mosbius_pmos.sch": "pfet3_g5v0d10v5.sym",
    "mosbius_nmos.sch": "nfet3_g5v0d10v5.sym",
    "mosbius_ota.sch": "nfet3_g5v0d10v5.sym",
}
# The node mosbius_pmos.sch/mosbius_nmos.sch hang their FET body on.
WELL_NODE = "well"


def test_the_two_parts_differ_by_the_documented_ratio():
    """1.5x the fingers at the same total width. If this ever stops holding,
    one parameter stops being enough to describe the difference and the
    sheets need more than a division."""
    assert TNT.pmos_width_per_finger == 7.5
    assert KANG.pmos_width_per_finger == 5.0
    assert TNT.pmos_width_per_finger / KANG.pmos_width_per_finger == 1.5


@pytest.mark.parametrize("key", sorted(CHIPS))
def test_every_part_divides_every_width_in_use_exactly(key):
    """A finger count has to be a whole number. 30, 60 and 120 um are the
    three PMOS widths the ideal library builds."""
    per_finger = CHIPS[key].pmos_width_per_finger
    for width in (30, 60, 120):
        fingers = width / per_finger
        assert fingers == int(fingers), (
            f"{key}: W={width} um gives {fingers} fingers at "
            f"{per_finger} um per finger"
        )


@pytest.mark.parametrize("key", sorted(CHIPS))
def test_the_routed_netlist_names_the_part_and_sets_the_parameter(key):
    """The generated netlist is where the as-drawn half is told which part it
    is, so it has to say so in words a reader can check as well as in the
    parameter ngspice acts on."""
    chip = CHIPS[key]
    text = render_drawn_geometry(chip)
    assert chip.title in text
    assert re.search(
        rf"^\.param\s+{PARAM}={chip.pmos_width_per_finger}$", text, re.M
    ), text


@pytest.mark.parametrize("name", (PARAM,) + WELL_PARAMS)
def test_the_parameters_are_global_not_inside_the_subcircuit(name):
    """They have to reach the ideal symbols on the design sheet, which are in
    a different subcircuit entirely, so they must be written above
    `.subckt`."""
    from mosbius.model import SwitchConfig
    from mosbius.simulate import render_mosbius_wrapper

    text = render_mosbius_wrapper(SwitchConfig(bits=frozenset()), "probe")
    param_at = text.index(name)
    subckt_at = text.index(".subckt probe_routed")
    assert param_at < subckt_at, (
        f"{name} is written inside the subcircuit, so the ideal symbols on "
        f"the design sheet cannot see it"
    )


def _instances(sch: Path, symbol: str) -> list[str]:
    """Every instance of one PDK symbol on a sheet, as its attribute text.

    An instance line is `C {sky130_fd_pr/<sym>} x y r f {name=... }`, and the
    attribute braces run over many lines, so the block ends at the first line
    that is a lone closing brace rather than at the first brace character --
    the symbol name itself ends in one.
    """
    out = []
    for block in sch.read_text().split("C {sky130_fd_pr/"):
        if not block.startswith(symbol):
            continue
        attrs = block.split("{name=", 1)[1]
        out.append(attrs.split("\n}", 1)[0])
    return out


def _sheets_with(symbol: str) -> list[Path]:
    return sorted(
        p for p in LIB.glob("*.sch") if f"C {{sky130_fd_pr/{symbol}" in p.read_text()
    )


def test_every_pmos_in_the_library_derives_its_finger_count():
    """A PMOS drawn with a literal `nf` keeps tnt's geometry whatever part the
    design was routed for, and nothing else would say so."""
    sheets = _sheets_with("pfet3_g5v0d10v5.sym")
    assert sheets, "no PMOS sheets found -- has the library moved?"
    for sch in sheets:
        code = sch.read_text()
        for attrs in _instances(sch, "pfet3_g5v0d10v5.sym"):
            nf = re.search(r"^nf=(.*)$", attrs, re.M)
            assert nf, f"{sch.name}: a PMOS instance has no nf="
            value = nf.group(1).strip().strip('"')
            if PARAM in value:
                continue
            # The indirect form: nf="nfdev", with a code block defining nfdev
            # from the parameter. mosbius_pmos needs that because its own
            # width attribute is called w, which collides with sky130's
            # (CLAUDE.md trap 10).
            assert value == "nfdev", (
                f"{sch.name}: PMOS nf={value!r} is a literal -- derive it from "
                f"{PARAM} so the sheet follows the part the design was routed for"
            )
            assert re.search(rf"nfdev='[^']*{PARAM}[^']*'", code), (
                f"{sch.name}: nf=nfdev but no code block defines nfdev from {PARAM}"
            )


def test_no_nmos_in_the_library_depends_on_it():
    """The two parts' NMOS are identical, so an NMOS reaching for this
    parameter is either a typo or a discovery that belongs in TODO.md first."""
    for sch in _sheets_with("nfet3_g5v0d10v5.sym"):
        for attrs in _instances(sch, "nfet3_g5v0d10v5.sym"):
            assert PARAM not in attrs, (
                f"{sch.name}: an NMOS instance uses {PARAM}, but NMOS geometry "
                f"is the same on both parts"
            )


def test_no_testbench_names_a_part_of_its_own():
    """The part is chosen once, by `mosbius route --project`, and arrives
    through the generated routed netlist. A testbench that named its own part
    could disagree with the routed netlist beside it, and the two halves of
    the comparison would then be different chips with nothing saying so."""
    benches = sorted(REPO.glob("examples/*/tb_*.sch")) + [LIB / "tb_template.sch"]
    assert len(benches) >= 8
    for sch in benches:
        text = sch.read_text()
        for name in (PARAM,) + WELL_PARAMS:
            assert name not in text, (
                f"{sch.relative_to(REPO)} sets {name} itself -- let it come "
                f"from the routed netlist, so only --project chooses a part"
            )


# -- the bulk tie: the other half of a part's device geometry


def test_the_two_parts_disagree_about_the_bulk():
    """Andrew Kang's generic transistors follow their own source, through real
    deep-nwell isolation; tnt's follow the rail. If a third part ever agrees
    with neither, this field stops being a bool before anything else does."""
    assert TNT.bulk_follows_source is False
    assert KANG.bulk_follows_source is True


@pytest.mark.parametrize("key", sorted(CHIPS))
def test_the_routed_netlist_sets_both_well_resistors(key):
    """One resistor shorts the well to where the bulk really goes, the other
    leaves it open. Which is which is the whole content of the difference, so
    a swap here is a silently wrong as-drawn simulation on both parts at once
    rather than on one."""
    chip = CHIPS[key]
    text = render_drawn_geometry(chip)
    found = re.search(
        r"^\.param\s+rwell_rail=(\S+)\s+rwell_source=(\S+)$", text, re.M
    )
    assert found, f"{key}: no rwell_rail/rwell_source line in:\n{text}"
    rail, source = found.groups()
    if chip.bulk_follows_source:
        assert (rail, source) == (BULK_OPEN_OHMS, BULK_TIE_OHMS), (
            f"{key} follows its own source, so rwell_source is the short"
        )
    else:
        assert (rail, source) == (BULK_TIE_OHMS, BULK_OPEN_OHMS), (
            f"{key} follows the rail, so rwell_rail is the short"
        )


def test_the_tie_and_open_values_stay_within_reach_of_each_other():
    """Not cosmetic. The first pair tried was 1e-12/1e12 ohm, mirroring
    CONFIG_TIE_OHMS, and ngspice ran for 50+ minutes at ~100% CPU instead of
    the usual ~2-minute model load: 24 decades of conductance on one floating
    node, with 1e-12 sitting on top of ngspice's own default gmin, is a much
    harder solve than a single tie to a fixed rail. Nine decades is dominant
    either way against the stiffest real node in these decks (~50 kOhm) and
    nowhere near ngspice's internal constants."""
    decades = math.log10(float(BULK_OPEN_OHMS) / float(BULK_TIE_OHMS))
    assert 6 <= decades <= 12, (
        f"{BULK_TIE_OHMS} to {BULK_OPEN_OHMS} ohm is {decades:.0f} decades -- "
        f"too few and the open leg conducts, too many and ngspice's DC solve "
        f"grinds (see this test's docstring)"
    )


def _resistor_values(sch: Path) -> dict[str, str]:
    """Every `devices/res.sym` instance on a sheet, as name -> value."""
    out = {}
    for block in sch.read_text().split("C {devices/res.sym}")[1:]:
        attrs = block.split("{", 1)[1].split("}", 1)[0]
        name = re.search(r"name=(\S+)", attrs)
        value = re.search(r'value="([^"]*)"', attrs)
        if name and value:
            out[name.group(1)] = value.group(1).strip("'")
    return out


@pytest.mark.parametrize("sheet,fet", sorted(WELL_SPLIT_SHEETS.items()))
def test_a_moving_source_hangs_its_body_on_the_split_well_node(sheet, fet):
    """The bulk must not go straight to the rail. If it does, the sheet is
    tnt's part hard-coded, and a design routed for Andrew's gets an as-drawn
    branch modelling the wrong chip with nothing saying so -- which is how
    this was found, as two source followers 15-19% off their own silicon."""
    sch = LIB / sheet
    instances = _instances(sch, fet)
    assert instances, f"{sheet}: no {fet} instance found -- has it moved?"
    for attrs in instances:
        body = re.search(r"^body=(\S+)$", attrs, re.M)
        assert body, f"{sheet}: a {fet} instance has no body="
        assert body.group(1) == WELL_NODE, (
            f"{sheet}: body={body.group(1)!r} goes straight to a rail -- hang "
            f"it on {WELL_NODE!r} so Chip.bulk_follows_source can steer it"
        )


@pytest.mark.parametrize("sheet", sorted(WELL_SPLIT_SHEETS))
def test_a_well_split_sheet_names_the_generated_parameters_exactly(sheet):
    """The join. Nothing in Python reads these names, so a rename on either
    side alone leaves the well tied to neither node through two 1-ohm-default
    resistors, and every drawn transistor quietly loses its bulk."""
    values = _resistor_values(LIB / sheet)
    assert set(values.values()) == set(WELL_PARAMS), (
        f"{sheet}: resistors evaluate {sorted(set(values.values()))}, but "
        f"mosbius simulate writes {sorted(WELL_PARAMS)}"
    )


def test_the_otas_pmos_loads_stay_on_the_supply():
    """The other half of the OTA rule, and it has to be said out loud: only
    the input pair's source moves. Both parts sit the PMOS loads' sources on
    VAPWR, so their bulk is already the same node, and hanging them on the
    well would invent a difference neither chip has."""
    sch = LIB / "mosbius_ota.sch"
    loads = _instances(sch, "pfet3_g5v0d10v5.sym")
    assert len(loads) == 2, f"expected two PMOS loads, found {len(loads)}"
    for attrs in loads:
        body = re.search(r"^body=(\S+)$", attrs, re.M)
        assert body and body.group(1) != WELL_NODE, (
            "an OTA PMOS load hangs on the well -- its source is on the "
            "supply on both parts, so its bulk has nowhere else to go"
        )
