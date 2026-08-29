# SPDX-License-Identifier: Apache-2.0
"""mosbius/pads.py: deriving which PCB pad to probe, per shuttle.

These tests never touch the network -- each writes a project page into a
temporary cache directory, which is also the documented offline path for a
bench with no internet (save the project's page as
build/pads_<shuttle>_<macro>.html).
"""


import urllib.error

import pytest

from mosbius import pads
from mosbius.bitstream import unpack
from mosbius.model import SwitchConfig

# The Analog pins table exactly as tinytapeout.com serves it for
# tt_um_tnt_mosbius on ttsky25a, copied verbatim on 2026-08-29. Kept as the
# real markup rather than something hand-rolled: it is the only thing
# standing between a restyle of those pages and a wrong pad letter at the
# bench, so the parser is tested against the genuine article.
REAL_PAGE_TABLE = (
    "<h3>Analog pins</h3><table><thead><tr><th><code>ua</code></th>"
    "<th>PCB Pin</th><th>Internal index</th><th>Description</th></tr></thead>"
    "<tbody>"
    "<tr><td>0</td><td>K</td><td>5</td><td>Reference Bias</td></tr>"
    "<tr><td>1</td><td>C</td><td>0</td><td>Bus 1A</td></tr>"
    "<tr><td>2</td><td>J</td><td>4</td><td>Bus 2A</td></tr>"
    "<tr><td>3</td><td>D</td><td>1</td><td>Bus 3A</td></tr>"
    "<tr><td>4</td><td>G</td><td>3</td><td>Bus 4A</td></tr>"
    "<tr><td>5</td><td>F</td><td>2</td><td>Bus 5A</td></tr>"
    "</tbody></table>"
)

# Project pages put the digital pinout table above the analog one, so a
# parser that took "the first table" would read pad letters out of the
# wrong one -- and its first column is `#` 0..7, which looks enough like a
# ua column to be dangerous.
DIGITAL_TABLE_BEFORE = (
    "<table><thead><tr><th>#</th><th>Input</th><th>Output</th>"
    "<th>Bidirectional</th></tr></thead><tbody>"
    "<tr><td>0</td><td>data_in</td><td>data_out</td><td></td></tr>"
    "<tr><td>1</td><td>enable</td><td></td><td></td></tr>"
    "</tbody></table>"
)

REAL_PAGE = "<html><body>" + DIGITAL_TABLE_BEFORE + REAL_PAGE_TABLE + "</body></html>"

INVERTER = "080000004010000001000000000000000040000400000000"
RING = "3f008803f004001401000210188406000050040100000019"

TNT_MOSBIUS_PADS = {
    "ibias": "K", "ua1": "C", "ua2": "J", "ua3": "D", "ua4": "G", "ua5": "F",
}


def page_with(rows, headers=("<code>ua</code>", "PCB Pin", "Internal index")):
    """A project page carrying `rows` -- (ua, pad, index) triples."""
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows
    )
    return (
        "<html><body><table><thead><tr>" + head + "</tr></thead><tbody>"
        + body + "</tbody></table></body></html>"
    )


@pytest.fixture
def cached_page(tmp_path, monkeypatch):
    """Install a project page in the cache, so no test reaches the network.

    This is also the documented offline path: save the project's page as
    build/pads_<shuttle>_<macro>.html and the lookup works with no internet.
    """
    monkeypatch.setattr(pads, "CACHE_DIR", tmp_path)

    def no_network(*args, **kwargs):
        raise urllib.error.URLError("network disabled in tests")
    monkeypatch.setattr(pads.urllib.request, "urlopen", no_network)

    def install(html=REAL_PAGE, shuttle="ttsky25a", macro="tt_um_tnt_mosbius"):
        (tmp_path / f"pads_{shuttle}_{macro}.html").write_text(html)
    return install


def test_pad_map_reads_the_pads_off_the_project_page(cached_page):
    cached_page()
    assert pads.pad_map("ttsky25a", "tt_um_tnt_mosbius") == TNT_MOSBIUS_PADS


def test_pad_map_ignores_the_digital_pinout_table_above_it(cached_page):
    """The digital table comes first on the page and its `#` column also
    counts 0..7, so picking a table by position rather than by its own
    headers reads pad letters out of the wrong one.
    """
    cached_page()
    assert pads.pad_map("ttsky25a", "tt_um_tnt_mosbius")["ua1"] == "C"


def test_a_different_shuttle_can_give_entirely_different_pads(cached_page):
    """The whole reason this is a lookup and not a constant. Both halves of
    the answer -- where the project sits on the shuttle, and how that
    shuttle's carrier is wired -- are free to change, so the letters for the
    same design on the next shuttle are not predictable from these ones.
    """
    cached_page(
        page_with([("0", "A", "0"), ("1", "S", "1"), ("2", "X", "2")]),
        shuttle="ttsky26b",
    )
    assert pads.pad_map("ttsky26b", "tt_um_tnt_mosbius") == {
        "ibias": "A", "ua1": "S", "ua2": "X",
    }


def test_ua_zero_is_named_ibias(cached_page):
    """Every schematic and every other module calls that pin ibias; the
    page calls it ua 0 / "Reference Bias". Translate once, here.
    """
    cached_page()
    assert pads.pad_map("ttsky25a", "tt_um_tnt_mosbius")["ibias"] == "K"
    assert "ua0" not in pads.pad_map("ttsky25a", "tt_um_tnt_mosbius")


def test_pads_in_use_follows_the_bitstream(cached_page):
    cached_page()
    config = SwitchConfig(bits=unpack(INVERTER))
    # the inverter wires ua1 and ua2 only, and needs no bias current
    assert pads.pads_in_use(config, "ttsky25a", "tt_um_tnt_mosbius") == {"ua1": "C", "ua2": "J"}


def test_pads_in_use_includes_the_ring_buffer_output(cached_page):
    cached_page()
    config = SwitchConfig(bits=unpack(RING))
    in_use = pads.pads_in_use(config, "ttsky25a", "tt_um_tnt_mosbius")
    assert in_use == {"ua1": "C", "ua2": "J", "ua3": "D"}
    # rail-tied diff-pair sources short the tail bank out, so no bias is drawn
    assert "ibias" not in in_use


def test_a_page_with_no_analog_table_is_explained(cached_page):
    """A purely digital project, or a restyled page. Either way there is
    nothing to fall back on, so it must say so rather than return nothing.
    """
    cached_page("<html><body>" + DIGITAL_TABLE_BEFORE + "</body></html>",
                macro="tt_um_digital")
    with pytest.raises(pads.PadLookupError, match="no Analog pins table"):
        pads.pad_map("ttsky25a", "tt_um_digital")


def test_a_renamed_pad_column_fails_loudly(cached_page):
    """The parser matches the table's own column headers, so a restyle that
    renames them finds nothing and raises -- which is the safe failure. A
    restyle that reordered the columns would otherwise hand back a letter
    from the wrong column, and a wrong pad reads as a probe on a dead node.
    """
    cached_page(page_with([("1", "C", "0")], headers=("ua", "Breakout", "idx")))
    with pytest.raises(pads.PadLookupError, match="no Analog pins table"):
        pads.pad_map("ttsky25a", "tt_um_tnt_mosbius")


def test_pad_table_names_the_pad_the_pin_and_what_is_on_it(cached_page):
    cached_page()
    table = pads.format_pad_table(
        SwitchConfig(bits=unpack(INVERTER)), "ttsky25a", "tt_um_tnt_mosbius"
    )
    lines = [line.split() for line in table.splitlines() if line.startswith("  C ")]
    assert lines and lines[0][:2] == ["C", "ua1"]
    assert "nmos_a gate" in table and "pmos_a drain" in table
    # the pads this configuration does not use are worth saying too, so
    # nobody probes a pin that is connected to nothing
    assert "Nothing is on the other analog pads" in table
    assert "G (ua4)" in table


def test_pad_table_shows_the_bias_pad_only_when_something_draws_on_it(cached_page):
    """`ibias` is bench setup rather than a signal, and a design that draws
    no bias current does not need it wired at all."""
    cached_page()
    table = pads.format_pad_table(
        SwitchConfig(bits=unpack(INVERTER)), "ttsky25a", "tt_um_tnt_mosbius"
    )
    assert "bias current in" not in table

    # examples/diffamp: a pair floating off the rail draws its tail current
    biased = pads.format_pad_table(
        SwitchConfig.from_bitstream("00100000c020004820000000004821000000000000000030"),
        "ttsky25a", "tt_um_tnt_mosbius",
    )
    assert "K         ibias" in biased
    assert "bias current in, 100.0 uA -- drawn by ndiffpair" in biased
    # one pair, named once -- not both halves of it
    assert "ndiffpair+, ndiffpair-" not in biased


# ---------------------------------------------------------------------------
# The ANALOG header picture
#
# The layout is data read off a physical board, not something derived, so
# what is worth testing is that it stays consistent with the pad letters the
# rest of the module works in -- and that the drawing marks the right holes.
# ---------------------------------------------------------------------------

def test_header_carries_every_pad_the_mapping_can_name():
    letters = [
        cell for row in pads.ANALOG_HEADER for cell in row
        if cell not in (pads.GND_PAD, "3v3")
    ]
    # A pad letter the lookup can return but the header cannot show would
    # print a table naming a hole the picture does not have. The letters the
    # lookup returns come off the website, so this checks the ones this chip
    # is actually known to use rather than a hard-coded list.
    for letter in TNT_MOSBIUS_PADS.values():
        assert letter in letters, letter
    assert len(letters) == len(set(letters)) == 22


def test_header_skips_I_and_O():
    """The board letters A..X without I or O, so they cannot be misread as 1
    and 0. A gap in the sequence is the convention, not a missing pad.
    """
    letters = {cell for row in pads.ANALOG_HEADER for cell in row}
    assert "I" not in letters and "O" not in letters


def test_header_grounds_are_on_both_rows():
    """The grounds alternate rows as they step along -- that is what makes
    the lettering look irregular, and it is the part nobody reconstructs
    correctly from the letter sequence alone.
    """
    top, bottom = pads.ANALOG_HEADER
    assert pads.GND_PAD in top and pads.GND_PAD in bottom
    assert top[0] == "A" and bottom[0] == pads.GND_PAD  # first gnd is under A


def test_header_picture_brackets_only_the_pads_in_use():
    drawing = pads.format_analog_header({"ua1": "C", "ua2": "J"})
    assert "[C]" in drawing and "[J]" in drawing
    assert "[D]" not in drawing and "[A]" not in drawing
    # both rows are drawn, whichever row the used pads happen to fall on
    assert "gnd" in drawing and "X" in drawing and "3v3" in drawing


def test_header_picture_rows_line_up_in_columns():
    """It is read by eye at a bench, so the two rows have to stay in
    register -- a letter over the wrong gap points at the wrong hole.
    """
    drawing = pads.format_analog_header({"ua1": "C"})
    top, bottom = [l for l in drawing.split("\n") if "gnd" in l][:2]
    assert top.index("[C]") % 4 == bottom.index("gnd") % 4


def test_pad_table_draws_the_header(cached_page):
    cached_page()
    config = SwitchConfig(bits=unpack(INVERTER))
    out = pads.format_pad_table(config, "ttsky25a", "tt_um_tnt_mosbius")
    assert "ANALOG header" in out
    assert "[C]" in out and "[J]" in out
    assert "ground to any square marked gnd" in out


def test_an_unreachable_page_says_how_to_work_offline(cached_page):
    """The letters are published in exactly one place, so there is no
    fallback to offer -- only the URL to save and where to put it.
    """
    cached_page(macro="tt_um_other")   # installs the fixture, not this macro
    with pytest.raises(pads.PadLookupError) as excinfo:
        pads.pad_map("ttsky25a", "tt_um_tnt_mosbius")
    message = str(excinfo.value)
    assert "https://tinytapeout.com/chips/ttsky25a/tt_um_tnt_mosbius" in message
    assert "pads_ttsky25a_tt_um_tnt_mosbius.html" in message


def test_a_missing_page_names_the_project_and_shuttle(cached_page, monkeypatch):
    """404 means this macro is not on this shuttle, which is a different
    problem from no internet and deserves a different sentence: the usual
    cause is the wrong chip in the socket or a mistyped --project.
    """
    cached_page(macro="tt_um_other")

    def not_found(*args, **kwargs):
        raise urllib.error.HTTPError("u", 404, "Not Found", {}, None)
    monkeypatch.setattr(pads.urllib.request, "urlopen", not_found)

    with pytest.raises(pads.PadLookupError, match="no page for tt_um_tnt_mosbius"):
        pads.pad_map("ttsky25a", "tt_um_tnt_mosbius")


def test_a_fetched_page_is_cached_for_next_time(cached_page, monkeypatch, tmp_path):
    """One download per project per shuttle: a bench with no internet needs
    the fetch to have happened once, not every run.
    """
    cached_page(macro="tt_um_other")

    class Response:
        def read(self):
            return REAL_PAGE.encode()
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    monkeypatch.setattr(pads.urllib.request, "urlopen", lambda *a, **k: Response())
    assert pads.pad_map("ttsky25a", "tt_um_tnt_mosbius") == TNT_MOSBIUS_PADS
    assert (tmp_path / "pads_ttsky25a_tt_um_tnt_mosbius.html").exists()
