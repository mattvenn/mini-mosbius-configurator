# SPDX-License-Identifier: Apache-2.0
"""Shared test helpers: look up chain bits by pin name, and a hand-built
CMOS inverter SwitchConfig used across test_check.py and test_decode.py.
"""

from __future__ import annotations

import pytest

from mosbius.bitmap import DEVICE_SETTING_BITS, MATRIX_BITS
from mosbius.model import SwitchConfig


def bit_for(pin: str, index: int) -> int:
    """The chain bit number for a matrix pin's given [index]."""
    for b, mb in MATRIX_BITS.items():
        if mb.pin == pin and mb.index == index:
            return b
    raise KeyError(f"no matrix bit for {pin}[{index}]")


def setting_bit(pin: str, index: int = 0) -> int:
    """The chain bit number for a device-setting pin's given bit index."""
    for b, sb in DEVICE_SETTING_BITS.items():
        if sb.pin == pin and sb.index == index:
            return b
    raise KeyError(f"no device-setting bit for {pin}[{index}]")


def make_inverter_config() -> SwitchConfig:
    """A hand-routed CMOS inverter, built directly from the bit map:

        nfeta.g = pfeta.g = ua[1]  (input, bus_A[1])
        nfeta.d = pfeta.d = ua[2]  (output, bus_A[3])
        nfeta.s -> VGND   (ctrl_nfeta_source)
        pfeta.s -> VAPWR  (ctrl_pfeta_source)

    This is the same shape as SPEC.md Sec 3.8's illustrative `mosbius
    decode` example, but built against the actual verified bit map rather
    than that pre-M0 mockup hex string (see M1 notes: that example string
    doesn't decode cleanly under the real map -- it was written before
    Sec 2.9 was resolved).
    """
    bits = {
        bit_for("cfga_nfeta_g", 1),
        bit_for("cfga_pfeta_g", 1),
        bit_for("cfga_nfeta_d", 3),
        bit_for("cfga_pfeta_d", 3),
        setting_bit("ctrl_nfeta_source"),
        setting_bit("ctrl_pfeta_source"),
    }
    return SwitchConfig(bits=frozenset(bits))


@pytest.fixture
def inverter_config() -> SwitchConfig:
    return make_inverter_config()
