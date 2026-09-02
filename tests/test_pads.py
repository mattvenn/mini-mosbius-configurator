# SPDX-License-Identifier: Apache-2.0
"""mosbius/pads.py: deriving which PCB pad to probe, per shuttle.

These tests never touch the network -- each writes a project's shuttle-index
entry into a temporary cache directory, which is also the documented offline
path for a bench with no internet (save
https://index.tinytapeout.com/<shuttle>/<macro>.json as
build/pads_<shuttle>_<macro>.json).
"""


import json
import urllib.error

import pytest

from mosbius import messages, pads
from mosbius.bitstream import unpack
from mosbius.model import SwitchConfig

# tt_um_tnt_mosbius's entry in the ttsky25a index, exactly as
# https://index.tinytapeout.com/ttsky25a/tt_um_tnt_mosbius.json serves it,
# fetched 2026-08-29. Trimmed to the fields this module reads plus enough
# neighbours to keep it recognisable as the real document.
REAL_ENTRY = {
    "macro": "tt_um_tnt_mosbius",
    "address": 239,
    "title": "tnt's variant of SKY130 mini-MOSbius",
    "author": "Sylvain Munaut",
    "clock_hz": 0,
    "tiles": "3x2",
    "analog_pins": [5, 0, 4, 1, 3, 2],
    "pinout": {
        "ua[0]": "Reference Bias",
        "ua[1]": "Bus 1A",
        "ua[2]": "Bus 2A",
        "ua[3]": "Bus 3A",
        "ua[4]": "Bus 4A",
        "ua[5]": "Bus 5A",
    },
}

INVERTER = "080000004010000001000000000000000040000400000000"
RING = "3f008803f004001401000210188406000050040100000019"

TNT_MOSBIUS_PADS = {
    "ibias": "K", "ua1": "C", "ua2": "J", "ua3": "D", "ua4": "G", "ua5": "F",
}


@pytest.fixture
def cached_entry(tmp_path, monkeypatch):
    """Install an index entry in the cache, so no test reaches the network.

    This is also the documented offline path: save the project's JSON as
    build/pads_<shuttle>_<macro>.json and the lookup works with no internet.
    """
    monkeypatch.setattr(pads, "CACHE_DIR", tmp_path)

    def no_network(*args, **kwargs):
        raise urllib.error.URLError("network disabled in tests")
    monkeypatch.setattr(pads.urllib.request, "urlopen", no_network)

    def install(entry=REAL_ENTRY, shuttle="ttsky25a", macro="tt_um_tnt_mosbius"):
        body = entry if isinstance(entry, str) else json.dumps(entry)
        (tmp_path / f"pads_{shuttle}_{macro}.json").write_text(body)
    return install


def test_pad_map_composes_the_index_entry_with_the_carrier_wiring(cached_entry):
    """analog_pins [5, 0, 4, 1, 3, 2] through the ETR carrier's
    C D F G J K X W U T R Q gives K C J D G F -- the letters measured on
    silicon, and the ones tinytapeout.com prints for this project.
    """
    cached_entry()
    assert pads.pad_map("ttsky25a", "tt_um_tnt_mosbius") == TNT_MOSBIUS_PADS


def test_the_carrier_wiring_matches_the_boards_it_was_read_off():
    """The one hard-coded half, and the reason it is trusted.

    Verified by joining TinyTapeout/breakout-ttsky-cob's J1 (pin -> an0..an11)
    with TinyTapeout/tt-demo-pcb's J5 L-side (pin -> the ANALOG header
    letters): an0..an11 come out on C D F G J K X W U T R Q. No API
    publishes this, so if it ever changes it changes here, deliberately.
    """
    assert pads.carrier_pads("ttsky25a") == (
        "C", "D", "F", "G", "J", "K", "X", "W", "U", "T", "R", "Q"
    )
    # every letter the carrier can name is a real hole on the header
    header = {cell for row in pads.ANALOG_HEADER for cell in row}
    assert set(pads.carrier_pads("ttsky25a")) <= header


def test_shuttles_before_the_etr_demoboard_use_the_old_breakout_labels():
    """tt06/tt07/tt08 shipped a breakout labelled A0..A5 / B0..B5, not
    letters. Upstream's website means to make this split and does not --
    its `shuttle in nonETRShuttles` tests array indices, never values -- so
    those project pages show ETR letters that mean nothing there. Doing the
    split here is the reason not to scrape them.
    """
    assert pads.carrier_pads("tt07")[0] == "A0"
    assert pads.carrier_pads("tt07")[6] == "B0"
    assert pads.carrier_pads("ttsky25a")[0] == "C"


def test_a_different_shuttle_can_give_entirely_different_pads(cached_entry):
    """The whole reason this is a lookup and not a constant. Where the
    project sits on the shuttle is free to change, so the letters for the
    same design on the next shuttle are not predictable from these ones.
    """
    cached_entry({"analog_pins": [1, 8, 11]}, shuttle="ttsky26b")
    assert pads.pad_map("ttsky26b", "tt_um_tnt_mosbius") == {
        "ibias": "D", "ua1": "U", "ua2": "Q",
    }


def test_ua_zero_is_named_ibias(cached_entry):
    """Every schematic and every other module calls that pin ibias; the
    index calls it ua 0 / "Reference Bias". Translate once, here.
    """
    cached_entry()
    assert pads.pad_map("ttsky25a", "tt_um_tnt_mosbius")["ibias"] == "K"
    assert "ua0" not in pads.pad_map("ttsky25a", "tt_um_tnt_mosbius")


def test_pads_in_use_follows_the_bitstream(cached_entry):
    cached_entry()
    config = SwitchConfig(bits=unpack(INVERTER))
    # the inverter wires ua1 and ua2 only, and needs no bias current
    assert pads.pads_in_use(config, "ttsky25a", "tt_um_tnt_mosbius") == {"ua1": "C", "ua2": "J"}


def test_pads_in_use_includes_the_ring_buffer_output(cached_entry):
    cached_entry()
    config = SwitchConfig(bits=unpack(RING))
    in_use = pads.pads_in_use(config, "ttsky25a", "tt_um_tnt_mosbius")
    assert in_use == {"ua1": "C", "ua2": "J", "ua3": "D"}
    # rail-tied diff-pair sources short the tail bank out, so no bias is drawn
    assert "ibias" not in in_use


def test_a_project_with_no_analog_pins_is_explained(cached_entry):
    """A purely digital project has nothing to probe, and saying so beats
    printing an empty table.
    """
    cached_entry({"macro": "tt_um_digital", "analog_pins": []}, macro="tt_um_digital")
    with pytest.raises(pads.PadLookupError) as excinfo:
        pads.pad_map("ttsky25a", "tt_um_digital")
    url = pads.PROJECT_INDEX_URL.format(shuttle="ttsky25a", macro="tt_um_digital")
    expected = messages.PADS_NO_ANALOG_PINS.format(macro="tt_um_digital", shuttle="ttsky25a", url=url)
    assert str(excinfo.value) == expected


def test_the_wrong_json_saved_by_hand_says_which_file_was_wanted(cached_entry):
    """The offline path is "save this URL here", so the likely mistake is
    saving the whole-shuttle index or the web page instead. That has to name
    the file it wanted rather than raise a JSON traceback.
    """
    cached_entry({"version": 3, "id": "ttsky25a", "projects": []})
    with pytest.raises(pads.PadLookupError) as excinfo:
        pads.pad_map("ttsky25a", "tt_um_tnt_mosbius")
    assert "analog_pins" in str(excinfo.value)
    assert "index.tinytapeout.com/ttsky25a/tt_um_tnt_mosbius.json" in str(excinfo.value)


def test_an_analog_pin_the_carrier_cannot_reach_refuses_to_guess(cached_entry):
    """A future carrier bringing out more analog pins than this one would
    otherwise index off the end of the table. A pad letter is an instruction
    to clip a probe somewhere, so this stops rather than inventing one.
    """
    cached_entry({"analog_pins": [0, 12]})
    with pytest.raises(pads.PadLookupError) as excinfo:
        pads.pad_map("ttsky25a", "tt_um_tnt_mosbius")
    # ua0 -> internal 0 is fine; ua1 -> internal 12 is off the end of the
    # carrier's 12-entry table, which is the one that raises.
    expected = messages.PADS_INTERNAL_PIN_NOT_ON_CARRIER.format(
        macro="tt_um_tnt_mosbius", shuttle="ttsky25a", ua=1, internal=12,
        n_pads=len(pads.ETR_CARRIER_PADS), pads=", ".join(pads.ETR_CARRIER_PADS),
    )
    assert str(excinfo.value) == expected


def test_pad_table_names_the_pad_the_pin_and_what_is_on_it(cached_entry):
    cached_entry()
    table = pads.format_pad_table(
        SwitchConfig(bits=unpack(INVERTER)), "ttsky25a", "tt_um_tnt_mosbius"
    )
    lines = [line.split() for line in table.splitlines() if line.startswith("  C ")]
    assert lines and lines[0][:2] == ["C", "ua1"]
    assert "nmos_a gate" in table and "pmos_a drain" in table
    # the pads this configuration does not use are worth saying too, so
    # nobody probes a pin that is connected to nothing
    assert messages.PADS_TABLE_IDLE_PREFIX in table
    assert "G (ua4)" in table


def test_pad_table_shows_the_bias_pad_only_when_something_draws_on_it(cached_entry):
    """`ibias` is bench setup rather than a signal, and a design that draws
    no bias current does not need it wired at all."""
    cached_entry()
    table = pads.format_pad_table(
        SwitchConfig(bits=unpack(INVERTER)), "ttsky25a", "tt_um_tnt_mosbius"
    )
    assert messages.PADS_TABLE_IBIAS_ROW_PREFIX not in table

    # examples/diffamp: a pair floating off the rail draws its tail current
    biased = pads.format_pad_table(
        SwitchConfig.from_bitstream("00100000c020004820000000004821000000000000000030"),
        "ttsky25a", "tt_um_tnt_mosbius",
    )
    assert messages.PADS_TABLE_ROW.format(pad="K", pin="ibias", what="").rstrip() in biased
    assert messages.PADS_TABLE_IBIAS_ROW.format(amps=100.0, drawn_by="ndiffpair") in biased
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


def test_pad_table_draws_the_header(cached_entry):
    cached_entry()
    config = SwitchConfig(bits=unpack(INVERTER))
    out = pads.format_pad_table(config, "ttsky25a", "tt_um_tnt_mosbius")
    assert messages.PADS_HEADER_TITLE in out
    assert "[C]" in out and "[J]" in out
    assert messages.PADS_HEADER_CAPTION_GROUND_NOTE in out


def test_an_unreachable_index_says_how_to_work_offline(cached_entry):
    """No internet at the bench. There is nothing to fall back on, so the
    message has to be the URL to save and where to put it -- plus the
    project's own page, which has the same answer already composed for
    someone who would rather read it than save a file.
    """
    cached_entry(macro="tt_um_other")   # installs the fixture, not this macro
    with pytest.raises(pads.PadLookupError) as excinfo:
        pads.pad_map("ttsky25a", "tt_um_tnt_mosbius")
    message = str(excinfo.value)
    assert "https://index.tinytapeout.com/ttsky25a/tt_um_tnt_mosbius.json" in message
    assert "pads_ttsky25a_tt_um_tnt_mosbius.json" in message
    assert "https://tinytapeout.com/chips/ttsky25a/tt_um_tnt_mosbius" in message


def test_a_missing_index_entry_names_the_project_and_shuttle(cached_entry, monkeypatch):
    """404 means this macro is not on this shuttle, which is a different
    problem from no internet and deserves a different sentence: the usual
    cause is the wrong chip in the socket or a mistyped --project.
    """
    cached_entry(macro="tt_um_other")

    def not_found(*args, **kwargs):
        raise urllib.error.HTTPError("u", 404, "Not Found", {}, None)
    monkeypatch.setattr(pads.urllib.request, "urlopen", not_found)

    with pytest.raises(pads.PadLookupError) as excinfo:
        pads.pad_map("ttsky25a", "tt_um_tnt_mosbius")
    url = pads.PROJECT_INDEX_URL.format(shuttle="ttsky25a", macro="tt_um_tnt_mosbius")
    expected = messages.PADS_PROJECT_NOT_ON_SHUTTLE.format(
        macro="tt_um_tnt_mosbius", shuttle="ttsky25a", url=url,
    )
    assert str(excinfo.value) == expected


def test_a_fetched_entry_is_cached_for_next_time(cached_entry, monkeypatch, tmp_path):
    """One download per project per shuttle: a bench with no internet needs
    the fetch to have happened once, not every run.
    """
    cached_entry(macro="tt_um_other")

    class Response:
        def read(self):
            return json.dumps(REAL_ENTRY).encode()
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    monkeypatch.setattr(pads.urllib.request, "urlopen", lambda *a, **k: Response())
    assert pads.pad_map("ttsky25a", "tt_um_tnt_mosbius") == TNT_MOSBIUS_PADS
    assert (tmp_path / "pads_ttsky25a_tt_um_tnt_mosbius.json").exists()
