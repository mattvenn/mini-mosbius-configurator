# SPDX-License-Identifier: Apache-2.0
"""mosbius/cli.py -- thin argv->function wrappers (M5). Each subcommand
just calls an already-tested library function, so these tests check
dispatch and formatting, not the underlying logic (covered elsewhere).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from mosbius.cli import main

INVERTER_NETLIST = """
nfeta_0 ua1 ua2 VGND VGND mosbius_nmos w=1
pfeta_1 ua1 ua2 VAPWR VAPWR mosbius_pmos w=1
"""

INVERTER_BITSTREAM = "080000004010000001000000000000000040000400000000"


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


def test_no_subcommand_is_an_argparse_error():
    with pytest.raises(SystemExit):
        main([])
