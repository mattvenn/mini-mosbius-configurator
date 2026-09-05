# SPDX-License-Identifier: Apache-2.0
"""What one bit of a config chain means.

Both mini-MOSbius parts shift a chain of bits through the chip and use each
one either to close a switch in the analog matrix or to set a device's width,
ratio or tail. The two parts disagree about how many bits there are and which
bit does what, but not about the shape of the answer, so these two records are
shared and the per-chip tables that use them are generated separately --
`tnt_bits.py` and `kang_bits.py`, both written by tools/extract_bitmap.py.

The chain positions quoted in the comments below are tnt's. Andrew Kang's part
has a 196-bit chain, and its own generated module says so.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MatrixBit:
    """A bit that closes a `tt_asw_3v3` transmission gate.

    Most sit in the switch matrix and connect a crosspoint node (a device
    terminal) to one row of one bus side -- for those, `crosspoint`, `bus` and
    `row` are all set.

    `cfg_bus_short` bits join `bus_A[row]` to `bus_B[row]`, so they have no
    crosspoint and no single side (`crosspoint=None`, `bus=None`).

    `cfg_bus_pwr` (tnt) and `cfga_vapwr`/`cfga_vgnd` (Andrew's) tie one bus
    segment directly to a rail: `crosspoint=None`, `bus` and `rail` set.

    `cfg_bus_ext` (Andrew's only) connects a package pin to a bus row, which is
    a bond wire on tnt's part and so has no bit there at all: `crosspoint=None`,
    `bus` set, and `pin_net` naming the package pin it reaches.
    """

    bit: int          # position in the config chain
    pin: str           # mosbius.sym pin name, e.g. "cfga_nfeta_s"
    index: int         # 1-based index into that pin's [N:1] array
    crosspoint: str | None  # xpt_<signal> node; None for the bus-level bits
    bus: str | None    # "A", "B", or None (cfg_bus_short joins both sides)
    row: int           # bus row 1-6
    rail: str | None = None  # "VAPWR"/"VGND" for rail-tie bits, else None
    pin_net: str | None = None  # "ua1".."ua5" for cfg_bus_ext bits, else None


@dataclass(frozen=True)
class DeviceSettingBit:
    """A bit that sets a device rather than closing a matrix switch: the
    device widths, mirror ratios, diff-pair and OTA tails, the FET source
    ties, the diff-pair source ties, and the OTA's output mode.
    """

    bit: int    # position in the config chain
    pin: str    # mosbius.sym pin name, e.g. "ctrl_pfeta_width"
    index: int  # 0-based bit position within that pin (0 for single-bit pins)
