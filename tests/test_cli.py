# SPDX-License-Identifier: Apache-2.0
"""mosbius/cli.py -- thin argv->function wrappers (M5). Each subcommand
just calls an already-tested library function, so these tests check
dispatch and formatting, not the underlying logic (covered elsewhere).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import urllib.error

import pytest

from mosbius import pads
from tests.test_pads import REAL_ENTRY as ANALOG_PINS_ENTRY
from mosbius.cli import main
from mosbius.program import ProgramError

INVERTER_NETLIST = """
nfeta_0 ua1 ua2 VGND VGND mosbius_nmos w=1
pfeta_1 ua1 ua2 VAPWR VAPWR mosbius_pmos w=1
"""

INVERTER_BITSTREAM = "080000004010000001000000000000000040000400000000"


@pytest.fixture(autouse=True)
def offline_project_entry(tmp_path, monkeypatch):
    """No test here may reach the network. `program` and `pads` both print
    the pad table, whose ua -> analog pin half comes off the Tiny Tapeout
    shuttle index, so every test in this file gets a cached copy -- the same
    file a bench with no internet saves by hand (mosbius/pads.py).
    """
    monkeypatch.setattr(pads, "CACHE_DIR", tmp_path)

    # Belt and braces: a cached entry only covers the macro it was written
    # for, so a test naming an unknown project would otherwise fall through
    # to a real fetch of the shuttle index. Block the socket outright.
    def no_network(*args, **kwargs):
        raise urllib.error.URLError("network disabled in tests")
    monkeypatch.setattr(pads.urllib.request, "urlopen", no_network)

    def install(shuttle="ttsky25a", macro="tt_um_tnt_mosbius"):
        (tmp_path / f"pads_{shuttle}_{macro}.json").write_text(
            json.dumps(ANALOG_PINS_ENTRY)
        )

    install()
    return install


@pytest.fixture(autouse=True)
def board_in_the_socket(monkeypatch):
    """And no test here may reach a real demoboard either. `pads` asks the
    chip in the socket which shuttle it came from, which would otherwise
    shell out to mpremote -- and pass or fail depending on whether the
    machine running the tests happens to have hardware plugged in.

    The default here is the ordinary bench case: a ttsky25a part carrying
    this project. Tests for the two ways of not knowing patch over it.
    """
    monkeypatch.setattr(
        "mosbius.cli.read_board_identity",
        lambda **kw: {
            "shuttle": "ttsky25a", "has_project": True, "identity_source": "chip ROM",
            "repo": "TinyTapeout/tinytapeout-sky-25a", "commit": "85e372cf",
        },
    )


def test_decode_prints_devices(capsys):
    rc = main(["decode", INVERTER_BITSTREAM])
    out = capsys.readouterr().out
    assert rc == 0
    assert "nmos_a" in out and "pmos_a" in out


def test_check_reports_ok_and_hides_info_by_default(capsys):
    rc = main(["check", INVERTER_BITSTREAM])
    out = capsys.readouterr().out
    assert rc == 0
    assert "OK" in out
    assert "hidden" in out
    assert "does nothing" not in out


def test_check_verbose_shows_info(capsys):
    rc = main(["check", INVERTER_BITSTREAM, "--verbose"])
    out = capsys.readouterr().out
    assert rc == 0
    # merge_findings (TODO.md was Sec 3) collapses every sparse segment
    # into one "do nothing" block rather than repeating the explanation
    # per segment -- assert on the shared explanation, not the headline
    # verb, so this doesn't depend on how many segments happen to merge.
    # Normalised: the body is wrapped, so phrases span line breaks.
    flat = " ".join(out.split())
    assert "none of these segments is wiring anything together" in flat


def test_check_nonzero_exit_on_errors(capsys):
    # bits 170, 174, 5 -- the same deliberate E1 supply short used in
    # tests/test_program.py.
    from mosbius.bitstream import pack
    bitstream = pack(frozenset({170, 174, 5}))
    rc = main(["check", bitstream])
    out = capsys.readouterr().out
    assert rc == 1
    assert "DANGEROUS" in out


def test_route_writes_and_reuses_sticky_config(tmp_path: Path, capsys):
    netlist = tmp_path / "inverter.spice"
    netlist.write_text(INVERTER_NETLIST)
    config_path = tmp_path / "design.mosbius.json"

    rc = main(["route", str(netlist), "--out", str(config_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert config_path.exists()
    assert INVERTER_BITSTREAM in out
    assert "nfeta_0" in out and "-> nmos_a" in out


def test_route_without_out_does_a_fresh_route_each_time(tmp_path: Path, capsys):
    netlist = tmp_path / "inverter.spice"
    netlist.write_text(INVERTER_NETLIST)
    rc = main(["route", str(netlist)])
    out = capsys.readouterr().out
    assert rc == 0
    assert INVERTER_BITSTREAM in out


def test_route_reports_impossible_on_bad_netlist(tmp_path: Path, capsys):
    netlist = tmp_path / "broken.spice"
    netlist.write_text("* nothing here\n")
    rc = main(["route", str(netlist)])
    err = capsys.readouterr().err
    assert rc == 1
    assert "IMPOSSIBLE" in err


def test_simulate_reports_cant_simulate_on_a_netlist(tmp_path: Path, capsys):
    # The netlist, not the routed design JSON `mosbius route --out` writes:
    # a failed exit and an explanation, not a JSONDecodeError traceback.
    netlist = tmp_path / "inverter.spice"
    netlist.write_text(INVERTER_NETLIST)
    rc = main(["simulate", str(netlist)])
    err = capsys.readouterr().err
    assert rc == 1
    assert "CAN'T SIMULATE" in err
    assert "xschem netlist" in err
    assert "Traceback" not in err


def test_watch_once_delegates_to_watch_module(tmp_path: Path, capsys):
    netlist = tmp_path / "inverter.spice"
    netlist.write_text(INVERTER_NETLIST)
    rc = main(["watch", str(netlist), "--once"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "OK" in out


def test_program_refuses_unsafe_bitstream_without_reaching_hardware(capsys):
    from mosbius.bitstream import pack
    bitstream = pack(frozenset({170, 174, 5}))
    with patch("mosbius.cli.program") as mock_program:
        from mosbius.program import ProgramError
        mock_program.side_effect = ProgramError("UPLOAD BLOCKED -- 1 safety error found")
        rc = main(["program", bitstream])
    err = capsys.readouterr().err
    assert rc == 1
    assert "UPLOAD BLOCKED" in err
    mock_program.assert_called_once()


def test_program_success_prints_ok(capsys):
    with patch("mosbius.cli.program") as mock_program:
        mock_program.return_value = {"ok": True, "verify_ok": None}
        rc = main(["program", INVERTER_BITSTREAM, "--project", "tt_um_tnt_mosbius"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "OK" in out
    _, kwargs = mock_program.call_args
    assert kwargs["project"] == "tt_um_tnt_mosbius"
    assert kwargs["reset"] is True
    assert kwargs["verify"] is False


def test_program_passes_no_reset_and_verify_flags(capsys):
    with patch("mosbius.cli.program") as mock_program:
        mock_program.return_value = {"ok": True, "verify_ok": True}
        main(["program", INVERTER_BITSTREAM, "--no-reset", "--verify", "--force", "--port", "/dev/ttyACM0"])
    _, kwargs = mock_program.call_args
    assert kwargs["reset"] is False
    assert kwargs["verify"] is True
    assert kwargs["force"] is True
    assert kwargs["port"] == "/dev/ttyACM0"


def test_pads_prints_the_bench_wiring_table(capsys):
    rc = main(["pads", INVERTER_BITSTREAM])
    out = capsys.readouterr().out
    assert rc == 0
    # the inverter wires ua1 and ua2, which this placement puts on C and J
    assert "C" in out and "ua1" in out
    assert "J" in out and "ua2" in out
    # and it says what is on each, in the words the schematic used
    assert "gate" in out and "drain" in out


def test_pads_explains_an_unknown_project_rather_than_tracebacking(capsys):
    """A macro with no cached index entry (and, here, no network to fetch
    one) has no pads, and the message has to name the URL that would have
    had them plus where to save it.
    """
    rc = main(["pads", INVERTER_BITSTREAM, "--project", "tt_um_not_here"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "CAN'T WORK OUT THE PADS" in err
    assert "https://index.tinytapeout.com/ttsky25a/tt_um_not_here.json" in err
    assert "pads_ttsky25a_tt_um_not_here.json" in err


def test_program_prints_the_pad_table_after_uploading(capsys):
    """The upload is only half of what someone at the bench needs -- the
    other half is where to put the probe.
    """
    with patch("mosbius.cli.program") as mock_program:
        mock_program.return_value = {"ok": True, "verify_ok": None, "shuttle": "ttsky25a"}
        rc = main(["program", INVERTER_BITSTREAM])
    out = capsys.readouterr().out
    assert rc == 0
    assert "OK -- uploaded" in out
    assert "Pads in use" in out and "ua1" in out


def test_program_still_succeeds_when_the_pad_table_cannot_be_built(capsys):
    """The bits are on the chip either way: a missing shuttle index is a
    note, not a failed upload.
    """
    with patch("mosbius.cli.program") as mock_program:
        mock_program.return_value = {"ok": True, "verify_ok": None, "shuttle": "tt_next"}
        rc = main(["program", INVERTER_BITSTREAM])
    captured = capsys.readouterr()
    assert rc == 0
    assert "OK -- uploaded" in captured.out
    assert "uploaded fine" in captured.err


def test_no_subcommand_is_an_argparse_error():
    with pytest.raises(SystemExit):
        main([])


# ---------------------------------------------------------------------------
# Argument handling: a routed design JSON where a bitstream is expected.
# ---------------------------------------------------------------------------

def test_decode_accepts_a_routed_design_json(tmp_path, capsys):
    """Handing decode the file the rest of the pipeline passes around is the
    obvious thing to try, and used to end in a BitstreamError traceback.
    """
    routed = tmp_path / "ring.mosbius.json"
    routed.write_text(json.dumps({"bitstream": "0" * 46 + "10"}))
    assert main(["decode", str(routed)]) == 0
    assert "Devices in use" in capsys.readouterr().out


def test_decode_explains_a_file_that_is_not_routed_json(tmp_path, capsys):
    netlist = tmp_path / "ring.spice"
    netlist.write_text("XM1 a b VGND VGND mosbius_nmos w=1\n")
    assert main(["decode", str(netlist)]) == 1
    err = capsys.readouterr().err
    assert "does not parse as JSON" in err
    assert "mosbius.cli route" in err  # names the command that fixes it


def test_decode_explains_json_without_a_bitstream(tmp_path, capsys):
    stray = tmp_path / "other.json"
    stray.write_text(json.dumps({"device_roles": {}}))
    assert main(["decode", str(stray)]) == 1
    assert 'no "bitstream" in it' in capsys.readouterr().err


def test_decode_reports_a_bad_bitstream_without_a_traceback(capsys):
    assert main(["decode", "deadbeef"]) == 1
    err = capsys.readouterr().err
    assert "expected exactly 48" in err
    assert "Traceback" not in err


def test_program_accepts_a_routed_design_json(tmp_path, capsys):
    """`program` was the one command that took only the 48 hex characters,
    so the routed design the rest of the pipeline passes around had to be
    unpacked by hand on the command line.
    """
    routed = tmp_path / "inverter.mosbius.json"
    routed.write_text(json.dumps({"bitstream": INVERTER_BITSTREAM}))
    with patch("mosbius.cli.program") as mock_program:
        mock_program.return_value = {"ok": True, "verify_ok": True}
        rc = main(["program", str(routed), "--verify"])
    assert rc == 0
    assert "OK" in capsys.readouterr().out
    config, = mock_program.call_args[0]
    assert config.to_bitstream() == INVERTER_BITSTREAM


def test_program_explains_a_missing_routed_design_without_reaching_hardware(tmp_path, capsys):
    """A path that isn't there used to fall through to from_bitstream() and
    come back as "27 hex characters, expected 48" -- unreadable to someone
    who simply hasn't run `route` yet.
    """
    missing = tmp_path / "inverter.mosbius.json"
    with patch("mosbius.cli.program") as mock_program:
        rc = main(["program", str(missing)])
    assert rc == 1
    mock_program.assert_not_called()
    err = capsys.readouterr().err
    assert "there is no file at" in err
    assert "mosbius.cli route" in err  # names the step that writes it
    assert "hex" not in err


def test_a_bare_bitstream_is_still_not_treated_as_a_path(capsys):
    """48 hex characters have no slash and no suffix, so they must not trip
    the missing-file branch.
    """
    with patch("mosbius.cli.program") as mock_program:
        mock_program.return_value = {"ok": True, "verify_ok": None}
        assert main(["program", INVERTER_BITSTREAM]) == 0
    assert mock_program.called


def test_pads_reads_the_shuttle_off_the_chip_in_the_socket(capsys, monkeypatch, offline_project_entry):
    """Which pad a ua[k] comes out on depends on the shuttle, and the chip
    carries its own shuttle in ROM -- so put a different chip in the socket
    and the table follows it, with no flag to remember.
    """
    offline_project_entry(shuttle="ttsky99z")
    monkeypatch.setattr(
        "mosbius.cli.read_board_identity",
        lambda **kw: {"shuttle": "ttsky99z", "has_project": True, "identity_source": "chip ROM"},
    )
    rc = main(["pads", INVERTER_BITSTREAM])
    out = capsys.readouterr().out
    assert rc == 0
    assert "ttsky99z" in out


def test_pads_fails_rather_than_guessing_when_no_board_answers(capsys, monkeypatch):
    """A pad table is an instruction to clip a probe onto a letter, so a
    guessed one is worse than none -- and a chip you can't reach is a chip
    you couldn't have programmed either. It must name --shuttle as the way
    to read the table away from the bench.
    """
    def refuse(**kw):
        raise ProgramError("CAN'T READ THE BOARD -- no result from the board")
    monkeypatch.setattr("mosbius.cli.read_board_identity", refuse)
    rc = main(["pads", INVERTER_BITSTREAM])
    captured = capsys.readouterr()
    assert rc == 1
    assert "ttsky25a" not in captured.out  # no guessed table at all
    assert "--shuttle" in captured.err and "CAN'T READ THE BOARD" in captured.err


def test_pads_fails_when_the_project_is_not_on_the_chip_present(capsys, monkeypatch):
    """Same reasoning the other way round: the board answered, but this
    bitstream could not be programmed to that chip, so there are no pads.
    """
    monkeypatch.setattr(
        "mosbius.cli.read_board_identity",
        lambda **kw: {"shuttle": "ttsky25a", "has_project": False},
    )
    rc = main(["pads", INVERTER_BITSTREAM])
    err = capsys.readouterr().err
    assert rc == 1
    assert "is not on it" in err and "cannot be programmed" in err


def test_program_says_where_the_shuttle_came_from(capsys):
    with patch("mosbius.cli.program") as mock_program:
        mock_program.return_value = {
            "ok": True, "verify_ok": True, "shuttle": "ttsky25a",
            "repo": "TinyTapeout/tinytapeout-sky-25a", "commit": "85e372cf",
            "identity_source": "chip ROM",
        }
        rc = main(["program", INVERTER_BITSTREAM])
    out = capsys.readouterr().out
    assert rc == 0
    assert "read from the chip in the socket" in out
    assert "TinyTapeout/tinytapeout-sky-25a" in out and "85e372cf" in out


def test_program_prints_no_pad_table_when_the_board_reported_no_shuttle(capsys):
    """The bits are on the chip, so this is not a failed upload -- but the
    pad letters are per shuttle, and a guessed table looks exactly like a
    measured one.
    """
    with patch("mosbius.cli.program") as mock_program:
        mock_program.return_value = {"ok": True, "verify_ok": None}
        rc = main(["program", INVERTER_BITSTREAM])
    captured = capsys.readouterr()
    assert rc == 0
    assert "OK -- uploaded" in captured.out
    assert "PCB pad" not in captured.out
    assert "--shuttle" in captured.err


class TestIbiasWarning:
    """The bias current a board could not deliver has to be said out loud.

    Only the later ETR demoboards carry the RP2350-controlled bias circuit.
    On an older one the upload is still good and the bits are still right,
    so this is a warning beside a success, never a failure -- but staying
    silent leaves every mirror and tail in the design unbiased.
    """

    def _config(self, ibias):
        from mosbius.bitstream import unpack
        from mosbius.model import SwitchConfig
        return SwitchConfig(bits=unpack("0" * 48), ibias=ibias)

    def test_names_the_current_and_what_it_affects(self):
        from mosbius.program import ibias_warning
        text = ibias_warning({"ibias_set": False}, self._config(100e-6))
        assert "100.0 uA" in text
        assert "mosbius_ota" in text and "mosbius_nsink" in text
        assert "tools/measure_ibias_clamp_ad3.py" in text
        assert "on the chip and correct" in text  # not a failed upload

    def test_silent_when_the_board_did_set_it(self):
        from mosbius.program import ibias_warning
        assert ibias_warning({"ibias_set": True}, self._config(100e-6)) is None

    def test_silent_when_the_board_never_said(self):
        # A device script older than the ibias_set field must not produce a
        # warning about hardware we know nothing about.
        from mosbius.program import ibias_warning
        assert ibias_warning({}, self._config(100e-6)) is None

    def test_silent_when_no_bias_was_asked_for(self):
        from mosbius.program import ibias_warning
        assert ibias_warning({"ibias_set": False}, self._config(0)) is None
