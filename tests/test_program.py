# SPDX-License-Identifier: Apache-2.0
"""mosbius/program.py -- SPEC.md Sec 3.5 hardware programming (M4).

None of this can exercise real hardware in this environment (no demoboard
attached). What IS testable without one, and is covered here:

  - generate_device_script(): the generated MicroPython source is correct
    text -- right bit string, right MSB-first order, the enable-low-for-
    the-whole-shift safety invariant holds, ibias/project/reset/verify are
    threaded through correctly.
  - _ibias_level(): the amps->level conversion and its clamping.
  - program()'s safety gate: refuses on a checker ERROR unless force=True,
    with no attempt to reach mpremote at all in that case.
  - _run_mpremote()'s result-parsing/error-handling logic, with subprocess
    and the mpremote binary itself mocked out.

What's NOT covered here, and can't be without a board: that the generated
script actually runs correctly on a real RP2040 against a real chip
(Sec 8.4's exit criterion) -- see program.py's module docstring.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from mosbius.check import check
from mosbius.model import SwitchConfig
from mosbius.program import (
    ProgramError,
    _ibias_level,
    _run_mpremote,
    generate_device_script,
    generate_identity_script,
    program,
    read_board_identity,
)

from .conftest import make_inverter_config

# A deliberate E1 supply short, built directly from the bit map (not routed
# through mosbius.route -- this only needs to trip check(), not be a real
# circuit): bit 170 taps bus_B[6] to VAPWR, bit 174 taps bus_A[6] to VGND,
# and bit 5 closes cfg_bus_short[6], joining bus_A[6] and bus_B[6] -- so
# VAPWR and VGND end up on the same node.
SHORTED_BITS = frozenset({170, 174, 5})


# ---------------------------------------------------------------------------
# generate_device_script()
# ---------------------------------------------------------------------------

def test_bit_string_is_msb_first_and_matches_config_bits():
    config = make_inverter_config()
    script = generate_device_script(config, project="tt_um_tnt_mosbius")

    line = next(l for l in script.splitlines() if l.startswith("BITS ="))
    bit_string = line.split('"')[1]

    assert len(bit_string) == 192
    # BITS[0] is chain bit 191 (MSB first); BITS[191] is chain bit 0.
    for i, ch in enumerate(bit_string):
        chain_bit = 191 - i
        assert ch == ("1" if chain_bit in config.bits else "0")


def test_enable_held_low_for_entire_shift_loop():
    """Sec 3.5 / CLAUDE.md's core safety invariant: enable (ui_in[1]) must
    not go high until after the last bit of the 192-bit shift.
    """
    script = generate_device_script(make_inverter_config(), project="p")

    first_enable_high = script.index('tt.ui_in[1] = 1')
    shift_loop = script.index("for bit_char in BITS:")
    assert shift_loop < first_enable_high, (
        "enable must be raised after the shift loop, not before or during it"
    )
    # And it's held explicitly low right before anything else happens.
    enable_low = script.index("tt.ui_in[1] = 0")
    assert enable_low < shift_loop


def test_project_reset_verify_are_threaded_through():
    script = generate_device_script(
        make_inverter_config(), project="tt_um_tnt_mosbius", reset=False, verify=True,
    )
    assert "PROJECT = 'tt_um_tnt_mosbius'" in script
    assert "DO_RESET = False" in script
    assert "DO_VERIFY = True" in script


def test_verify_off_by_default():
    script = generate_device_script(make_inverter_config(), project="p")
    assert "DO_VERIFY = False" in script


def test_ibias_level_encoded_in_script():
    config = SwitchConfig(bits=make_inverter_config().bits, ibias=125e-6)
    script = generate_device_script(config, project="p")
    assert f"IBIAS_LEVEL = {_ibias_level(125e-6)!r}" in script


def test_demoboard_get_takes_no_arguments():
    """Regression check for a real bug caught during development: DemoBoard
    .get() takes zero arguments upstream -- mode must be set via the
    property setter afterward, not passed into get().
    """
    script = generate_device_script(make_inverter_config(), project="p")
    assert "DemoBoard.get()" in script
    assert "DemoBoard.get(mode=" not in script
    assert "tt.mode = RPMode.ASIC_RP_CONTROL" in script


# ---------------------------------------------------------------------------
# _ibias_level()
# ---------------------------------------------------------------------------

def test_ibias_level_zero_amps_is_zero():
    assert _ibias_level(0.0) == 0


def test_ibias_level_at_approx_max_is_full_scale():
    assert _ibias_level(250e-6) == 0xFFFF


def test_ibias_level_clamps_above_max():
    assert _ibias_level(1.0) == 0xFFFF


def test_ibias_level_clamps_below_zero():
    assert _ibias_level(-1.0) == 0


def test_ibias_level_is_monotonic():
    assert _ibias_level(50e-6) < _ibias_level(150e-6) < _ibias_level(250e-6)


# ---------------------------------------------------------------------------
# program() -- safety gate
# ---------------------------------------------------------------------------

def test_program_refuses_a_config_with_errors_without_reaching_mpremote():
    report = check(SwitchConfig(bits=SHORTED_BITS))
    assert report.has_errors  # sanity: this fixture IS unsafe

    with patch("mosbius.program._run_mpremote") as mock_run:
        with pytest.raises(ProgramError, match="UPLOAD BLOCKED"):
            program(SwitchConfig(bits=SHORTED_BITS), report=report)
        mock_run.assert_not_called()


def test_program_force_bypasses_the_safety_gate():
    report = check(SwitchConfig(bits=SHORTED_BITS))
    assert report.has_errors

    with patch("mosbius.program._run_mpremote") as mock_run:
        mock_run.return_value = {"ok": True, "error": None, "verify_ok": None}
        result = program(SwitchConfig(bits=SHORTED_BITS), report=report, force=True)
        mock_run.assert_called_once()
        assert result["ok"] is True


def test_program_safe_config_reaches_mpremote():
    with patch("mosbius.program._run_mpremote") as mock_run:
        mock_run.return_value = {"ok": True, "error": None, "verify_ok": None}
        result = program(make_inverter_config())
        mock_run.assert_called_once()
        assert result["ok"] is True


def test_program_raises_on_device_side_error():
    with patch("mosbius.program._run_mpremote") as mock_run:
        mock_run.return_value = {"ok": False, "error": "project not found on this shuttle"}
        with pytest.raises(ProgramError, match="project not found"):
            program(make_inverter_config())


def test_program_raises_when_verify_readback_mismatches():
    with patch("mosbius.program._run_mpremote") as mock_run:
        mock_run.return_value = {
            "ok": True, "error": None, "verify_ok": False, "captured": "0" * 192,
        }
        with pytest.raises(ProgramError, match="VERIFY FAILED"):
            program(make_inverter_config(), verify=True)


def test_program_passes_when_verify_readback_matches():
    with patch("mosbius.program._run_mpremote") as mock_run:
        mock_run.return_value = {"ok": True, "error": None, "verify_ok": True}
        result = program(make_inverter_config(), verify=True)
        assert result["verify_ok"] is True


# ---------------------------------------------------------------------------
# _run_mpremote()
# ---------------------------------------------------------------------------

def test_run_mpremote_raises_clearly_when_binary_missing():
    with patch("mosbius.program.shutil.which", return_value=None):
        with pytest.raises(ProgramError, match="mpremote isn't installed"):
            _run_mpremote("print('hi')", port=None)


def test_run_mpremote_raises_clearly_when_no_result_line():
    fake_proc = type("P", (), {"stdout": "some unrelated boot noise\n", "stderr": "", "returncode": 0})()
    with patch("mosbius.program.shutil.which", return_value="/usr/bin/mpremote"), \
         patch("mosbius.program.subprocess.run", return_value=fake_proc):
        with pytest.raises(ProgramError, match="no result from the board"):
            _run_mpremote("print('hi')", port=None)


def test_run_mpremote_parses_result_line():
    payload = {"ok": True, "error": None, "verify_ok": None}
    fake_proc = type("P", (), {
        "stdout": f"boot noise\nMOSBIUS_RESULT:{json.dumps(payload)}\n",
        "stderr": "",
        "returncode": 0,
    })()
    with patch("mosbius.program.shutil.which", return_value="/usr/bin/mpremote"), \
         patch("mosbius.program.subprocess.run", return_value=fake_proc):
        result = _run_mpremote("print('hi')", port=None)
        assert result == payload


def test_run_mpremote_passes_port_when_given():
    payload = {"ok": True, "error": None, "verify_ok": None}
    fake_proc = type("P", (), {
        "stdout": f"MOSBIUS_RESULT:{json.dumps(payload)}\n", "stderr": "", "returncode": 0,
    })()
    with patch("mosbius.program.shutil.which", return_value="/usr/bin/mpremote"), \
         patch("mosbius.program.subprocess.run", return_value=fake_proc) as mock_run:
        _run_mpremote("print('hi')", port="/dev/ttyACM0")
        cmd = mock_run.call_args[0][0]
        assert "connect" in cmd and "/dev/ttyACM0" in cmd


# ---------------------------------------------------------------------------
# read_board_identity() -- which chip is actually in the socket
#
# The shuttle decides which PCB pad each ua[k] comes out on, so reading it
# off the chip's own ROM is what stops `mosbius pads` from printing a table
# for a chip that isn't there. The device half was checked on a real
# demoboard (chip_ROM.shuttle == 'ttsky25a', 2026-08-29); these cover the
# host half with mpremote mocked.
# ---------------------------------------------------------------------------

def _fake_board(payload):
    proc = type("P", (), {
        "stdout": f"MOSBIUS_RESULT:{json.dumps(payload)}\n", "stderr": "", "returncode": 0,
    })()
    return (
        patch("mosbius.program.shutil.which", return_value="/usr/bin/mpremote"),
        patch("mosbius.program.subprocess.run", return_value=proc),
    )


def test_identity_script_is_valid_python_and_changes_nothing():
    script = generate_identity_script("tt_um_tnt_mosbius")
    compile(script, "identity", "exec")
    # Reading which chip is present must not touch the chip's state: no
    # enable, no clocking, no project selection, no bias.
    for forbidden in ("ui_in", "clock_project_once", "reset_project", "enable()", "analog_current_source"):
        assert forbidden not in script, forbidden
    assert "DemoboardDetect.probe()" in script  # still needed after mpremote's soft reset


def test_identity_script_omits_project_lookup_when_not_asked():
    assert "PROJECT = None" in generate_identity_script()


def test_read_board_identity_returns_what_the_rom_said():
    payload = {
        "ok": True, "error": None, "shuttle": "ttsky25a",
        "repo": "TinyTapeout/tinytapeout-sky-25a", "commit": "85e372cf",
        "identity_source": "chip ROM", "has_project": True,
    }
    which, run = _fake_board(payload)
    with which, run:
        assert read_board_identity(project="tt_um_tnt_mosbius") == payload


def test_read_board_identity_explains_a_board_that_reports_no_shuttle():
    which, run = _fake_board({"ok": True, "error": None})
    with which, run:
        with pytest.raises(ProgramError, match="reported no shuttle"):
            read_board_identity()


def test_read_board_identity_does_not_call_itself_a_failed_upload():
    # It reads; it never programs. Saying "CAN'T PROGRAM" here would send
    # someone hunting for a bad bitstream.
    proc = type("P", (), {"stdout": "boot noise\n", "stderr": "", "returncode": 1})()
    with patch("mosbius.program.shutil.which", return_value="/usr/bin/mpremote"), \
         patch("mosbius.program.subprocess.run", return_value=proc):
        with pytest.raises(ProgramError) as excinfo:
            read_board_identity()
    assert "CAN'T READ THE BOARD" in str(excinfo.value)
    assert "CAN'T PROGRAM" not in str(excinfo.value)


def test_device_script_reads_the_identity_it_reports_back():
    script = generate_device_script(make_inverter_config(), project="tt_um_tnt_mosbius")
    assert "chip_ROM" in script and "_read_identity(tt)" in script


def test_device_script_reports_bias_delivery_separately_from_failure():
    # The regression: this used to be written into result["error"], which the
    # host only reads when result["ok"] is False -- and "ok" goes True on this
    # very path. So a board with no bias circuit reported a clean upload and a
    # pad table asserting a current nothing had supplied.
    script = generate_device_script(make_inverter_config(), project="tt_um_tnt_mosbius")
    assert '"ibias_set": None' in script
    assert 'result["ibias_set"] = True' in script
    assert 'result["ibias_set"] = False' in script
    bias_block = script.split("analog_current_source")[1]
    assert 'result["error"]' not in bias_block.split("Sec 3.5 step 1")[0]
