# SPDX-License-Identifier: Apache-2.0
"""mosbius/pads.py: deriving which PCB pad to probe, per shuttle.

These tests never touch the network -- each writes a shuttle index into a
temporary cache directory, which is also the documented offline path for a
bench with no internet.
"""

import json

import pytest

from mosbius import pads
from mosbius.bitstream import unpack
from mosbius.model import SwitchConfig

# tt_um_tnt_mosbius on ttsky25a: design ua[k] -> internal analog index.
TNT_MOSBIUS = {"macro": "tt_um_tnt_mosbius", "analog_pins": [5, 0, 4, 1, 3, 2]}

INVERTER = "080000004010000001000000000000000040000400000000"
RING = "3f008803f004001401000210188406000050040100000019"


@pytest.fixture
def cached_index(tmp_path, monkeypatch):
    def install(projects, shuttle="ttsky25a"):
        monkeypatch.setattr(pads, "CACHE_DIR", tmp_path)
        (tmp_path / f"shuttle_{shuttle}.json").write_text(json.dumps({"projects": projects}))
    return install


def test_pad_map_composes_the_two_lookups(cached_index):
    cached_index([TNT_MOSBIUS])
    assert pads.pad_map("ttsky25a", "tt_um_tnt_mosbius") == {
        "ibias": "K", "ua1": "C", "ua2": "J", "ua3": "D", "ua4": "G", "ua5": "F",
    }


def test_a_different_placement_gives_different_pads(cached_index):
    """The point of deriving rather than hard-coding: the same design on a
    shuttle that placed it elsewhere comes out on other pads."""
    cached_index([{"macro": "tt_um_tnt_mosbius", "analog_pins": [0, 1, 2, 3, 4, 5]}])
    assert pads.pad_map("ttsky25a", "tt_um_tnt_mosbius")["ua1"] == "D"


def test_pads_in_use_follows_the_bitstream(cached_index):
    cached_index([TNT_MOSBIUS])
    config = SwitchConfig(bits=unpack(INVERTER))
    # the inverter wires ua1 and ua2 only, and needs no bias current
    assert pads.pads_in_use(config, "ttsky25a", "tt_um_tnt_mosbius") == {"ua1": "C", "ua2": "J"}


def test_pads_in_use_includes_the_ring_buffer_output(cached_index):
    cached_index([TNT_MOSBIUS])
    config = SwitchConfig(bits=unpack(RING))
    in_use = pads.pads_in_use(config, "ttsky25a", "tt_um_tnt_mosbius")
    assert in_use == {"ua1": "C", "ua2": "J", "ua3": "D"}
    # rail-tied diff-pair sources short the tail bank out, so no bias is drawn
    assert "ibias" not in in_use


def test_unknown_project_says_which_shuttle_was_searched(cached_index):
    cached_index([TNT_MOSBIUS])
    with pytest.raises(pads.PadLookupError, match="not in the ttsky25a shuttle index"):
        pads.pad_map("ttsky25a", "tt_um_someone_else")


def test_project_without_analog_pins_is_explained(cached_index):
    cached_index([{"macro": "tt_um_digital"}])
    with pytest.raises(pads.PadLookupError, match="no analog pins"):
        pads.pad_map("ttsky25a", "tt_um_digital")


def test_index_beyond_the_boards_pads_is_refused(cached_index):
    """A board this code does not know how to letter must fail loudly: a
    wrong pad shows up as a probe reading nothing, which is hard to debug."""
    cached_index([{"macro": "tt_um_wide", "analog_pins": [0, 1, 2, 3, 4, 9]}])
    with pytest.raises(pads.PadLookupError, match="analog index 9"):
        pads.pad_map("ttsky25a", "tt_um_wide")
