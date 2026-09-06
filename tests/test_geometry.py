# SPDX-License-Identifier: Apache-2.0
"""The one number that differs between the two parts' device geometry.

Every PMOS has the same total width and length on tnt's mini-MOSbius and on
Andrew Kang's; his part splits each into 1.5x as many fingers, so a finger is
5.0 um wide on his and 7.5 um on tnt's. The as-routed half of a simulation
gets that from the part's own device library, where the widths are literals.
The as-drawn half gets it from `pmos_width_per_finger`, which
`mosbius simulate` writes into the routed netlist as a global parameter --
so `--project` is the only place a part is ever named, and the two halves of
a drawn-versus-routed comparison cannot disagree about which chip they are.

Nothing else in Python reads that parameter -- xschem and ngspice do -- so
these tests are the join between the two halves. Without them a third part
could be added with no width per finger, or a PMOS drawn with a literal
finger count, and the only symptom would be an as-drawn simulation quietly
modelling the wrong chip.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from mosbius.chips import CHIPS, KANG, TNT
from mosbius.simulate import render_drawn_geometry

REPO = Path(__file__).resolve().parent.parent
LIB = REPO / "xschem" / "mosbius_lib"

PARAM = "pmos_width_per_finger"


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


def test_the_parameter_is_global_not_inside_the_subcircuit():
    """It has to reach the ideal symbols on the design sheet, which are in a
    different subcircuit entirely, so it must be written above `.subckt`."""
    from mosbius.model import SwitchConfig
    from mosbius.simulate import render_mosbius_wrapper

    text = render_mosbius_wrapper(SwitchConfig(bits=frozenset()), "probe")
    param_at = text.index(f".param {PARAM}")
    subckt_at = text.index(".subckt probe_routed")
    assert param_at < subckt_at


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
        assert PARAM not in text, (
            f"{sch.relative_to(REPO)} sets {PARAM} itself -- let it come from "
            f"the routed netlist, so only --project chooses a part"
        )
